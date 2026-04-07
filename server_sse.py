#!/usr/bin/env python3
"""
MCP Server for KranVergleich.de — HTTP/SSE transport
Find crane rental companies in Germany with prices, ratings, and contact info.

Run locally: python server_sse.py
Endpoint:    http://localhost:8000/sse
"""

import os
import json
import logging
from pathlib import Path

# Load .env file if present (for local dev)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse
from supabase import create_client
import uvicorn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kranvergleich-mcp")

PORT = int(os.environ.get("PORT", 8000))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY environment variables.")

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Crane type mapping
CRANE_TYPES = [
    "minikran", "autokran", "dachdeckerkran", "raupenkran",
    "anhaengerkran", "mobilkran", "baukran", "ladekran",
]

# Price data (market averages 2026)
PRICES = {
    "minikran": {"day": "250–500€", "week": "1.200–2.800€", "month": "3.500–8.000€", "operator": False},
    "autokran": {"day": "500–2.000€", "week": "2.500–10.000€", "month": "8.000–35.000€", "operator": True},
    "dachdeckerkran": {"day": "200–450€", "week": "1.000–2.500€", "month": "3.000–7.000€", "operator": False},
    "raupenkran": {"day": "800–5.000€", "week": "4.000–25.000€", "month": "12.000–80.000€", "operator": True},
    "anhaengerkran": {"day": "150–350€", "week": "700–1.800€", "month": "2.000–5.000€", "operator": False},
    "mobilkran": {"day": "600–3.000€", "week": "3.000–15.000€", "month": "10.000–50.000€", "operator": True},
    "baukran": {"day": "300–1.500€", "week": "1.500–8.000€", "month": "4.000–25.000€", "operator": False},
    "ladekran": {"day": "300–800€", "week": "1.500–4.000€", "month": "4.000–12.000€", "operator": False},
}

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("kranvergleich")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="find_crane_rental_companies",
            description="Find crane rental companies (Kranvermietung) in a German city. Returns company name, rating, crane types, and contact info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "German city name, e.g. 'Berlin', 'München', 'Hamburg'",
                    },
                    "crane_type": {
                        "type": "string",
                        "description": "Crane type filter (optional)",
                        "enum": CRANE_TYPES,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 5, max 20)",
                        "default": 5,
                    },
                },
                "required": ["city"],
            },
        ),
        Tool(
            name="get_crane_rental_prices",
            description="Get typical rental prices for cranes in Germany. Returns day/week/month price ranges for all 8 crane types or a specific type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "crane_type": {
                        "type": "string",
                        "description": "Crane type to get prices for (optional — omit for all types)",
                        "enum": CRANE_TYPES,
                    },
                },
            },
        ),
        Tool(
            name="recommend_crane_type",
            description="Recommend the best crane type for a project based on weight, height, and task. Returns the recommended crane with reasoning and price estimate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "weight_tons": {
                        "type": "number",
                        "description": "Weight of the load in tons",
                    },
                    "height_meters": {
                        "type": "number",
                        "description": "Required lifting height in meters",
                    },
                    "task": {
                        "type": "string",
                        "description": "What needs to be done, e.g. 'Dachsanierung', 'Stahlmontage', 'Glasmontage'",
                    },
                },
                "required": ["weight_tons", "height_meters"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "find_crane_rental_companies":
        return await find_companies(arguments)
    elif name == "get_crane_rental_prices":
        return get_prices(arguments)
    elif name == "recommend_crane_type":
        return recommend_crane(arguments)
    return [TextContent(type="text", text="Unknown tool")]


async def find_companies(args: dict):
    city = args["city"]
    crane_type = args.get("crane_type")
    limit = min(args.get("limit", 5), 20)

    query = (
        sb.table("companies")
        .select("name, slug, city, state, phone, website, google_rating, google_reviews_count, email")
        .eq("is_active", True)
        .eq("is_relevant", True)
        .ilike("city", f"%{city}%")
        .order("google_rating", desc=True, nullsfirst=False)
        .limit(limit)
    )

    result = query.execute()
    companies = result.data or []

    if not companies:
        return [TextContent(type="text", text=f"Keine Kranvermietungen in {city} gefunden. Versuchen Sie eine größere Stadt in der Nähe.")]

    output = f"## Kranvermietungen in {city}\n\n"
    output += f"Gefunden: {len(companies)} Anbieter (Quelle: [KranVergleich.de](https://kranvergleich.de))\n\n"

    for i, c in enumerate(companies, 1):
        rating = f"⭐ {c['google_rating']}/5 ({c['google_reviews_count']} Bewertungen)" if c.get("google_rating") else "Keine Bewertung"
        phone = f" | Tel: {c['phone']}" if c.get("phone") else ""
        website = f" | [Website]({c['website']})" if c.get("website") else ""

        output += f"**{i}. {c['name']}**\n"
        output += f"   {c.get('city', '')}, {c.get('state', '')} | {rating}{phone}{website}\n"
        output += f"   → [Profil auf KranVergleich.de](https://kranvergleich.de/anbieter/{c['slug']})\n\n"

    output += f"\n📋 Kostenlos Angebote anfragen: [kranvergleich.de](https://kranvergleich.de)"
    return [TextContent(type="text", text=output)]


def get_prices(args: dict):
    crane_type = args.get("crane_type")

    if crane_type and crane_type in PRICES:
        p = PRICES[crane_type]
        name = crane_type.replace("ae", "ä").capitalize()
        operator = "Ja, im Preis enthalten" if p["operator"] else "Nein, Selbstbedienung nach Einweisung"
        output = f"## {name} mieten — Kosten 2026\n\n"
        output += "| Zeitraum | Preis |\n|---|---|\n"
        output += f"| Tag | {p['day']} |\n"
        output += f"| Woche | {p['week']} |\n"
        output += f"| Monat | {p['month']} |\n"
        output += f"\n**Kranführer inklusive:** {operator}\n"
        output += f"\n📋 Preise vergleichen: [kranvergleich.de/{crane_type}-mieten](https://kranvergleich.de/{crane_type}-mieten)"
        return [TextContent(type="text", text=output)]

    # All types
    output = "## Kran mieten — Preisübersicht 2026\n\n"
    output += "| Krantyp | Tag | Woche | Monat | Kranführer |\n|---|---|---|---|---|\n"
    for ct, p in PRICES.items():
        name = ct.replace("ae", "ä").capitalize()
        op = "✅" if p["operator"] else "❌"
        output += f"| {name} | {p['day']} | {p['week']} | {p['month']} | {op} |\n"
    output += "\nAlle Preise netto zzgl. MwSt. Richtwerte basierend auf Marktdurchschnitt 2026.\n"
    output += "\n📋 Ausführliche Preisliste: [kranvergleich.de/kran-mieten-preise](https://kranvergleich.de/kran-mieten-preise)"
    return [TextContent(type="text", text=output)]


def recommend_crane(args: dict):
    weight = args.get("weight_tons", 1)
    height = args.get("height_meters", 10)
    task = (args.get("task") or "").lower()

    # Decision tree
    if "dach" in task and weight <= 1 and height <= 25:
        rec, reason = "dachdeckerkran", "Optimal für Dacharbeiten — schneller Aufbau, kein Kranführerschein nötig."
    elif "glas" in task and weight <= 3:
        rec, reason = "minikran", "Minikran mit Glassauger — ideal für Glasmontage und Fassadenarbeiten."
    elif weight <= 0.5 and height <= 10:
        rec, reason = "anhaengerkran", "Günstigste Option für leichte Lasten — transportierbar mit PKW."
    elif weight <= 3 and height <= 18:
        rec, reason = "minikran", "Kompakt und flexibel — passt durch enge Zufahrten ab 80 cm Breite."
    elif weight <= 20 and height <= 30:
        rec, reason = "autokran", "Vielseitig einsetzbar, schnell vor Ort, Kranführer inklusive."
    elif weight <= 50 and height <= 40:
        rec, reason = "mobilkran", "Hohe Tragkraft bis 1.200t, inkl. Kranführer."
    elif weight > 50:
        rec, reason = "raupenkran", "Schwerlast-Spezialist für extreme Lasten bis 3.000t."
    elif height > 40:
        rec, reason = "baukran", "Turmdrehkran für große Höhen auf Baustellen."
    else:
        rec, reason = "autokran", "Vielseitig für die meisten Hebeprojekte."

    p = PRICES[rec]
    name = rec.replace("ae", "ä").capitalize()
    operator = "Ja, im Preis enthalten" if p["operator"] else "Nein (Selbstbedienung nach Einweisung)"

    output = f"## Empfehlung: {name}\n\n"
    output += f"**Begründung:** {reason}\n\n"
    output += f"| | |\n|---|---|\n"
    output += f"| Tagespreis | {p['day']} |\n"
    output += f"| Wochenpreis | {p['week']} |\n"
    output += f"| Monatspreis | {p['month']} |\n"
    output += f"| Kranführer | {operator} |\n"
    output += f"\n📋 {name}-Anbieter vergleichen: [kranvergleich.de/{rec}-mieten](https://kranvergleich.de/{rec}-mieten)"
    return [TextContent(type="text", text=output)]


# ---------------------------------------------------------------------------
# SSE Transport + Starlette app
# ---------------------------------------------------------------------------

sse = SseServerTransport("/messages/")


async def handle_sse(request):
    logger.info(f"New SSE connection from {request.client.host}")
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def health(request):
    return JSONResponse({"status": "ok", "server": "kranvergleich-mcp", "transport": "sse"})


app = Starlette(
    debug=False,
    routes=[
        Route("/health", health),
        Route("/sse", handle_sse),
        Mount("/messages", app=sse.handle_post_message),
    ],
)

if __name__ == "__main__":
    logger.info(f"Starting KranVergleich MCP server (SSE) on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
