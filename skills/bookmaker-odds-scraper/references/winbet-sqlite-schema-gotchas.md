# WinBet SQLite Schema — Column Names Confirmed via PRAGMA (2026-06-08)

## Why this exists

The WinBet DB schema has trap names that look generic but aren't — they caused repeated
"no such column" errors during dashboard refactors and SNAI scraper fixes. This file
records the **actual** column names from `PRAGMA table_info(<table>)` so future agents
stop guessing and start querying correctly.

## Tables and columns (verified live)

### `matches`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | autoincrement PK |
| `match_id` | TEXT | External ID, e.g. `snai-36241-6645`, `eb_36241_14693`, `toa_<hash>` |
| `league_id` | TEXT | **The human-readable league name lives here** ("Amichevoli Internazionali", "FIFA World Cup"). NOT a separate `league` column. |
| `home_team` | TEXT | |
| `away_team` | TEXT | |
| `match_date` | TEXT | ISO date `YYYY-MM-DD` |
| `match_time` | TEXT | `HH:MM` (24h) |
| `status` | TEXT | `scheduled`, `finished`, etc. |
| `home_score`, `away_score` | INTEGER | nullable until match ends |
| `created_at`, `updated_at` | TEXT | ISO 8601 UTC |

### `odds`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | PK |
| `match_id` | TEXT | FK to `matches.match_id` |
| `bookmaker_id` | TEXT | e.g. `snai`, `eurobet`, `pinnacle` |
| `market_type` | TEXT | `1X2`, `1x2` (lowercase from SNAI), `h2h`, `totals`, `over_under`, `gol_nogol`, `doppia_chance`, `GG/NG` (mixed from Eurobet) |
| `selection_name` | TEXT | `1`, `X`, `2`, `Over`, `Under`, `GOAL`, `NOGOAL`, `Mexico`, `Draw` |
| `selection_label` | TEXT | Human label (`Casa`, `Trasferta`, `Pareggio`, `Over 1.5`, `Mexico`) |
| `odds_value` | REAL | **Raw value** (centesimi for SNAI/Eurobet) |
| `odds_decimal` | REAL | **Converted to decimal** (`odds_value / 100` for SNAI/Eurobet; already decimal for The Odds API) |
| `scraped_at`, `updated_at` | TEXT | ISO 8601 UTC |

### `surebets`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | PK |
| `match_id` | TEXT | FK |
| `market_type` | TEXT | |
| `selections` | TEXT | **JSON blob** — `[{selection, label, odds, bookmaker}, ...]` |
| `profit_percent` | REAL | e.g. `33.72` |
| `total_implied_prob` | REAL | Sum of 1/odds, <1 means arb |
| `detected_at` | TEXT | ISO 8601 |
| `notified` | INTEGER | 0/1 flag |
| `status` | TEXT | `active` / `expired` |

### `scrape_log`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | PK |
| `bookmaker_id` | TEXT | |
| `league_id` | TEXT | or `'ALL'` for full-sport scrapes |
| `matches_found` | INTEGER | |
| `odds_found` | INTEGER | |
| `errors` | TEXT | **No `status` column** — success = `errors IS NULL OR errors = ''` |
| `started_at` | TEXT | |
| `completed_at` | TEXT | **Not `scraped_at`** |

### `odds_history`, `notifications`
Standard append-only tables; column names match the obvious English.

## Common gotchas

1. **`league` doesn't exist** — the only league column is `league_id` on `matches`.
   Some scripts (including earlier WinBet code) joined on `WHERE league = ?` and
   silently returned 0 rows. Always filter on `league_id`.

2. **`outcome` is not a column on `odds`** — the field is `selection_name` and
   `selection_label`. The earlier winbet_email_handler used `outcome` and got
   empty results until patched to fall back: `sel.get("label", sel.get("selection", sel.get("outcome", "?")))`.

3. **`odds_value` vs `odds_decimal`** — for SNAI and Eurobet, `odds_value` is
   in centesimi (1.18 → 118) and `odds_decimal` is the divided value. For The
   Odds API, both are equal (already decimal). **Always prefer `odds_decimal`
   in display code** unless you specifically need the raw source value.

