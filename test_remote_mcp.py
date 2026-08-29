#!/usr/bin/env python3
"""Smoke test for the deployed MCP server (or a local one via MCP_URL).

Exercises all four tools and fails loudly when check_availability_by_plz
returns the "PLZ nicht gefunden" text for a valid PLZ (that was the symptom of
german-cities.json missing from the Docker image, unnoticed 27.04 - 29.08).

Usage: python test_remote_mcp.py            # remote (Render)
       MCP_URL=http://localhost:8000/sse python test_remote_mcp.py
"""
import asyncio
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from mcp import ClientSession
from mcp.client.sse import sse_client

URL = os.environ.get("MCP_URL", "https://mcp-kranvergleich.onrender.com/sse")

CASES = [
    ("find_crane_rental_companies", {"city": "Berlin", "limit": 3}, ["Profil auf KranVergleich.de", "?ref=mcp", "Sortiert nach"]),
    ("find_crane_rental_companies", {"city": "Wien", "limit": 2}, ["kranvergleich.at/anbieter/"]),
    ("find_crane_rental_companies", {"city": "%", "limit": 2}, ["mindestens 2 Zeichen"]),
    ("find_crane_rental_companies", {"city": "%%", "limit": 2}, ["Keine Kranvermietungen"]),  # wildcard escaped
    ("get_crane_rental_prices", {"crane_type": "autokran"}, ["500–2.000€", "?ref=mcp"]),
    ("recommend_crane_type", {"weight_tons": 2.8, "height_meters": 12, "task": "Sauna"}, ["Empfehlung"]),
    ("check_availability_by_plz", {"plz": "89584"}, ["Verfügbarkeit für PLZ 89584", "| minikran |", "| autokran |"]),
]


async def main() -> int:
    failures = 0
    t0 = time.time()
    print(f"Connecting to {URL} ...")
    async with sse_client(URL, timeout=90) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"Initialized OK in {time.time() - t0:.1f}s")
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"Tools: {names}")
            assert len(names) == 4, names

            for name, args, expect in CASES:
                t = time.time()
                result = await session.call_tool(name, args)
                text = "\n".join(getattr(c, "text", "") for c in result.content)
                missing = [e for e in expect if e not in text]
                status = "OK " if not missing else "FAIL"
                if missing:
                    failures += 1
                print(f"[{status}] {name} {args} ({time.time() - t:.1f}s)" + (f" missing={missing}" if missing else ""))
                print("      " + text[:300].replace("\n", "\n      "))
                if name == "check_availability_by_plz" and "nicht im PLZ-Verzeichnis" in text:
                    print("      >>> german-cities.json missing from deployment?")
    print(f"\n{'ALL OK' if not failures else str(failures) + ' FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
