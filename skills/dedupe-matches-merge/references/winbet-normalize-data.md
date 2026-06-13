# WinBet Normalization Tables

Specific mappings discovered while building the WinBet agent. Use as reference
when adding new bookmakers or running dedupe on existing data.

## League Equivalences (as of June 2026)

| SNAI / Eurobet | The Odds API | Canonical |
|---|---|---|
| Amichevoli Internazionali | (n/a) | Amichevoli Nazionali |
| Amichevoli Nazionali | (n/a) | Amichevoli Nazionali |
| Mondiali 2026 | FIFA World Cup | FIFA World Cup |
| (n/a) | soccer_fifa_world_cup | FIFA World Cup |

The Odds API returns the canonical English name; SNAI and Eurobet use
Italian. Always collapse to the canonical name when merging.

## Team Name Normalization (Italian → English)

These are the pairs that actually appeared in WinBet DB after one scraping cycle.
Add new pairs as they appear. Format: lowercase, no apostrophes, no diacritics.

```python
TEAM_NORMALIZE = {
    "messico": "mexico",
    "sudafrica": "south africa",
    "repubblica di corea": "south korea",
    "corea del sud": "south korea",
    "repubblica ceca": "czech republic",
    "bosnia-erzegovina": "bosnia & herzegovina",
    "stati uniti": "usa",
    "emirati arabi uniti": "united arab emirates",
    "arabia saudita": "saudi arabia",
    "capo verde": "cabo verde",
    "costa d'avorio": "ivory coast",
    "olanda": "netherlands",
    "paesi bassi": "netherlands",
    "nuova zelanda": "new zealand",
    "repubblica centrafricana": "central african republic",
    "repubblica democratica del congo": "dr congo",
    "cambogia u23": "cambodia u23",
    "perù": "peru", "cile": "chile", "haiti": "haiti", "qatar": "qatar",
    "panama": "panama", "scozia": "scotland", "svizzera": "switzerland",
    "turchia": "turkey", "marocco": "morocco", "brasile": "brazil",
    "germania": "germany", "giappone": "japan", "tunisia": "tunisia",
    "algeria": "algeria", "austria": "austria", "colombia": "colombia",
    "ecuador": "ecuador", "svezia": "sweden", "belgio": "belgium",
    "iraq": "iraq", "norvegia": "norway", "giordania": "jordan",
    "croazia": "croatia", "iran": "iran", "uruguay": "uruguay",
    "ghana": "ghana", "senegal": "senegal", "camerun": "cameroon",
    "egitto": "egypt", "filippine": "philippines", "thailandia": "thailand",
    "indonesia": "indonesia", "myanmar": "myanmar", "cambogia": "cambodia",
    "tagikistan": "tajikistan", "armenia": "armenia", "moldova": "moldova",
    "ungheria": "hungary", "kazakistan": "kazakhstan", "angola": "angola",
    "irlanda": "ireland", "galles": "wales", "hong kong": "hong kong",
    "cina": "china", "india": "india", "australia": "australia",
    "spagna": "spain", "italia": "italy", "francia": "france",
    "inghilterra": "england", "portogallo": "portugal", "canada": "canada",
    "uzbekistan": "uzbekistan", "curacao": "curacao",
}
```

## Market Type Normalization

| SNAI/Eurobet raw | The Odds API | Canonical | Notes |
|---|---|---|---|
| 1X2 | h2h | 1X2 | Standard 3-way |
| 1x2 (lowercase) | (n/a) | 1X2 | SNAI uses lowercase |
| GG/NG | (n/a) | GG/NG | Eurobet |
| gol_nogol | (n/a) | GG/NG | SNAI |
| U/O GOAL 2,5 | (n/a) | OU25 | Eurobet (comma) |
| U/O GOAL 2.5 | totals | OU25 | Eurobet (period) |
| over_under | (n/a) | OU25 | SNAI |
| doppia_chance | (n/a) | DC | SNAI |
| market_30562 | (n/a) | HANDICAP | SNAI internal ID |
| h2h_lay | (n/a) | (skip) | Betfair lay bets — exclude from surebet |
| totals | totals | (use as-is) | The Odds API totals |

## Source URLs & Auth Patterns

| Source | Endpoint | Method | Notes |
|---|---|---|---|
| SNAI | `betting-snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0` | curl_cffi chrome136 | Required headers: `Referer`, `Origin`, `bet-locale: it_IT`, `bet-brand: 391`, `user_data` JSON |
| Eurobet | `www.eurobet.it/detail-service/sport-schedule/services/meeting/calcio/{slug}?prematch=1&live=0` | curl_cffi chrome136 | Slugs: `wd-mondiali-calcio`, `wd-amichevoli-nazionali` |
| The Odds API | `api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/events?apiKey=...` | standard requests | ~2 credits/call, 500/month free |

## Bookmaker IDs Seen in DB

```
betfair_ex_eu, betonlineag, coolbet, eurobet, everygame, gtbets,
leovegas_se, marathonbet, mybookieag, onexbet, pinnacle, pmu_fr,
snai, sport888, tipico_de, unibet_fr, unibet_nl, unibet_se,
williamhill, winamax_de, winamax_fr
```

## DB Schema (as observed June 2026)

```sql
matches(id, match_id TEXT UNIQUE, league_id, home_team, away_team,
        match_date, match_time, status, home_score, away_score,
        created_at, updated_at)

odds(id, match_id, bookmaker_id, market_type, selection_name,
     selection_label, odds_value, odds_decimal, scraped_at, updated_at)
-- UNIQUE on (match_id, bookmaker_id, market_type, selection_name)

odds_history(id, match_id, bookmaker_id, market_type, selection_name,
             odds_value, recorded_at)
-- NOTE: no odds_decimal, no selection_label (use the live odds table for those)

surebets(id, match_id, market_type, selections TEXT,  -- JSON string
         profit_percent, total_implied_prob, detected_at, notified, status)

scrape_log(id, bookmaker_id, league_id, matches_found, odds_found,
           errors, started_at, completed_at)
-- NOTE: no `status` column — use errors IS NULL OR errors = '' for success
```

## Pipelines That Worked

1. **SNAI**: `curl_cffi.requests.get(url, headers=..., impersonate='chrome136', timeout=30)` → 0.38s for 10 events
2. **Eurobet**: same pattern, with `?prematch=1&live=0` query params (without them, 404)
3. **The Odds API**: plain `requests.get` works (no TLS fingerprinting)
4. **Surebet detection**: `1/prob_sum < 1.0` check, profit = `(1/prob_sum - 1) * 100`
5. **Merge**: pick canonical = match_id with most odds; transfer with `INSERT OR IGNORE` semantics; keep higher decimal in case of conflict
