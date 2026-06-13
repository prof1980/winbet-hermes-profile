---
name: libero-email-notifier
description: >
  Bidirectional email control plane per progetti Python: SMTP per invio (report, notifiche) e IMAP per ricevere comandi. Pattern riusabile con qualsiasi provider IMAP/SMTP standard (Libero.it, Gmail con App Password, Outlook, Yahoo). Include template per daily report HTML+plaintext e command handler con whitelist mittenti.
---

# Libero.it Email Notifier — Pattern Riusabile

## Quando usare

In qualsiasi progetto Python servia:
- Inviare email transazionali/report (SMTP)
- Ricevere email e processarle come comandi (IMAP)
- Monitorare una inbox per automazioni
- Notifiche email senza dipendenze da servizi terzi (SendGrid, Mailgun, ecc.)
- **Report periodici schedulati** (HTML+plaintext) — vedi [Daily Report Pattern](#daily-report-pattern)
- **Command-plane via email** (utente scrive, sistema risponde) — vedi [Command Handler Pattern](#command-handler-pattern)

## File in questa skill

- `templates/daily_report.py` — scheletro copy-and-modify per report periodici (dual format, dry-run, multi-destinatario)
- `templates/email_handler.py` — scheletro copy-and-modify per command handler via email (whitelist, parser, dispatch)
- `references/winbet-implementation.md` — implementazione reale WinBet, schema DB, cronjob, indirizzi email
- `references/winbet-email-monitor-actual-schema.md` — schema DB reale WinBet, JSON `selections` structure, cronjob IMAP 10m, Gmail→Libero spam pitfall, dual-format report
- `references/html-report-styling.md` — pattern CSS per email HTML (stat boxes, tabelle, color coding profit), pitfall con backslash in f-string, scheduling

## Provider supportati

Funziona con qualsiasi provider che espone SMTP/IMAP standard:
- **Libero.it**: `smtp.libero.it:465` SSL, `imapmail.libero.it:993` SSL
- **Gmail**: `smtp.gmail.com:587` STARTTLS, `imap.gmail.com:993` SSL (richiede App Password)
- **Outlook**: `smtp.office365.com:587`, `outlook.office365.com:993`
- **Yahoo**: `smtp.mail.yahoo.com:465`, `imap.mail.yahoo.com:993`

## Variabili d'ambiente (.env)

```
EMAIL_USER=tuonome@libero.it
EMAIL_PASSWORD=***  # non committare, chmod 600
SMTP_HOST=smtp.libero.it
SMTP_PORT=465
SMTP_SSL=true
IMAP_HOST=imapmail.libero.it
IMAP_PORT=993
```

## Pattern base

```python
import smtplib, imaplib, ssl, email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os, time, logging

load_dotenv()

class EmailNotifier:
    def __init__(self):
        self.user = os.getenv("EMAIL_USER")
        self.password = os.getenv("EMAIL_PASSWORD")

    def send(self, to, subject, body, html=None):
        msg = MIMEMultipart("alternative")
        msg["From"] = self.user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.libero.it", 465, context=ctx, timeout=30) as s:
            s.login(self.user, self.password)
            s.sendmail(self.user, [to], msg.as_string())

    def fetch(self, limit=10, unseen_only=True):
        msgs = []
        ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL("imapmail.libero.it", 993, ssl_context=ctx) as imap:
            imap.login(self.user, self.password)
            imap.select("INBOX")
            crit = "UNSEEN" if unseen_only else "ALL"
            _, data = imap.search(None, crit)
            for num in data[0].split()[-limit:]:
                _, raw = imap.fetch(num, "(RFC822)")
                msgs.append(email.message_from_bytes(raw[0][1]))
            imap.close()
        return msgs

    def monitor(self, callback, interval=60):
        seen = set()
        while True:
            for msg in self.fetch(unseen_only=True):
                uid = msg.get("Message-ID")
                if uid in seen: continue
                seen.add(uid)
                callback(msg)
            time.sleep(interval)
```

## Pitfall

- **MAI stampare la password**: usare funzione `_sanitize(text)` che la sostituisce con `***REDACTED` prima di loggare
- **Encoding subject**: email.header.decode_header() gestisce encoded-word (es. `=?utf-8?B?...?=`)
- **Charset email body**: usare `part.get_content_charset() or "utf-8"` con `errors="replace"`
- **SSL vs STARTTLS**: porta 465 = SSL diretto, porta 587 = STARTTLS
- **IMAP folder case**: "INBOX" è case-sensitive su alcuni server
- **Timeout**: sempre specificare `timeout=30` per evitare blocchi
- **Permessi .env**: `chmod 600` per evitare lettura da altri utenti
- **Rate limiting**: monitor con intervallo >= 60s per evitare blocchi
- **Filtro mittenti**: in handler che esegue comandi, whitelista solo mittenti autorizzati
- **Libero→Gmail è classificato come "Promozioni"**: prima email, istruire l'utente a spostarla in "Principale" e marcare "Fallo sempre per questo mittente". Vedi `references/winbet-email-monitor-actual-schema.md`

## Operazioni & Troubleshooting

Vedi `references/winbet-email-monitor-ops.md` per checklist operativa reale (log, PID, IMAP health-check, crash-loop recovery).
Vedi `references/crash-loop-guard-protect-example.md` per un log reale di crash loop con guard circuit breaker (exit 143 → 137, 6 riavvii in 3 min, fermo di sicurezza, recovery dopo ore).
Vedi `references/cron-status-report-pattern.md` per il formato di report strutturato da usare quando un cron job dice "esegui e mantieni in esecuzione" ma il sistema è già attivo e sano — include tabella PID, excerpt log, checklist funzionalità, e note operative.
Vedi `references/winbet-email-monitor-deployment-session-2026-06-09.md` per deployment effettivo con `run_email_monitor.py` supervisor.

### Supervisor script (pattern raccomandato)

Il progetto WinBet include `run_email_monitor.py` — uno **supervisor loop** in Python che:
1. Avvia il monitor come child process con `Popen(..., stdout=logf, stderr=STDOUT)`
2. Scrive il PID del child su `email_handler.pid`
3. Se il child termina (qualsiasi exit code), attende 5 secondi e riavvia
4. Scrive tutto l'output (stdout+stderr) su `email_handler.log` (append)

Questo è il pattern preferito per email monitor a lunga durata, perché isola il monitor dal processo sorgente (Hermes cronjob) e fornisce auto-recovery senza dover ricorrere a `nohup` o `systemd`.

```bash
cd /mnt/c/Users/angel/WinBet && ./venv/bin/python run_email_monitor.py
```

Non avviare direttamente `winbet_email_handler.py monitor` in background se il progetto mette a disposizione uno script supervisor: preferisci il supervisor per la resilienza.

### Pitfall: stdout vuoto in background

Quando il monitor è avviato tramite supervisor che redirige `stdout` e `stderr` su file di log (`email_handler.log`), la sessione interattiva **non mostra alcun output** in tempo reale anche se il processo è attivo. Usare `cat` sul file di log per ispezionare lo stato, non fare affidamento su `process(action="log")` o polling del processo parent per vedere l'output del monitor.

```bash
# Stato operativo
head -20 /mnt/c/Users/angel/WinBet/email_handler.log
tail -f /mnt/c/Users/angel/WinBet/email_handler.log   # live

# PID attivo
cat /mnt/c/Users/angel/WinBet/email_handler.pid
```

## Codice completo di riferimento

Vedi `winbet/execution/libero_notifier.py` per implementazione completa con:
- Classe `EmailMessage` dataclass
- `send_email()` con supporto HTML, CC, BCC, allegati
- `fetch_inbox()` con filtri (unseen, since, folder)
- `mark_as_read()` per IMAP
- `search_emails()` con regex su subject/sender
- `monitor_inbox()` con callback e deduplica
- Sanitizzazione credenziali nei log
- CLI: `test-send`, `test-fetch`, `monitor`

## Test

```bash
# Test invio (auto-risponde a se stesso)
python libero_notifier.py test-send

# Test ricezione (mostra ultime 5 email)
python libero_notifier.py test-fetch

# Test monitor (gira continuo con intervallo 60s)
python libero_notifier.py monitor --interval 60
```

---

## Daily Report Pattern

Pattern per report automatici periodici (es. stato sistema, scrape, KPI) inviati a un destinatario via email.

### Architettura

```
┌──────────────┐    cron    ┌──────────────────┐    SMTP    ┌────────────┐
│ Hermes       │───────────▶│ report_sender.py │───────────▶│ destinat.  │
│ cronjob      │  8:00 AM   │ (dry-run + send) │            │ email      │
└──────────────┘            └──────────────────┘            └────────────┘
```

### Caratteristiche essenziali

1. **Dual-format**: ogni report viene generato sia in **plaintext** (per client testuali) sia in **HTML con CSS** (per client moderni). Costruiscili con due funzioni `render_text_report()` e `render_html_report()` che leggono lo stesso dict di statistiche.
2. **Flag `--dry-run`**: SEMPRE offrire `--dry-run` come opzione CLI. L'utente vuole vedere il report a terminale prima dell'invio reale. Pattern:

```python
parser.add_argument("--dry-run", action="store_true", help="Stampa report senza inviare")
...
if args.dry_run:
    print("=" * 70)
    print(f"SUBJECT: {subject}")
    print("=" * 70)
    print(text)
    return 0
```

3. **Destinatario separato dal mittente**: il mittente è l'account SMTP (es. `watson.ag@libero.it`), il destinatario può essere un altro indirizzo (es. `angelo.bruno80@gmail.com`). Parametrizza con `--to` (accetta CSV per multi-destinatario).
4. **Subject con data**: `[NomeProgetto] Report YYYY-MM-DD` — facile da filtrare/cancellare in batch.
5. **Subject prefix configurabile**: `--subject-prefix` per chi vuole personalizzare (es. `[WinBet]` vs `[Daily]`).

### Template skeleton

Vedi `templates/daily_report.py` per uno script di partenza completo con:
- Raccolta statistiche da DB
- Calcolo salute sistema (disco, DB size)
- Generazione testo+HTML con CSS inline
- CLI con `--to`, `--days`, `--dry-run`, `--subject-prefix`

### Schedulazione consigliata

```bash
# Report giornaliero 8:00 UTC
hermes cronjob create \
  --name "Daily Report 8:00" \
  --schedule "0 8 * * *" \
  --prompt "Esegui: cd <PROJ> && ./venv/bin/python execution/daily_report.py --to <DEST>"
```

Per report settimanale: stesso script con `--days 7`. Per più frequenza: duplica il cronjob cambiando orario.

---

## Command Handler Pattern

Pattern per ricevere email dall'utente e parsarle come comandi che eseguono azioni o rispondono con dati dal sistema.

### Architettura

```
utente scrive "status" ─▶ SMTP ─▶ IMAP polling ─▶ handler.callback(msg)
                                                       │
                                                       ▼
                                                cmd parser + executor
                                                       │
                                                       ▼
                                                reply via SMTP
```

### Componente: email handler

Vedi `templates/email_handler.py` per lo scheletro completo. Elementi chiave:

1. **Whitelist mittenti**: MAI eseguire comandi da chiunque. Default: `[self.notifier.email]` (auto-risponditore). Parametrizza con `allowed_senders`.

```python
if msg.from_addr.lower() not in [s.lower() for s in self.allowed_senders]:
    log.warning(f"Sender non autorizzato: {msg.from_addr}")
    return
```

2. **Parser robusto**: cerca il comando prima nel **subject**, poi nei primi 200 caratteri del **body**. Normalizza:
   - Rimuovi prefisso `[NomeProgetto]`
   - Rimuovi prefisso `comando:` / `cmd:` / `command:`
   - Case-insensitive
   - Trim spazi

3. **Dispatch table**: una serie di `if re.match(...)` o un dict `{"status": self._cmd_status, ...}`. Ogni `_cmd_X(self) -> str` ritorna il testo della risposta.

4. **Subject reply**: `RE: <original subject>` se non inizia già con `RE:`. Aiuta il threading del client email.

5. **Limita lunghezza body**: trunca a 8000 caratteri prima dell'invio per evitare problemi con client che rifiutano email enormi.
6. **Conferma SEMPRE le azioni di stato**: comandi come `stop`, `start`, `pause`, `resume` devono restituire un messaggio di conferma esplicito ("⏸️ Scraper in pausa", "▶️ Scraper ripristinato") anche se l'azione è un no-op. L'utente che non riceve feedback tende a inviare il comando ripetutamente, causando email duplicate e confusione.

### Comandi tipici

| Comando | Risposta |
|---|---|
| `status` | Report stato sistema |
| `help` | Lista comandi |
| `stop` / `start` | Toggle pausa |
| `<entity> <query>` | Es. `matches serie a`, `odds Inter` |
| `surebet` | Lista opportunità profittevoli |

### Pitfall: schema DB reale

Quando il command handler interroga un DB esistente, **ispeziona SEMPRE lo schema prima di scrivere query**. Pattern di colonne comuni che variano tra progetti:
- `league` vs `league_id` (questo progetto usa `league_id` che contiene direttamente il nome leggibile)
- `success` (bool) vs `errors IS NULL` (text vuoto = successo)
- `outcome` vs `selection` vs `label` in JSON serializzato

Comando diagnostico:
```python
import sqlite3
conn = sqlite3.connect("db.sqlite")
c = conn.cursor()
c.execute("PRAGMA table_info(table_name)")
for col in c.fetchall():
    print(col[1], col[2])
c.execute("SELECT * FROM table_name LIMIT 3")
for row in c.fetchall():
    print(repr(row))
```

Vedi `references/winbet-email-monitor-actual-schema.md` per i pattern
specifici del progetto WinBet osservati in produzione (es. JSON `selections`
con chiave `selection`/`label`, `odds_decimal` vs `odds_value`).
Vedi anche `references/winbet-email-handler-monitor-commands-2026-06-09.md` per:
- CLI `test` vs `monitor` (best-practice: test prima di monitor)
- Tabella comandi supportati con alias
- Meccanismo stop/start via filesystem flag
- PID file: tracking (no singleton guard!) — supervisione esterna richiesta
- Architettura logging: applicazione su FileHandler, stdout vuoto
- Checklist pre-launch per cron job

### Schedulazione del monitor

```bash
# Monitor IMAP ogni 10 minuti (sweet spot: abbastanza reattivo, non stressante per Libero)
hermes cronjob create \
  --name "Email Monitor" \
  --schedule "every 10m" \
  --prompt "Esegui: cd <PROJ> && ./venv/bin/python run_email_monitor.py"
```

⚠️ **Non serve un monitor ogni 30s**: IMAP è lento, batching va bene. 5-15 minuti è il sweet spot.

⚠️ **Usa lo script supervisor del progetto** se esiste (es. `run_email_monitor.py`). Non avviare direttamente il monitor in background — vedi sezione Supervisor sopra.

---

## Pitfall aggiuntivi (da esperienza WinBet)

Vedi `references/winbet-email-monitor-actual-schema.md` per:
- Schema DB WinBet reale (WinBet specifics)
- Struttura JSON `selections` (tre varianti osservate)
- Cronjob monitor IMAP con cadenza 10m
- Pitfall Gmail: Libero finisce in "Promozioni"
- Comandi email: regex parser case-insensitive
- Stop/Start via flag file (no DB schema change)
- Pattern report giornaliero dual-format (HTML+plaintext)
- Multi-destinatario SMTP relay su Libero

### Config.json WinBet

Non è flat. Struttura:
```json
{
  "scrape": {
    "interval_minutes": 60,
    "bookmakers_enabled": ["snai", "eurobet", ...]
  },
  "mode": "DEMO" | "LIVE"
}
```
Path errato: `cfg.get("interval_minutes")`. Path corretto: `cfg.get("scrape", {}).get("interval_minutes")`.

### Gmail riceve email da Libero

Libero.it è spesso classificato da Gmail come **"Promozioni"** o **"Aggiornamenti"**, non "Principale". L'utente potrebbe non vedere l'email in inbox. Soluzione:
- Chiedi all'utente di spostare la prima email in "Principale" e selezionare "Fallo sempre per questo mittente"
- Oppure: includi nel report un header che invita a controllare spam/promozioni

### Log email troppo verbosi

Dopo un monitor attivo, la inbox si riempie di RE: email. Per il debug, segna tutte come lette dopo il test:
```python
for m in n.fetch_inbox(limit=50, unseen_only=False):
    if m.message_id:
        n.mark_as_read(m.message_id)
```
