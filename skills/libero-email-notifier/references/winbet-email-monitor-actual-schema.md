# WinBet Email Monitor — Schema reale, pitfalls Gmail, monitor cadence

Documento di riferimento operativo per l'email control plane di WinBet, basato
sulla sessione di setup del 5 Giugno 2026.

## Indirizzo Gmail destinatario

L'utente Angelo riceve i report a **`angelo.bruno80@gmail.com`**. Mittente è
`watson.ag@libero.it`. Pitfall osservato:

**Libero.it è spesso classificato da Gmail come "Promozioni" / "Aggiornamenti"**
anziché "Principale". Conseguenze:

- L'email non compare nella inbox principale → l'utente pensa che il sistema
  non funzioni
- Anche il report giornaliero delle 8:00 può finire lì

**Mitigazione comunicata all'utente**: alla prima email, istruire a:
1. Aprire l'email in Gmail
2. Cliccare "Sposta in Principale" (in alto) oppure spostare manualmente
3. Selezionare "Fallo sempre per questo mittente"

Questo deve essere detto **esplicitamente** nel primo invio di test, idealmente
incluso come footer del primo report.

## Schema DB reale WinBet (da ispezionare SEMPRE prima di scrivere query)

Lo schema è **più strano del previsto**. NON fidarsi dei nomi di colonna "ovvi".

```python
import sqlite3
conn = sqlite3.connect("winbet.db")
c = conn.cursor()
c.execute("PRAGMA table_info(<table>)")
for col in c.fetchall():
    print(col[1], col[2])
```

| Tabella | Colonne chiave | Pitfall |
|---|---|---|
| `matches` | `match_id`, `league_id` (testo leggibile tipo `"FIFA World Cup"`), `home_team`, `away_team`, `match_date`, `match_time` | La lega è memorizzata in `league_id` direttamente, NON in una colonna `league` separata. Query: `WHERE LOWER(league_id) LIKE ?` |
| `odds` | `match_id`, `bookmaker_id`, `market_type` (es. `"1X2"`, `"gng"`, `"ou25"`), `selection_name`, `selection_label`, `odds_decimal` | Le quote sono in **`odds_decimal`** (float), NON in una colonna `odds`. C'è anche `odds_value` (raw) usato raramente |
| `surebets` | `match_id`, `market_type`, `selections` (JSON), `profit_percent`, `total_implied_prob` | `selections` è una stringa JSON, non un dict relazionale. Va parsata con `json.loads()`. Vedi struttura sotto |
| `scrape_log` | `bookmaker_id`, `matches_found`, `odds_found`, `errors` (TEXT, NULL/empty = successo), `started_at`, `completed_at` | **NON c'è una colonna `success` (bool)**. Usare `errors IS NULL OR errors = ''` come predicato di successo. `started_at` ≠ `completed_at` |
| `odds_history` | colonne standard time-series | |
| `notifications` | log delle notifiche inviate | |

### Struttura del JSON in `surebets.selections`

```json
[
  {
    "selection": "1",
    "label": "Casa",
    "odds": 1.85,
    "bookmaker": "eurobet"
  },
  {
    "selection": "X",
    "label": "Pareggio",
    "odds": 3.40,
    "bookmaker": "snai"
  }
]
```

**Pitfall comune**: usare `sel.get("outcome", "?")` produce "?" ovunque. La
chiave corretta è `selection` o `label`. Pattern difensivo consigliato:

```python
oc = sel.get("label", sel.get("selection", sel.get("outcome", "?")))
```

Questo gestisce 3 varianti osservate (WinBet vecchio, WinBet nuovo, The Odds API).

## winbet_config.json — Struttura nested

NON è flat. Errore comune: `cfg.get("interval_minutes")` ritorna `None`.
Path corretti:

```python
cfg = json.loads(open("winbet_config.json").read())
cfg["scrape"]["interval_minutes"]      # 60, 120, ecc.
cfg["scrape"]["bookmakers_enabled"]    # ["snai", "eurobet", ...]
cfg["mode"]                            # "LIVE" o "DEMO"
```

Vedi `templates/winbet_config.example.json` per un esempio canonico.

## Cronjob monitor IMAP

Per il monitor IMAP continuo (utente invia comando → sistema risponde), la
frequenza giusta è **ogni 10 minuti** (`every 10m` in Hermes cronjob). Non meno
per evitare rate-limiting IMAP di Libero; non di più per non ritardare troppo
la risposta percepita dall'utente.

```bash
hermes cronjob create \
  --name "WinBet Email Monitor" \
  --schedule "every 10m" \
  --prompt "Esegui: cd /mnt/c/Users/angel/WinBet && ./venv/bin/python execution/winbet_email_handler.py monitor --interval 600"
```

L'intervallo interno al monitor (parametro `--interval` di `monitor_inbox`) può
essere più alto (es. 600s = 10 min) per non fare polling strettissimo.

