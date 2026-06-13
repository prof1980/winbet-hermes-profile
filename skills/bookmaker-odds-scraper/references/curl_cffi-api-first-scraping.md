# API-First Scraping via curl_cffi — Real Endpoints

**Context:** Italian bookmakers (SNAI, Eurobet) on WSL2. Playwright headless/non-headless fails due to TLS fingerprint filtering and Cloudflare. The only reliable extraction is `curl_cffi` hitting the **internal REST API** endpoints that the React/Next.js frontend uses.

---

## SNAI — `flutterseatech.it` API

**Base:** `https://betting-snai.flutterseatech.it`
**Working endpoint (Mondiali 2026):**
```
GET /api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0
GET /api/lettura-palinsesto-sport/avvenimento/prematch/v1/eventi-utente?tipologia=0&codiceAvvenimento=0&codiceScommessa={scommessa_id}
```

**Required headers:**
```python
headers = {
    'Referer': 'https://www.snai.it/',
    'Origin': 'https://www.snai.it',
    'bet-locale': 'it_IT',
    'bet-brand': '391',
    'bet-offer': '0',
    'user_data': '{"accountId":null,"token":null,"tokenJWT":null,"locale":"it_IT","loggedIn":false,"channel":62,"brandId":391,"offerId":0,"clientType":"WEB"}',
}
```

**Data paths in response:**
| Field | Path | Note |
|---|---|---|
| Markets | `result.scommessaMap` | codicePalinsesto, codiceAvvenimento, codiceScommessa |
| Odds | `result.infoAggiuntivaMap[].esitoList[*].quota` | **centesimi** → divide by 100 |
| Teams | `result.infoAggiuntivaMap[].descrizioneSquadre` | pipe-delimited "home \| away" |
| Time | `result.infoAggiuntivaMap[].dataAvvenimento` | epoch seconds |

**Market mapping (SNAI codiceScommessa):**
| ID | Market | Display name |
|---|---|---|
| `3` | 1X2 / h2h | Esito Finale (1H) |
| `4` | U/O | Under/Over 2.5 |
| `5` | GG/NG | Gol/NoGol |
| `7` | 1X2 (full) | Esito Finale 3W |

---

## Eurobet — `detail-service` API

**Base:** `https://www.eurobet.it`
**Working endpoint (Mondiali 2026):**
```
GET /detail-service/sport-schedule/services/meeting/{discipline}/{meeting}?prematch=1&live=0
```

**Known meeting slugs:**
| Competition | Slug |
|---|---|
| Mondiali Calcio | `wd-mondiali-calcio` |
| Amichevoli Nazionali | `wd-amichevoli-nazionali` |

**Required headers:**
```python
headers = {
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.eurobet.it/it/scommesse',
    'Origin': 'https://www.eurobet.it',
}
```

**Data paths in response:**
| Field | Path | Note |
|---|---|---|
| Competition name | `result.dataGroupList[*].description` | e.g. "Coppa del Mondo" |
| Events | `result.dataGroupList[*].itemList[*].eventInfo` | homeTeam, awayTeam, eventData |
| Event time | `eventData` | **milliseconds since epoch** |
| Markets | `result.dataGroupList[*].itemList[*].betGroupList[*]` | codiceScommessa, descrizione |
| Market selections | `betGroupList[*].oddGroupList[*].oddList[*]` | descrizione, oddValue |
| Odds | `oddValue` | **centesimi** → divide by 100 |

**Key fields per oddList item:**
- `addInfo.oddId` → selection ID
- `addInfo.descrizioneEvento` → description (may include handicap, e.g. "Under (-0,5)")
- `oddValue` → **centesimi**
- `addInfo.stato` → `1` = active, `2` = suspended

---

## The Odds API v4

**Base:** `https://api.the-odds-api.com/v4`
**Best for:** WSL/datacenter environments — no TLS fingerprint blocks, no anti-bot.

**Endpoint:**
```
GET /sports/{sport_key}/odds?regions={regions}&markets={markets}&oddsFormat=decimal&apiKey={key}
```

**Working parameters (Mondiali 2026):**
```python
params = {
    'sports': 'soccer_fifa_world_cup',
    'regions': 'eu',
    'markets': 'h2h,totals',   # btts not always supported
    'oddsFormat': 'decimal',
    'apiKey': os.environ['ODDS_API_KEY'],
}
```

**Data paths in response:**
| Field | Path | Note |
|---|---|---|
| Events | `list` body (root array) | Each item is one event |
| Home team | `home_team` | Raw name (EN spelling: "Mexico") |
| Away team | `away_team` | Raw name (EN spelling: "South Korea") |
| Start time | `commence_time` | ISO 8601 string |
| Bookmakers | `bookmakers[*]` | one entry per bookmaker |
| Odds | `bookmakers[*].markets['h2j].outcomes[*]` | Each outcome has `name`, `price` |

**CRITICAL: Selection names in `h2h` market are team names (EN), NOT "1/X/2". E.g. `{name: "Mexico", price: 1.45}` — NOT `{name: "1", price: 1.45}`.**

For surebet detection against Italian bookmaker sources (which use "1/X/2"), normalize with `normalize_name()` that maps EN→IT spellings (see the pipeline skill).

---

## General Architecture Pattern

When building a production pipeline that combines these sources:

1. **Primary source:** The Odds API (reliable, low-latency, no anti-bot).
2. **Secondary source:** Eurobet API (fast, structured, no auth).
3. **Tertiary source:** SNAI API (Italian odds, requires specific headers).
4. **Browser scraping** (Playwright/DOM): Use only as last resort, always inside TigerVNC+OpenBox or with `--no-headless` + Xvfb on WSL.

For the full orchestration pattern (unified scraper, surebet engine, dashboard, cronjob), see the `winbet-odds-pipeline` skill.
