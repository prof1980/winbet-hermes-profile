#!/usr/bin/env python3
"""
Daily Report Sender — Template riusabile per report periodici via email.

Copia questo file, modifica:
- collect_db_stats() con le query al tuo DB
- render_text_report() e render_html_report() con le sezioni che ti servono

Mantiene invariati: CLI args, sanitizzazione log, dual format, dry-run.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dotenv"]
# ///

from __future__ import annotations
import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "execution"))
from libero_notifier import LiberoNotifier  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("daily_report")

DB_PATH = _PROJECT_ROOT / "data.db"  # ← MODIFICA QUI


# --- DATA COLLECTION -------------------------------------------------------

def collect_db_stats() -> dict:
    """Raccoglie statistiche dal database. MODIFICA con le tue query."""
    if not DB_PATH.exists():
        return {"error": "Database non trovato"}
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    stats = {}
    # Esempio: conta record in tabelle note
    for table in ["matches", "odds", "surebets"]:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            stats[f"total_{table}"] = c.fetchone()[0]
        except sqlite3.OperationalError:
            stats[f"total_{table}"] = 0
    conn.close()
    return stats


def collect_system_health() -> dict:
    """Salute sistema: disco, dimensione DB."""
    import shutil
    health = {}
    if DB_PATH.exists():
        health["db_size_mb"] = DB_PATH.stat().st_size / (1024**2)
    disk = shutil.disk_usage(_PROJECT_ROOT)
    health["disk_free_gb"] = disk.free / (1024**3)
    health["disk_used_percent"] = (disk.used / disk.total) * 100
    return health


# --- REPORT RENDERING ------------------------------------------------------

def render_text_report(stats: dict, health: dict, days: int = 1) -> str:
    """Report plaintext. MODIFICA le sezioni."""
    now = datetime.now(timezone.utc)
    lines = [
        "=" * 70,
        f"📊 REPORT {'GIORNALIERO' if days == 1 else f'ULTIMI {days} GIORNI'}",
        f"📅 Generato: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "=" * 70,
        "",
        "🖥️  STATO SISTEMA",
        "-" * 70,
    ]
    if "db_size_mb" in health:
        lines.append(f"  • Database: {health['db_size_mb']:.2f} MB")
    if "disk_free_gb" in health:
        lines.append(f"  • Disco libero: {health['disk_free_gb']:.1f} GB")
    # Aggiungi qui le tue sezioni
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def render_html_report(stats: dict, health: dict, days: int = 1) -> str:
    """Report HTML con CSS inline. MODIFICA le sezioni."""
    css = """
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .header { background: #1e3a8a; color: white; padding: 20px; border-radius: 8px; }
        .card { background: white; padding: 15px 20px; border-radius: 8px; margin: 15px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    </style>
    """
    body = "<h1>📊 Report</h1>"
    if "db_size_mb" in health:
        body += f"<div class='card'>DB: {health['db_size_mb']:.2f} MB</div>"
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'>{css}</head><body>{body}</body></html>"


# --- MAIN ------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Daily Report via email")
    parser.add_argument("--to", required=True, help="Destinatari (CSV)")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--subject-prefix", default="Report")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = collect_db_stats()
    health = collect_system_health()
    text = render_text_report(stats, health, args.days)
    html = render_html_report(stats, health, args.days)
    subject = f"[{args.subject_prefix}] Report {datetime.now():%Y-%m-%d}"

    if args.dry_run:
        print("=" * 70)
        print(f"SUBJECT: {subject}")
        print("=" * 70)
        print(text)
        return 0

    n = LiberoNotifier()
    for recipient in [r.strip() for r in args.to.split(",") if r.strip()]:
        ok = n.send_email(to=recipient, subject=subject, body=text, html_body=html)
        log.info(f"{'✅' if ok else '❌'} {recipient}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
