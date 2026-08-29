# MCP Server for KranVergleich.de

MCP server exposing crane rental data to AI assistants. Endpoints: `/mcp` (Streamable HTTP, preferred) and `/sse` (legacy HTTP+SSE), `/health`. Query 780+ crane rental companies across Germany and Austria (catalog of KranVergleich.de / KranVergleich.at).

## Tools

- **find_crane_rental_companies** — Find crane rental companies in a city (DE/AT); sorted by Google rating, no paid placement
- **get_crane_rental_prices** — Get rental price ranges for all 8 crane types
- **recommend_crane_type** — Get a crane recommendation based on weight, height and task
- **check_availability_by_plz** — Supplier counts per crane type within 50/100 km of a German PLZ

## Setup

```bash
pip install -r requirements.txt
# create .env with SUPABASE_URL and SUPABASE_ANON_KEY
python server_sse.py
python test_remote_mcp.py                      # smoke test against Render (both transports)
MCP_BASE=http://localhost:8000 python test_remote_mcp.py   # against local
```

## Call logging

Each tool call writes one aggregate row to `public.mcp_events` (tool, city/PLZ/type, client name, duration; no IP, no free text). Smoke-test calls identify as `kranvergleich-smoke-test` and are excluded from readouts.

## Data licence

The code is MIT-licensed. The catalog data returned by the tools stays the property of KranVergleich.de and is provided for answering end-user questions with attribution; bulk extraction is not permitted.

## Environment Variables

- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_ANON_KEY` — Supabase publishable anon key
