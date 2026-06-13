# Changelog

Tutte le modifiche rilevanti a questo profilo. Il versioning segue [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-13

### Added
- Distribuzione iniziale del profilo `winbet` per Hermes Agent ≥0.12.0
- `distribution.yaml` con 7 env vars documentate (3 required, 4 optional)
- `SOUL.md` con personalità italiana per analisi quote calcistiche
- `profile.yaml` con descrizione operativa (scraping, surebet detection, alert Telegram)
- `config.yaml` con modello `minimax-m3:cloud` (Ollama Cloud), Telegram come unica piattaforma gateway, toolset `hermes-cli`
- Skill WinBet-specific incluse:
  - `bookmaker-odds-scraper` (SNAI, Eurobet, Goldbet, William Hill, Sisal, Lottomatica, Bet365, OddsPortal)
  - `dedupe-matches-merge` (merge partite duplicate cross-bookmaker)
  - `libero-email-notifier` (SMTP/IMAP bidirezionale per notifiche email)
  - `github-push-with-pat-from-env` (pattern pubblicazione GitHub con PAT da `.env`)
  - `python-project-replication-package` (packaging replicabile del progetto)
- 17 categorie di skill bundled (creative, github, mlops, productivity, research, software-development, ...)
- Compressione contesto attiva (soglia 50% → 20%)
- Memory persistente (2 voci: setup WinBet project + profilo Hermes quirks)
- Licenza MIT

### Note di rilascio
- Necessita `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `OLLAMA_API_KEY` per funzionare
- `THE_ODDS_API_KEY` raccomandato per scraping cross-bookmaker di produzione
- Cron di scraping non pre-attivati (richiede setup esplicito post-install)
- Path del profilo: `~/.hermes/profiles/winbet/` (con `HERMES_HOME` se impostato)
