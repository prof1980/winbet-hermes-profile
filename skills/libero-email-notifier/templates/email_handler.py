#!/usr/bin/env python3
"""
Email Command Handler — Template riusabile per processare email come comandi.

Copia questo file, modifica:
- Comandi in _parse_command() e relativi handler _cmd_X()
- Query al tuo DB (ispeziona sempre lo schema prima!)
- Eventuali side-effect (scrittura file, update DB, ecc.)

Mantiene invariati: whitelist mittenti, parser, dispatch, reply troncato.
"""
from __future__ import annotations
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "execution"))
from libero_notifier import EmailMessage, LiberoNotifier  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("email_handler")

DB_PATH = _PROJECT_ROOT / "data.db"  # ← MODIFICA QUI


class EmailHandler:
    def __init__(self, allowed_senders: list[str] | None = None) -> None:
        self.notifier = LiberoNotifier()
        self.allowed_senders = allowed_senders or [self.notifier.email]

    def handle(self, msg: EmailMessage) -> None:
        if msg.from_addr.lower() not in [s.lower() for s in self.allowed_senders]:
            log.warning(f"Sender non autorizzato: {msg.from_addr}")
            return
        cmd = self._parse_command(msg)
        if not cmd:
            self._reply(msg, self._cmd_help())
            return
        try:
            response = getattr(self, f"_cmd_{cmd['action']}", lambda a: f"Comando sconosciuto: {cmd['action']}")(cmd["args"])
        except Exception as e:
            log.error(f"Errore comando {cmd['action']}: {e}")
            response = f"❌ Errore: {e}"
        self._reply(msg, response)

    def _parse_command(self, msg: EmailMessage) -> dict | None:
        text = (msg.subject or "") + " " + (msg.body or "")[:200]
        text = re.sub(r"\[WinBet\]\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(comando|cmd|command):\s*", "", text, flags=re.IGNORECASE)
        text = text.lower().strip()
        # MODIFICA: aggiungi pattern per i tuoi comandi
        if re.match(r"^(status|stato)\b", text):
            return {"action": "status", "args": ""}
        if re.match(r"^help\b", text):
            return {"action": "help", "args": ""}
        return None

    # --- Comandi default (MODIFICA O AGGIUNGI) ----------------------------

    def _cmd_status(self, args: str) -> str:
        if not DB_PATH.exists():
            return "❌ DB non trovato"
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        n_tables = c.fetchone()[0]
        conn.close()
        return f"📊 STATUS\nTabelle: {n_tables}\nGenerato: {datetime.now():%Y-%m-%d %H:%M}"

    def _cmd_help(self, args: str = "") -> str:
        return "🤖 Comandi disponibili:\n  status → Report stato\n  help   → Questo messaggio"

    def _reply(self, original: EmailMessage, body: str) -> None:
        subj = original.subject or "Command"
        if not subj.lower().startswith("re:"):
            subj = f"RE: {subj}"
        if len(body) > 8000:
            body = body[:7900] + "\n\n[...troncato...]"
        self.notifier.send_email(to=original.from_addr, subject=subj, body=body)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    p_mon = sub.add_parser("monitor")
    p_mon.add_argument("--interval", type=int, default=120)
    sub.add_parser("test")
    args = parser.parse_args()
    h = EmailHandler()
    if args.command == "monitor":
        h.notifier.monitor_inbox(callback=h.handle, interval_seconds=args.interval)
    else:
        h.handle(EmailMessage(
            from_addr=h.notifier.email, to_addr=h.notifier.email,
            subject="status", body=""
        ))


if __name__ == "__main__":
    main()
