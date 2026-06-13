#!/usr/bin/env python3
"""WinBet Skill Bridge — Connette la skill bookmaker-odds-scraper al DB WinBet.

1. Esegue bookmaker_scraper.py con i parametri corretti
2. Converte l'output JSON nel formato del database
3. Inserisce/aggiorna quote nel DB WinBet
"""

import sqlite3
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

DB_PATH = "winbet.db"
CONFIG_PATH = "winbet_config.json"

SKILL_DIR = Path.home() / ".hermes" / "skills" / "bookmaker-odds-scraper" / "scripts"
SCRAPER_SCRIPT = SKILL_DIR / "bookmaker_scraper.py"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def run_skill_scraper(bookmaker: str, league_id: str, output_file: str) -> dict:
    """Esegue la skill bookmaker_scraper.py e restituisce il risultato JSON."""

    # Mappa league_id a competition key della skill
    comp_map = {
        "serie-a": "serie-a",
        "serie-b": "serie-b",
        "premier-league": "premier-league",
        "la-liga": "la-liga",
        "bundesliga": "bundesliga",
        "ligue-1": "ligue-1",
        "champions-league": "champions-league",
        "europa-league": "europa-league"
    }

    competition = comp_map.get(league_id, league_id)

    cmd = [
        "python3", str(SCRAPER_SCRIPT),
        "scrape",
        "--bookmaker", bookmaker,
        "--sport", "calcio",
        "--competition", competition,
        "--output", output_file
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {}
        with open(output_file) as f:
            return json.load(f)
    except Exception:
        return {}

def import_to_db(data: dict, league_id: str):
    """Importa i risultati della skill nel database WinBet."""
    if not data or not data.get("events"):
        return 0

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    bookmaker = data.get("bookmaker", "unknown")
    updated = 0

    for event in data["events"]:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        start = event.get("start_time", "")
        if not home or not away:
            continue

        match_id = f"{league_id}_{home.lower().replace(' ', '')}_{away.lower().replace(' ', '')}_{start[:10].replace('-', '')}"

        c.execute("""
            INSERT OR IGNORE INTO matches (match_id, league_id, home_team, away_team, match_date, match_time, status)
            VALUES (?, ?, ?, ?, ?, ?, 'scheduled')
        """, (match_id, league_id, home, away, start[:10], start[11:16] if len(start) > 11 else "20:00"))

        for market in event.get("markets", []):
            mkt_type = market.get("type", "1x2").lower().replace("match_result", "1x2").replace("over_under", "ou25")
            for sel in market.get("selections", []):
                odds = sel.get("odds", 0.0)
                if odds <= 1.0:
                    continue
                c.execute("""
                    INSERT OR REPLACE INTO odds (match_id, bookmaker_id, market_type, selection_name, selection_label, odds_value, odds_decimal, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (match_id, bookmaker, mkt_type, sel.get("name", ""), sel.get("label", ""), odds, odds, datetime.now().isoformat()))
                updated += 1

    conn.commit()
    conn.close()
    return updated

def main():
    cfg = load_config()
    if cfg["mode"] == "DEMO":
        return  # DEMO usa scraper.py interno

    os.makedirs(".tmp/skill_output", exist_ok=True)
    for bm in cfg.get("bookmakers", []):
        if not bm.get("enabled", False):
            continue
        for league in cfg.get("leagues", []):
            if not league.get("enabled", False):
                continue
            out_file = f".tmp/skill_output/{bm['id']}_{league['id']}.json"
            data = run_skill_scraper(bm["id"], league["id"], out_file)
            if data:
                import_to_db(data, league["id"])

if __name__ == "__main__":
    main()
