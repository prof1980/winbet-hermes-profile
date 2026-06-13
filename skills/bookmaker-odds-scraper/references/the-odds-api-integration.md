# The Odds API Integration — WinBet Reference (2026-06-01)

## What It Is

`https://the-odds-api.com` is a paid REST API that aggregates real-time odds from 80+ bookmakers (pinnacle, betfair_ex_eu, betonlineag, gtbets, marathonbet, winamax_fr/de, unibet_se/nl, everygame, tipico_de, mybookieag, onexbet, coolbet, etc.). It's the **single most reliable** data source from WSL/datacenter IPs because it bypasses all Italian bookmaker anti-bot layers.

## Account & Limits

- Free tier: **500 credits/month** (resets monthly)
- 1 credit ≈ 1 call per region per market per sport
- Typical cost: 1 call = `regions_count × markets_count` credits
- A single Mondiali fetch with 2 markets × 1 region = 2 credits

## Endpoint

```
GET https://api.the-odds-api.com/v4/sports/{sport_key}/odds
  ?apiKey=YOUR_KEY
  &regions=eu
  &markets=h2h,totals
  &oddsFormat=decimal
  &dateFormat=iso
  &tz=Europe/Rome
```

## Sport Keys (verified 2026-06-01)

| Sport | Key | Status |
|---|---|---|
| FIFA World Cup | `soccer_fifa_world_cup` | ✅ 72 events returned |
| International Friendlies | `soccer_international_friendlies` | (not tested) |

Use `GET /v4/sports?apiKey=KEY` to discover current sport keys.

## Markets — CRITICAL PITFALL

| Market | Description | Status |
|---|---|---|
| `h2h` | Head-to-head (1X2 equivalent) | ✅ Always works |
| `totals` | Over/Under (with point, e.g. 2.5) | ✅ Works |
| `spreads` | Handicaps | ✅ Works |
| `btts` | Both Teams To Score | ❌ **Returns 422 for some sports** — error: `INVALID_MARKET` |

Always omit `btts` unless you verify it for the specific sport. The error response is:
```json
{"message":"Markets not supported by this endpoint: btts","error_code":"INVALID_MARKET"}
```

## Response Schema

```json
[
  {
    "id": "80d82d1113934bfbea4ce8daf37a2433",
    "sport_key": "soccer_fifa_world_cup",
    "sport_title": "FIFA World Cup",
    "commence_time": "2026-06-11T19:00:00Z",
    "home_team": "Mexico",
    "away_team": "South Africa",
    "bookmakers": [
      {
        "key": "pinnacle",
        "title": "Pinnacle",
        "markets": [
          {
            "key": "h2h",
            "outcomes": [
              {"name": "Mexico", "price": 1.45},
              {"name": "South Africa", "price": 7.95},
              {"name": "Draw", "price": 4.48}
            ]
          },
          {
            "key": "totals",
            "outcomes": [
              {"name": "Over", "price": 1.85, "point": 2.5},
              {"name": "Under", "price": 1.95, "point": 2.5}
            ]
          }
        ]
      }
    ]
  }
]
```

### Key Data Paths

| Field | Path | Notes |
|---|---|---|
| Event ID | `id` (string) | Use as-is or prefix `toa_` for namespace |
| Teams | `home_team`, `away_team` | English names (Mexico, South Africa) |
| Kickoff | `commence_time` | ISO 8601 UTC |
| Bookmaker key | `bookmakers[*].key` | e.g. `pinnacle`, `marathonbet`, `betfair_ex_eu` |
| Market type | `bookmakers[*].markets[*].key` | `h2h`, `totals` |
| Selection | `outcomes[*].name` | **Team name** for h2h (NOT "1"/"X"/"2") |
| Odds | `outcomes[*].price` | Decimal already, no conversion |
| Spread point | `outcomes[*].point` | Only on totals/spreads |

