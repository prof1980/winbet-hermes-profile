# Changelog

Tutte le modifiche rilevanti a questo profilo. Il versioning segue [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-13

### Added
- Distribuzione iniziale del profilo `winbet` per Hermes Agent ≥0.12.0
- `distribution.yaml` con 7 env vars documentate (3 required, 4 optional)
- Blocco `distribution_owned` esplicito (12 path, inclusi `mcp.json`, `cron/jobs.json`, 5 skill WinBet-specific)
- `mcp.json` vuoto (nessun MCP server esterno richiesto)
- `cron/jobs.json` con 2 schedule template (hourly scrape, daily digest) — `enabled: false` per scelta conservativa
- `SOUL.md` con personalità italiana per analisi quote calcistiche
- `profile.yaml` con descrizione operativa (scraping, surebet detection, alert Telegram)
- `config.yaml` con modello `minimax-m3:cloud` (Ollama Cloud), Telegram come unica piattaforma gateway, toolset `hermes-cli`
- Skill WinBet-specific incluse (dichiarate in `distribution_owned`):
  - `bookmaker-odds-scraper` (SNAI, Eurobet, Goldbet, William Hill, Sisal, Lottomatica, Bet365, OddsPortal)
  - `dedupe-matches-merge` (merge partite duplicate cross-bookmaker)
  - `libero-email-notifier` (SMTP/IMAP bidirezionale per notifiche email)
  - `github-push-with-pat-from-env` (pattern pubblicazione GitHub con PAT da `.env`)
  - `python-project-replication-package` (packaging replicabile del progetto)
- 17 categorie di skill bundled (creative, github, mlops, productivity, research, software-development, ...)
- Compressione contesto attiva (soglia 50% → 20%)
- Memory persistente (2 voci: setup WinBet project + profilo Hermes quirks)
- Licenza MIT
- `.gitignore` con esclusioni per secrets, state, cache, logs, runtime locks, bundled manifest runtime state, pastes, backup

### Note di rilascio
- Necessita `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `OLLAMA_API_KEY` per funzionare
- `THE_ODDS_API_KEY` raccomandato per scraping cross-bookmaker di produzione
- Cron di scraping **NON pre-attivati** (`enabled: false` in `cron/jobs.json`) — richiede setup esplicito post-install con credenziali reali
- Path del profilo: `~/.hermes/profiles/winbet/` (con `HERMES_HOME` se impostato)
- Struttura canonica rispettata: `distribution.yaml` + `SOUL.md` + `config.yaml` + `mcp.json` + `profile.yaml` + `skills/` + `cron/` + `README.md`
