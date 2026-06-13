# WinBet Email Handler — Session Notes 2026-06-09

## CLI Subcommands

`winbet_email_handler.py` exposes two subcommands:

| Subcommand | Purpose |
|---|---|
| `monitor --interval N` | Long-running IMAP polling loop (sleep-polling daemon) |
| `test` | One-shot synthetic email through the full pipeline: create message, parse command, execute DB query, send SMTP reply |

**Best practice:** always run `test` before `monitor` to validate SMTP/IMAP credentials, DB connectivity, and command parsing without firing up the long-lived loop.

## Supported Commands

All commands are case-insensitive and matched against subject + first 200 chars of body. Prefixes like `[WinBet]`, `comando:`, `cmd:` are stripped automatically.

| Command | Aliases | Action |
|---|---|---|
| `status` | `stato`, `report` | Send DB + scraping status report |
| `surebet` | `arbitraggio`, `arb` | List active surebets with profit >= 1% |
| `matches <league>` | `match` | List matches for a league (LIKE search on `league_id`) |
| `odds <team>` | `odd` | Show 1X2 odds for a team (LIKE on `home_team`/`away_team`) |
| `stop` | `ferma`, `pausa` | Create `.tmp/scraper_paused.flag` to pause scraper |
| `start` | `riprendi`, `via` | Remove `.tmp/scraper_paused.flag` to resume scraper |
| `help` | `aiuto`, `comandi`, `?` | Return command list |

**Reply format:** all replies are sent via SMTP back to the sender, subject prefixed with `RE:` unless already present. Body is truncated to 8000 chars.

## Stop / Start Mechanism

Unlike DB-based toggles, `stop` and `start` use a **filesystem flag**:
- Stop → write `.tmp/scraper_paused.flag` with ISO timestamp
- Start → delete the flag file if present

This avoids DB schema changes and works across processes that simply check `flag_path.exists()`.

## PID File Behavior (Tracking, NOT Singleton Guard)

The handler writes its PID to `execution/.winbet_email_handler.pid` on startup:
```python
PID_FILE.write_text(str(os.getpid()))
```

It does **not** check whether another process is already running before overwriting. This means:
- Two copies of `monitor` can run simultaneously (IMAP/SMTP double-polling, database contention)
- The PID file is useful for tracking and supervisor health-checks, but **not** for duplicate prevention
- External supervision must enforce singleton (e.g. `flock`-based guard, or a supervisor that checks `pgrep` before launching)

## Logging Architecture

`winbet_email_handler.py` imports `LiberoNotifier` from `libero_notifier.py`, which configures Python `logging` with a `FileHandler`. Key consequence:
- **Stdout/stderr is empty** — `terminal(background=true)` will show no output
- **Application logs** are written to `logs/winbet_email_monitor.log` and `logs/email_monitor.log`
- When diagnosing health, always tail the application log, not the stdout capture

Example log lines (healthy):
```
2026-06-09 14:39:46 [INFO] libero_notifier: Avvio monitor inbox (intervallo: 300s)
2026-06-09 14:39:46 [INFO] libero_notifier: IMAP connesso a imapmail.libero.it:993
2026-06-09 14:39:47 [INFO] libero_notifier: Email inviata a watson.ag@libero.it | subject='RE: status'
2026-06-09 14:39:47 [INFO] libero_notifier: Email 375 segnata come letta
```

## Supervision in This Session

This session deployed a bash supervisor (`winbet_monitor_supervisor.sh`) that:
1. Reads the PID file every 60s
2. If `kill -0 $PID` fails, restarts the monitor with `nohup`
3. Logs wrapper decisions to the same log file as the child

Because the child already has its own logging and a tracking PID file, a simple bash-loop supervisor is the right lightweight choice (no need for a double-fork Python daemon).

## Pre-Launch Checklist for Cron Jobs

When a cron job says "execute and keep it running":
1. `ps aux | grep winbet_email_handler | grep -v grep` — check for existing instances
2. `tail -n 20 logs/winbet_email_monitor.log` — verify recent log timestamps
3. `cat execution/.winbet_email_handler.pid` — check PID file
4. If healthy and supervised: report status, do NOT kill/relaunch
5. If missing or stale: run `./venv/bin/python execution/winbet_email_handler.py test` first, then start monitor under supervisor