4. **`scrape_log` has no `status` column** — use `errors IS NULL OR errors = ''`
   for success. Several scrapers tried `INSERT ... status` and failed.

5. **`scrape_log.completed_at`** — the timestamp is `completed_at`, not
   `scraped_at`. Queries like `MAX(scraped_at)` return nothing.

6. **`scraped_at` is on `odds`**, not on `matches` — to find "odds updated in
   the last hour" filter on `odds.scraped_at > datetime('now', '-1 hour')`.

7. **`surebets.selections` is a JSON string** — always `json.loads()` before
   iterating, and wrap in try/except (older rows may have malformed JSON).

## Right vs wrong query patterns

### "Show me today's surebets" — RIGHT
```python
c.execute("""
    SELECT s.profit_percent, s.market_type, s.selections,
           m.home_team, m.away_team, m.match_date
    FROM surebets s
    JOIN matches m ON s.match_id = m.match_id
    WHERE s.profit_percent >= 1.0
    ORDER BY s.profit_percent DESC LIMIT 10
""")
for profit, market, sels_json, home, away, date in c.fetchall():
    sels = json.loads(sels_json)
    for s in sels:
        bk = s["bookmaker"]
        oc = s.get("label", s.get("selection", "?"))
        od = s["odds"]
```

### "Show me today's surebets" — WRONG (silently broken)
```python
c.execute("""
    SELECT s.profit_percent, s.market_type, s.bookmaker_a, s.bookmaker_b,
           s.outcome_a, s.outcome_b, s.odds_a, s.odds_b
    FROM surebets s ...
""")
# → sqlite3.OperationalError: no such column: s.bookmaker_a
```

### "Find matches in a league" — RIGHT
```python
c.execute("SELECT DISTINCT league_id FROM matches WHERE LOWER(league_id) LIKE ?", (f"%{q.lower()}%",))
```

### "Find matches in a league" — WRONG
```python
c.execute("SELECT ... WHERE LOWER(league) LIKE ?", ...)
# → sqlite3.OperationalError: no such column: league
```

### "Bookmaker activity in last hour" — RIGHT
```python
c.execute("""
    SELECT bookmaker_id, COUNT(DISTINCT match_id), COUNT(*)
    FROM odds
    WHERE scraped_at > datetime('now', '-1 hour')
    GROUP BY bookmaker_id
""")
```

### "Compare odds across bookmakers for one match" — see pitfall #10 in SKILL.md
The `GROUP BY market_type, selection_name` pattern drops all but the best bookmaker.
For a comparison UI you need every row + a Python-side best annotation.

## Flask `all_bookmakers` response pattern

The dashboard endpoint `/api/matches/<league_id>` should return each selection
with all bookmakers, not just the best:

```python
# In api_matches()
c.execute("""
    SELECT bookmaker_id, market_type, selection_name, selection_label, odds_decimal
    FROM odds WHERE match_id = ?
    ORDER BY market_type, selection_name, odds_decimal DESC
""", (match_id,))
all_odds = c.fetchall()

best_per_sel = {}
sel_map = {}
for o in all_odds:
    key = (o["market_type"], o["selection_name"])
    if key not in best_per_sel or o["odds_decimal"] > best_per_sel[key]["odds"]:
        best_per_sel[key] = {"odds": o["odds_decimal"], "bookmaker": o["bookmaker_id"]}
    if key not in sel_map:
        sel_map[key] = {"market_type": o["market_type"], "selection_name": o["selection_name"],
                        "selection_label": o["selection_label"], "all_bookmakers": []}
    sel_map[key]["all_bookmakers"].append({"bookmaker": o["bookmaker_id"], "odds": o["odds_decimal"]})
```

Then the JSON includes both the best for legacy callers AND `all_bookmakers` for
the new table UI:
```json
{
  "selection": "1",
  "odds": 1.16,
  "bookmaker": "snai",
  "all_bookmakers": [
    {"bookmaker": "snai", "odds": 1.16},
    {"bookmaker": "eurobet", "odds": 1.18}
  ]
}
```

The template's `renderMatches()` then iterates `sel.all_bookmakers`, applies
the bookmaker filter, and renders one `<td>` per active bookmaker with `★` on the best.
