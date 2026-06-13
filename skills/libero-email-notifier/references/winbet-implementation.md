# Implementation Reference — WinBet Email Stack

Queste sono le implementazioni reali, testate in produzione, che vivono in `winbet/execution/`. Servono come riferimento concreto per il pattern descritto in SKILL.md.

## File di riferimento

| File | Ruolo | Note |
|---|---|---|
| `libero_notifier.py` | SMTP/IMAP wrapper | Classe `LiberoNotifier` con sanitize credenziali nei log |
| `winbet_email_handler.py` | Command handler | Parser subject+body, whitelist mittenti, dispatch table |
| `winbet_daily_report.py` | Report giornaliero | Dual format (text+HTML), CLI con `--dry-run`, multi-destinatario |

## Pitfall specifici del progetto WinBet (giugno 2026)

### DB schema reale

```sql
-- matches
match_id, league_id (testo tipo "FIFA World Cup"), home_team, away_team,
match_date, match_time, status, home_score, away_score, created_at, updated_at

-- odds
match_id, bookmaker_id, market_type (1X2|gng|ou25|...), selection_label,
odds_decimal, scraped_at, updated_at

-- surebets
match_id, market_type, selections (JSON), profit_percent, total_implied_prob,
detected_at, notified, status

-- scrape_log
bookmaker_id, league_id, matches_found, odds_found, errors (NULL=ok),
started_at, completed_at
```

### Config winbet_config.json (nested!)

```json
{
  "mode": "DEMO" | "LIVE",
  "scrape": {
    "interval_minutes": 60,
    "bookmakers_enabled": ["snai", "eurobet", ...]
  }
}
```

❌ `cfg.get("interval_minutes")` → None
✅ `cfg.get("scrape", {}).get("interval_minutes")` → 60

### Surebets: JSON selections shape

```json
[{"selection": "1", "label": "Casa", "odds": 7.96, "bookmaker": "eurobet"},
 {"selection": "X", "label": "Pareggio", "odds": 6.22, "bookmaker": "oddsportal"}]
```

Chiave è `selection`/`label`, NON `outcome`. Quando parsate, usate `.get("label", sel.get("selection"))` come fallback.

## Cronjob attivi in produzione

| Job ID | Nome | Schedule |
|---|---|---|
| `49c82947c398` | winbet-autoscraper | every 60m |
| `688e28232eb8` | WinBet SNAI Scraper | `0 * * * *` |
| `0abd69074c12` | WinBet Email Monitor | every 10m |
| `d467f1410c8d` | WinBet Daily Report 8:00 | `0 8 * * *` |

## Indirizzi email

- **Mittente** (sender): `watson.ag@libero.it` (Libero Free)
- **Destinatario report**: `angelo.bruno80@gmail.com` (Gmail, potrebbe finire in Promozioni)
- **Auto-risponditore**: stesso indirizzo del mittente (comandi inviati a se stesso per test)

## Test eseguiti

1. SMTP invio ✅ (test-send roundtrip < 2s)
2. IMAP ricezione ✅ (test-fetch legge 5+ email)
3. Command handler end-to-end ✅ (status → report con 199 partite, 3656 quote)
4. Daily report delivery ✅ (inviato a Gmail ricevuto)
5. Cronjob scheduling ✅ (4 cronjob attivi, tutti `last_status: ok`)
