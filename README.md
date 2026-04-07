# MCP Server for KranVergleich.de

MCP server exposing crane rental data to AI assistants. Query 800+ crane rental companies across Germany.

## Tools

- **find_crane_rental_companies** — Find crane rental companies in a German city
- **get_crane_rental_prices** — Get rental prices for all 8 crane types
- **recommend_crane_type** — Get a crane recommendation based on project requirements

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # add your Supabase keys
python server_sse.py
```

## Environment Variables

- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_ANON_KEY` — Supabase publishable anon key
