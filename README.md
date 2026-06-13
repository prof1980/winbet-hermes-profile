# WinBet — Hermes Agent Profile

> Agente autonomo di analisi quote calcistiche in italiano. Persona specializzata in scraping bookmaker, rilevamento surebet cross-bookmaker, alert e report via Telegram.

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](distribution.yaml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Hermes](https://img.shields.io/badge/hermes-%3E%3D0.12.0-purple.svg)](https://hermes-agent.nousresearch.com/)

## Cos'è

Questa è una **distribuzione ufficiale Hermes Agent** (profilo `winbet`).
È pensata per essere installata su un'istanza Hermes con:

```bash
hermes profile install prof1980/winbet-hermes-profile
hermes profile use winbet
```

Una volta installata, il profilo:

- parla italiano (con terminologia tecnica quote in inglese)
- è connesso di default a Telegram (serve `TELEGRAM_BOT_TOKEN`)
- usa Ollama Cloud come backend modello (richiede `OLLAMA_API_KEY`)
- include 4 skill WinBet-specific: `bookmaker-odds-scraper`, `dedupe-matches-merge`, `libero-email-notifier`, `github-push-with-pat-from-env`
- eredita 70+ skill bundled dal core Hermes

## Personalità

```
Sei WinBet, un analista autonomo di quote calcistiche. Lavori con precisione matematica.
- Lingua: italiano (terminologia tecnica inglese per le quote)
- Tono: professionale, conciso, orientato ai dati
- Principi: precisione nei calcoli, trasparenza sui margini, avvertenze sul gioco responsabile
- Non sei un consulente finanziario. Ogni analisi è a scopo informativo.
```

Vedi [`SOUL.md`](SOUL.md) per il testo completo.

## Struttura della distribuzione

```
.
├── distribution.yaml     # manifest installabile (env_requires, version, distribution_owned)
├── SOUL.md               # personalità agente
├── profile.yaml          # descrizione profilo (mostrata in `hermes profile list`)
├── config.yaml           # config Hermes (modello, toolset, terminal, memory, ...) — preserved on update
├── mcp.json              # MCP server connections (vuoto = nessun MCP esterno)
├── cron/
│   └── jobs.json         # schedule template (hourly scrape, daily digest)
├── skills/               # 22 categorie, ~71 SKILL.md (auto-caricate)
├── .gitignore            # esclude secrets, state, cache, logs, runtime locks
├── CHANGELOG.md
├── LICENSE               # MIT
└── README.md
```

## Variabili d'ambiente richieste

| Variabile | Obbligatoria | Descrizione |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot Telegram (da @BotFather) per alert e report |
| `TELEGRAM_ALLOWED_USERS` | ✅ | User ID Telegram autorizzati (CSV) |
| `OLLAMA_API_KEY` | ✅ | Ollama Cloud API key (backend LLM) |
| `OLLAMA_BASE_URL` | ❌ | Default: `http://host.docker.internal:11434/v1` |
| `THE_ODDS_API_KEY` | ❌ | Per scraping cross-bookmaker di produzione |
| `LIBERO_SMTP_USER` | ❌ | SMTP per notifiche email |
| `LIBERO_SMTP_PASS` | ❌ | SMTP password per notifiche email |

Tutte le variabili sono dichiarate in [`distribution.yaml`](distribution.yaml) — l'installer
di Hermes le chiede al setup e non ti disturba per quelle già presenti nel tuo `.env`.

## Installazione

### Da GitHub (consigliato)

```bash
hermes profile install prof1980/winbet-hermes-profile
hermes profile use winbet
hermes setup            # wizard: carica env vars, modello, terminale
hermes chat             # dogfood iniziale
```

### Manuale (sviluppo)

```bash
git clone https://github.com/prof1980/winbet-hermes-profile.git
cp -r winbet-hermes-profile/* ~/.hermes/profiles/winbet/
# oppure, per test live:
ln -s $(pwd)/winbet-hermes-profile ~/.hermes/profiles/winbet
hermes profile use winbet
```

## Note sull'uso

- **Aggiornamento distribuzione**: i file marcati come `distribution_owned` in `distribution.yaml` (SOUL.md, config.yaml, mcp.json, skills/ WinBet, cron/jobs.json) vengono **sostituiti** al `hermes profile update`. I dati utente (`memories/`, `sessions/`, `state.db`, `auth.json`, `.env`, `logs/`, `workspace/`, ecc.) sono **preservati**. Per forzare l'override di `config.yaml` usa `hermes profile update --force-config`.
- **Gioco responsabile**: questo agente analizza quote a scopo informativo. Non è un consulente finanziario né un servizio di consulenza scommesse.
- **Costi LLM**: il modello default (`minimax-m3:cloud` via Ollama) ha contesto 524k token. Sessioni lunghe vengono compresse automaticamente (soglia 50% → 20%).
- **Scraping**: la skill `bookmaker-odds-scraper` lavora senza autenticazione su SNAI, Eurobet, Goldbet, William Hill, Sisal, Lottomatica, Bet365, OddsPortal. Rispettare i ToS dei siti.

## Licenza

MIT — vedi [`LICENSE`](LICENSE).