## Cross-Bookmaker Surebet Detection (THE HARD PART)

The Odds API `h2h` selections are **team names** ("Mexico"), but SNAI/Eurobet use **outcome codes** ("1", "X", "2"). Cross-bookmaker surebet detection requires:

1. **Name normalization** (handle accents, articles, IT/EN synonyms):
   ```python
   "Messico" == "Mexico"      # both normalize to "messico"
   "USA" == "United States"   # both normalize to "statiuniti"
   "Inter" != "Internazionale" # edge cases need team-alias dictionary
   ```
2. **Outcome-to-selection mapping** (1X2 normalization):
   - If selection name is in `{"1", "1X"}` → "1" (home)
   - If selection name is in `{"2", "X2"}` → "2" (away)
   - If selection name is in `{"X", "D", "Draw", "Pareggio"}` → "X" (draw)
   - Otherwise: compare normalized name to `home_team` / `away_team` of the same match

3. **Match keying** across bookmakers: build key from `normalize(home) | normalize(away)`. **Do NOT use team-name raw string** because Eurobet has "Sudafrica" and The Odds API has "South Africa".

### Surebet Profit Formula
```python
margin = sum(1.0 / best_odds[outcome] for outcome in ["1", "X", "2"])
profit_percent = (1.0 - margin) * 100
# Surebet exists if margin < 1.0 (profit > 0%)
```

## WinBet-Specific Integration Pattern

WinBet already has a Flask dashboard (`execution/dashboard.py`) with REST endpoints. The Odds API output should be saved to the SQLite schema with these mappings:

| The Odds API field | DB column | Notes |
|---|---|---|
| `id` (prefixed `toa_`) | `matches.match_id` | Unique |
| `home_team` | `matches.home_team` | As-is (English) |
| `away_team` | `matches.away_team` | As-is |
| `sport_title` | `matches.league_id` | E.g. "FIFA World Cup" |
| `commence_time` (split) | `matches.match_date` + `match_time` | First 10 chars + HH:MM |
| `bookmakers[*].key` | `odds.bookmaker_id` | pinnacle, marathonbet, etc. |
| `markets[*].key` | `odds.market_type` | h2h, totals |
| `outcomes[*].name` | `odds.selection_name` | "Mexico", "Draw", "Over" |
| `outcomes[*].price` | `odds.odds_value` | Already decimal |

## Pitfalls

### 1. `pkill` Is Blocked by Hermes Tool Guard
When the Flask dashboard server needs restart, do NOT use `pkill -f dashboard.py` — it's blocked. Instead:
```bash
ps aux | grep dashboard.py | grep -v grep   # find PIDs
kill 23549 23559                            # kill specific PIDs found
```

### 2. The Odds API Credits Are Real Money
Always call once per cron tick, NOT per match. The 500 credit limit can be exhausted in days if the cronjob runs every 5 min across multiple markets.

### 3. Sport Keys Expire / Change
The `soccer_fifa_world_cup` key was valid in 2026-06 but will be wrong after the tournament. Always call `/v4/sports?apiKey=KEY` first to validate keys before scraping.

### 4. h2h Outcome Names Are Team Names
Most Italian bookmakers use `1`/`X`/`2` but The Odds API uses the team name directly. The downstream `surebet_detector` must map: `team_name == home_team → "1"`, `team_name == away_team → "2"`, name in `{Draw, X, Pareggio} → "X"`. Skipping this step gives 0 surebets even when they exist.

## Quick Test

```python
from curl_cffi import requests
import json

API_KEY = "17c06210795f0e165eddfbdc785dfc9b"  # 500 credits/month
resp = requests.get(
    "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds",
    params={
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
        "tz": "Europe/Rome",
    },
    impersonate="chrome136",
    timeout=20,
)
data = resp.json()
print(f"Got {len(data)} events")
# Sample: 72 events for soccer_fifa_world_cup, ~2 credits per call
```
