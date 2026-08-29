#!/usr/bin/env python3
"""Smoke test for the deployed MCP server (or a local one via MCP_BASE).

Exercises all four tools over BOTH transports (legacy SSE at /sse, Streamable
HTTP at /mcp) and fails loudly when check_availability_by_plz returns the
"PLZ nicht gefunden" text for a valid PLZ (that was the symptom of
german-cities.json missing from the Docker image, unnoticed 27.04 - 29.08).

The client identifies itself as "kranvergleich-smoke-test" so the readout
(scripts/mcp_events_readout.py in the app repo) can exclude our own calls.

Usage: python test_remote_mcp.py                       # remote (Render)
       MCP_BASE=http://localhost:8000 python test_remote_mcp.py
"""
import asyncio
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Implementation

BASE = os.environ.get("MCP_BASE", "https://mcp-kranvergleich.onrender.com").rstrip("/")
CLIENT_INFO = Implementation(name="kranvergleich-smoke-test", version="2026.08.29")

CASES = [
    ("find_crane_rental_companies", {"city": "Berlin", "limit": 3}, ["Profil auf KranVergleich.de", "?utm_source=mcp&utm_medium=ai-agent", "Sortiert nach"]),
    ("find_crane_rental_companies", {"city": "Wien", "limit": 2}, ["kranvergleich.at/anbieter/"]),
    ("find_crane_rental_companies", {"city": "%", "limit": 2}, ["mindestens 2 Zeichen"]),
    ("find_crane_rental_companies", {"city": "%%", "limit": 2}, ["Keine Kranvermietungen"]),  # wildcard escaped
    ("get_crane_rental_prices", {"crane_type": "autokran"}, ["500–2.000€", "?utm_source=mcp&utm_medium=ai-agent"]),
    ("recommend_crane_type", {"weight_tons": 2.8, "height_meters": 12, "task": "Sauna"}, ["Empfehlung"]),
    ("check_availability_by_plz", {"plz": "89584"}, ["Verfügbarkeit für PLZ 89584", "| minikran |", "| autokran |"]),
]


async def run_cases(session: ClientSession, label: str) -> int:
    failures = 0
    tools = await session.list_tools()
    names = [t.name for t in tools.tools]
    print(f"[{label}] tools: {names}")
    assert len(names) == 4, names
    for name, args, expect in CASES:
        t = time.time()
        result = await session.call_tool(name, args)
        text = "\n".join(getattr(c, "text", "") for c in result.content)
        missing = [e for e in expect if e not in text]
        status = "OK " if not missing else "FAIL"
        failures += bool(missing)
        print(f"[{label}] [{status}] {name} {args} ({time.time() - t:.1f}s)" + (f" missing={missing}" if missing else ""))
        if label == "sse":
            print("      " + text[:240].replace("\n", "\n      "))
        if name == "check_availability_by_plz" and "nicht im PLZ-Verzeichnis" in text:
            print("      >>> german-cities.json missing from deployment?")
    return failures


async def main() -> int:
    failures = 0
    t0 = time.time()
    print(f"Connecting to {BASE}/sse ...")
    async with sse_client(f"{BASE}/sse", timeout=90) as (read, write):
        async with ClientSession(read, write, client_info=CLIENT_INFO) as session:
            await session.initialize()
            print(f"[sse] initialized in {time.time() - t0:.1f}s")
            failures += await run_cases(session, "sse")

    t0 = time.time()
    print(f"\nConnecting to {BASE}/mcp (streamable-http) ...")
    async with streamablehttp_client(f"{BASE}/mcp", timeout=90) as (read, write, _get_session_id):
        async with ClientSession(read, write, client_info=CLIENT_INFO) as session:
            await session.initialize()
            print(f"[http] initialized in {time.time() - t0:.1f}s")
            failures += await run_cases(session, "http")

    print(f"\n{'ALL OK' if not failures else str(failures) + ' FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