## End-to-end test pipeline

Sequenza di test che ha funzionato il 5 Giugno 2026:

```bash
# 1. Setup credenziali in .env
LIBERO_EMAIL=watson.ag@libero.it
LIBERO_PASSWORD=***
LIBERO_SMTP_HOST=smtp.libero.it
LIBERO_SMTP_PORT=465
LIBERO_SMTP_SSL=true
LIBERO_IMAP_HOST=imapmail.libero.it
LIBERO_IMAP_PORT=993

# 2. Test invio SMTP
./venv/bin/python execution/libero_notifier.py test-send
# → "Email inviata a watson.ag@libero.it | subject='[WinBet] Test invio'"

# 3. Test ricezione IMAP
./venv/bin/python execution/libero_notifier.py test-fetch
# → "Trovate N email in inbox"

# 4. Invia comando "status" all'utente (simula utente)
./venv/bin/python execution/winbet_daily_report.py --to watson.ag@libero.it --dry-run

# 5. Esegui handler (leggere inbox, parsare, rispondere)
./venv/bin/python execution/winbet_email_handler.py test
# → "Comando: status | args: " + invio risposta SMTP

# 6. Verifica risposta ricevuta
./venv/bin/python execution/libero_notifier.py test-fetch
# → Trova la RE: tra le email
```

## Comandi email supportati

Parser regex robusto (case-insensitive, normalizza prefissi):

```python
text = msg.subject or ""
text += " " + (msg.body or "")[:200]
text = text.lower().strip()
text = re.sub(r"\[winbet\]\s*", "", text)
text = re.sub(r"^(comando|cmd|command):\s*", "", text)
```

Comandi:
| Pattern | Action |
|---|---|
| `status` / `stato` / `report` | Report DB + scraper + bookmaker |
| `surebet` / `arbitraggio` / `arb` | Top 10 surebet ≥1% |
| `matches <lega>` | Es. "matches serie a" → partite |
| `odds <squadra>` | Es. "odds Inter" → quote |
| `stop` / `ferma` / `pausa` | Metti scraper in pausa (scrive flag file) |
| `start` / `riprendi` / `via` | Riprendi scraper (rimuove flag) |
| `help` / `aiuto` / `comandi` | Lista comandi |

## Stop/Start via flag file (no DB)

Per non dover modificare lo schema DB, lo stop/start scrive un file flag:

```python
from pathlib import Path
import os

# Path: <project>/.tmp/scraper_paused.flag
flag_path = Path(__file__).parent.parent / ".tmp" / "scraper_paused.flag"

def _cmd_stop(self) -> str:
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    flag_path.write_text(datetime.now().isoformat())
    return "⏸️ Scraper WinBet in pausa. Usa 'start' per riprendere."

def _cmd_start(self) -> str:
    if flag_path.exists():
        flag_path.unlink()
    return "▶️ Scraper WinBet riattivato."
```

Lo scraper in `scrape_cycle.sh` può controllare:

```bash
if [ -f .tmp/scraper_paused.flag ]; then
    echo "Scraper in pausa, skip ciclo"
    exit 0
fi
```

## Report giornaliero 8:00 (con dual format HTML+plaintext)

Pattern adottato:

```python
# Subject
subject = f"[WinBet] Report {datetime.now():%Y-%m-%d}"

# Testo (sempre presente, per client testuali)
text = render_text_report(stats, health, days=args.days)

# HTML (opzionale ma sempre gradito, per client moderni)
html = render_html_report(stats, health, days=args.days)

# Invia entrambi nello stesso messaggio MIME multipart/alternative
n.send_email(to=recipient, subject=subject, body=text, html_body=html)
```

**Sezioni tipiche** (nell'ordine):
1. Header con timestamp e totali (partite, quote, surebet)
2. Stato sistema (DB size, disco, modalità, bookmaker abilitati)
3. Bookmaker attivi (top 10 per partite)
4. Top campionati
5. Surebet con conteggi per fascia profitto + top 10 dettagliate
6. Cronologia scraping (ultimi 7 giorni)
7. Footer con link dashboard e info comandi email

**Flag `--dry-run` SEMPRE** prima dell'invio reale. L'utente vuole
vedere cosa sta per essere inviato:

```python
if args.dry_run:
    print("=" * 70)
    print(f"SUBJECT: {subject}")
    print("=" * 70)
    print(text)
    return 0
```

## Pitfall multi-destinatario con SMTP relay

Libero permette di inviare a un solo destinatario "vero" per sessione SMTP.
Multi-destinatario funziona se sono tutti `@libero.it` (same domain), ma
l'invio a `angelo.bruno80@gmail.com` da `watson.ag@libero.it` funziona solo
perché Libero fa relay verso Gmail (raro ma consentito su account Free).

Per essere robusti, ciclare `n.send_email(to=recipient, ...)` per ogni
destinatario. Loggare success/fail per ciascuno.
