---
name: bookmaker-odds-scraper
description: >
  Scrape betting odds from Italian and international bookmaker websites (SNAI,
  Eurobet, Goldbet, William Hill, Sisal, Lottomatica, Bet365, OddsPortal) without
  authentication. Uses multi-strategy approach: API interception, DOM parsing, and
  WebSocket monitoring. Supports discovery mode and multi-bookmaker comparison.
  Use when the user asks about betting odds, quote scommesse, or odds comparison.
---

# Bookmaker Odds Scraper

Scrape and compare betting odds from Italian and international bookmakers using a multi-strategy approach (API interception, DOM parsing, WebSocket monitoring). No authentication required.

## Prerequisites

1. **`uv` package manager**: Read the `uv` skill (`C:\Users\angel\.gemini\config\plugins\science\skills\uv\SKILL.md`) and follow its Setup instructions to ensure `uv` is installed and on PATH.

2. **Playwright browsers**: Chromium must be installed for headless browser automation:
   ```bash
   playwright install chromium
   ```

3. **First-run note**: The first `uv run` invocation will automatically install all Python dependencies defined in the project. No manual `pip install` is needed.

## Core Rules

- **ALWAYS** use the provided utility script `scripts/bookmaker_scraper.py` for all scraping operations.
- **NEVER** use `curl`, `wget`, or custom HTTP requests directly against bookmaker sites — the script handles anti-bot mitigations, rate limiting, and data normalization.
- The `--output` flag is **REQUIRED** for every subcommand. All results are written to the specified JSON file.
- **Rate limiting**: respect the anti-bot delays configured per bookmaker in `bookmakers.json`. Do not reduce or bypass them.
- **Legal notice**: Scraping bookmaker websites may violate their Terms of Service. The user assumes full responsibility for how this tool is used. See the [Legal Disclaimer](#legal-disclaimer) section.

## Quick Start

```bash
# List all configured bookmakers and their supported strategies
uv run scripts/bookmaker_scraper.py list-bookmakers --output /tmp/bookmakers.json

# Scrape SNAI Serie A odds
uv run scripts/bookmaker_scraper.py scrape --bookmaker snai --sport calcio --competition serie-a --output /tmp/snai_odds.json
```

## Subcommands

### 1. `list-bookmakers` — List configured bookmakers

Returns all configured bookmakers with their supported strategies, difficulty levels, and available sports/competitions.

```bash
uv run scripts/bookmaker_scraper.py list-bookmakers --output /tmp/bookmakers.json
```

**Output**: JSON array of bookmaker configurations including name, key, strategies, and supported competitions.

---

### 2. `scrape` — Scrape odds from a specific bookmaker

Scrape current betting odds from a single bookmaker for a given sport and competition. The script automatically selects the best available strategy (API interception → DOM parsing → WebSocket monitoring).

```bash
# SNAI Serie A
uv run scripts/bookmaker_scraper.py scrape \
  --bookmaker snai \
  --sport calcio \
  --competition serie-a \
  --output /tmp/snai.json

# Eurobet Champions League
uv run scripts/bookmaker_scraper.py scrape \
  --bookmaker eurobet \
  --sport calcio \
  --competition champions-league \
  --output /tmp/eurobet.json

# OddsPortal (aggregator — returns odds from multiple bookmakers in one call)
uv run scripts/bookmaker_scraper.py scrape \
  --bookmaker oddsportal \
  --sport calcio \
  --competition serie-a \
  --output /tmp/oddsportal.json

# With visible browser for debugging
uv run scripts/bookmaker_scraper.py scrape \
  --bookmaker snai \
  --sport calcio \
  --no-headless \
  --output /tmp/debug.json
```

**Output**: JSON file containing a `ScrapeResult` object (see [Output Schema](#output-schema)).

---

### 3. `discover` — Discover API endpoints and data patterns

Runs a passive reconnaissance pass on a bookmaker's website to discover API endpoints, XHR/fetch calls, WebSocket connections, and DOM structure patterns. Useful for initial setup or when a bookmaker changes its frontend.

```bash
# Discover SNAI endpoints for calcio
uv run scripts/bookmaker_scraper.py discover \
  --bookmaker snai \
  --sport calcio \
  --output /tmp/snai_endpoints.json
```

**Output**: JSON file with discovered endpoints, request/response schemas, CSS selectors, and recommended scraping strategy.

---

### 4. `compare` — Compare odds across bookmakers

Scrape odds from multiple bookmakers for the same sport/competition and produce a side-by-side comparison, highlighting the best odds per selection.

```bash
uv run scripts/bookmaker_scraper.py compare \
  --bookmakers snai,eurobet,goldbet \
  --sport calcio \
  --competition serie-a \
  --output /tmp/comparison.json
```

**Output**: JSON file with matched events across bookmakers, best-odds highlighting, and margin calculations.

## Output Schema

The `scrape` subcommand produces a `ScrapeResult` JSON object with the following structure:

```json
{
  "bookmaker": "snai",
  "sport": "calcio",
  "competition": "serie-a",
  "scraped_at": "2026-05-25T21:00:00+02:00",
  "strategy_used": "api_interception",
  "events": [
    {
      "id": "evt_001",
      "home_team": "Juventus",
      "inter_team": "Inter",
      "event_date": "2026-05-26T20:45:00+02:00",
      "league": "Serie A",
      "markets": [
        {
          "name": "1X2",
          "type": "match_result",
          "selections": [
            {
              "name": "1",
              "label": "Juventus",
              "odds": 2.45
            },
            {
              "name": "X",
              "label": "Draw",
              "odds": 3.10
            },
            {
              "name": "2",
              "label": "Inter",
              "odds": 2.90
            }
          ]
        }
      ]
    }
  ],
  "metadata": {
    "total_events": 10,
    "total_markets": 10,
    "scrape_duration_seconds": 12.5,
    "errors": []
  }
}
```

### Schema Definitions

| Field | Type | Description |
|---|---|---|
| `bookmaker` | `string` | Bookmaker key used for scraping |
| `sport` | `string` | Sport category |
| `competition` | `string` | Competition/league key |
| `scraped_at` | `string` (ISO 8601) | Timestamp of the scrape |
| `strategy_used` | `string` | Strategy that succeeded (`api_interception`, `dom_parsing`, `websocket`) |
| `events` | `Event[]` | Array of sporting events with odds |
| `metadata` | `object` | Scrape statistics and any errors |

**Event**:

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique event identifier |
| `home_team` | `string` | Home team name |
| `away_team` | `string` | Away team name |
| `event_date` | `string` (ISO 8601) | Scheduled kickoff date/time |
| `league` | `string` | Human-readable league name |
| `markets` | `Market[]` | Available betting markets |

**Market**:

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Market display name (e.g., `1X2`, `Over/Under 2.5`) |
| `type` | `string` | Normalized market type identifier |
| `selections` | `Selection[]` | Available selections with odds |

**Selection**:

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Selection key (e.g., `1`, `X`, `2`, `Over`, `Under`) |
| `label` | `string` | Human-readable label |
| `odds` | `number` | Decimal odds |

## Supported Bookmakers

| Key | Name | Strategies | Difficulty |
|---|---|---|---|
| `snai` | SNAI | API interception, DOM parsing | 🟢 Easy |
| `eurobet` | Eurobet | **Internal API** (preferred), DOM parsing | 🟢 Easy |
| `goldbet` | Goldbet | DOM parsing | 🟡 Medium |
| `williamhill` | William Hill | API interception | 🟡 Medium |
| `sisal` | Sisal | API interception, DOM parsing | 🟡 Medium |
| `lottomatica` | Lottomatica | API interception | 🟡 Medium |
| `bet365` | Bet365 | WebSocket monitoring | 🔴 Hard |
| `oddsportal` | OddsPortal | DOM parsing (aggregator) | 🟡 Medium |
| `the_odds_api` | the-odds-api.com (multi-bookmaker aggregator) | REST v4 | 🟢 Easy |

> **Note**: Bet365 uses aggressive anti-bot protections and WebSocket-based data delivery. Expect higher failure rates and longer scrape times.

> **Aggregator alternative**: `the-odds-api.com` returns odds from 80+ bookmakers (pinnacle, betfair_ex_eu, marathonbet, etc.) in a single REST call. Free tier 500 credits/month. See `references/the-odds-api-integration.md`.

## Supported Competitions (Calcio)

| Key | Description |
|---|---|
| `serie-a` | Serie A (Italy) |
| `serie-b` | Serie B (Italy) |
| `champions-league` | UEFA Champions League |
| `europa-league` | UEFA Europa League |
| `conference-league` | UEFA Conference League |
| `premier-league` | Premier League (England) |
| `la-liga` | La Liga (Spain) |
| `bundesliga` | Bundesliga (Germany) |
| `ligue-1` | Ligue 1 (France) |
| `world-cup` | FIFA World Cup |
| `euro` | UEFA European Championship |

## Adding New Bookmakers

To add support for a new bookmaker:

1. **Run discovery** against the target site to identify endpoints and DOM structure:
   ```bash
   uv run scripts/bookmaker_scraper.py discover --bookmaker <new-key> --sport calcio --output /tmp/discovery.json
   ```

2. **Add an entry** to `bookmakers.json` with:
   - `key`: lowercase identifier (e.g., `betfair`)
   - `name`: display name
   - `base_url`: the bookmaker's odds page URL
   - `strategies`: ordered list of strategies to try (`api_interception`, `dom_parsing`, `websocket`)
   - `selectors`: CSS selectors for events, markets, and odds elements
   - `api_patterns`: URL patterns for XHR/fetch interception (if applicable)
   - `delays`: rate-limiting configuration (`page_load_wait`, `between_requests`)

3. **Test** with a small scrape:
   ```bash
   uv run scripts/bookmaker_scraper.py scrape --bookmaker <new-key> --sport calcio --competition serie-a --no-headless --output /tmp/test.json
   ```

4. **Iterate** on selectors and strategies until results are consistent.

## Troubleshooting

For detailed troubleshooting guidance, see `references/troubleshooting.md`.

For **real-world anti-bot diagnostics** from headless/WSL environments (SNAI TLS sinkhole, Cloudflare challenge loops, SPA placeholder data), see `references/bookmaker-anti-bot-notes.md`.

For the specific scenario where the user demands non-headless scraping on WSL and what actually happens (xvfb, WSLg, visible browser outcomes), see `references/wsl-browser-reality.md`.

For **the-odds-api.com** integration (sport keys, market pitfalls like `btts` 422 error, cross-bookmaker h2h outcome normalization with team-name → 1X2 mapping, WinBet SQLite mapping), see `references/the-odds-api-integration.md`.

For **WinBet SQLite schema** (actual column names, the `league_id` vs `league` trap, `odds_value` vs `odds_decimal`, `scrape_log` no-status column, the `all_bookmakers` Flask response pattern for the comparison view), see `references/winbet-sqlite-schema-gotchas.md`.

For **SNAI `codiceManifestazione` mapping** (the fact that the API returns numeric codes with no public lookup endpoint, plus the static-dict pattern and a discovery script to find new codes as SNAI rotates its catalog), see `references/snai-competition-code-mapping.md` and `scripts/discover_snai_codes.py`.

Common quick fixes:
- **No results?** Run `discover` to check if endpoints have changed.
- **Blocked by CAPTCHA?** Try `--no-headless` and increase delays.
- **Timeout?** Increase `page_load_wait` in `bookmakers.json`.

## Pitfalls

### 4. Italian Bookmakers from WSL / Datacenter IPs — TLS Fingerprint Blocks

When running from a WSL2 container or any datacenter IP against Italian bookmakers, expect failures at the **TLS/transport layer** that Playwright stealth cannot bypass. However, `curl_cffi` TLS impersonation *can* bypass these blocks for some targets.

| Bookmaker | Headless Playwright | curl_cffi TLS impersonation | Notes |
|---|---|---|---|
| **SNAI** | ❌ ERR_HTTP2 | ✅ **Working** | `flutterseatech.it` backend API reachable with `impersonate='chrome136'` |
| **Eurobet** | ❌ Cloudflare loop | ⚠️ SPA — needs Playwright + xvfb | Static HTML has no `__NEXT_DATA__`; non-headless + xvfb captures Next.js SSR payload |
| **Goldbet** | ❌ Cloudflare | ❌ Same as Eurobet | |
| **William Hill** | ❌ Heavy anti-bot | ❌ Not tested with curl_cffi | Likely similar to Eurobet |
| **OddsPortal** | ❌ Placeholder DOM | ❌ Pure SPA | Real odds loaded via JS `fetch()` after hydration |
| **the-odds-api.com** | N/A (REST) | ✅ **Working** | Aggregator: 80+ bookmakers via single endpoint. Use when Italian bookmakers blocked. |

**What works for SNAI (confirmed 2026-05-31):**
```python
from curl_cffi import requests
resp = requests.get(
    'https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0',
    impersonate='chrome136',
    headers={
        'Referer': 'https://www.snai.it/',
        'Origin': 'https://www.snai.it',
        'bet-locale': 'it_IT',
        'bet-brand': '391',
        'bet-offer': '0',
        'user_data': '{"accountId":null,"token":null,"tokenJWT":null,"locale":"it_IT","loggedIn":false,"channel":62,"brandId":391,"offerId":0,"clientType":"WEB"}',
    },
    timeout=20,
)
# → 200 OK, ~670 KB JSON with real odds (10–50 events)
```

**Key data paths in SNAI response:**
- `scommessaMap` — market definitions (codicePalinsesto, codiceAvvenimento, codiceScommessa)
- `infoAggiuntivaMap` — **actual odds** under `esitoList[*]['quota']` (centesimi, divide by 100)
- Market mapping: `3` = 1X2 (Esito Finale), `4` = Under/Over 2.5, `5` = Gol/NoGol

**What works for Eurobet (confirmed 2026-05-31):**

Eurobet has **two distinct data paths**. The right choice depends on whether the internal API is reachable.

**Path A: API-first (preferred, fastest, most reliable)**

Eurobet serves structured JSON via `/detail-service/sport-schedule/services/meeting/{discipline}/{meeting}?prematch=1&live=0`. This endpoint is **not** protected by Cloudflare — it only requires TLS impersonation via `curl_cffi`.

```python
from curl_cffi import requests
resp = requests.get(
    'https://www.eurobet.it/detail-service/sport-schedule/services/meeting/calcio/wd-mondiali-calcio?prematch=1&live=0',
    headers={
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.eurobet.it/it/scommesse',
        'Origin': 'https://www.eurobet.it',
    },
    impersonate='chrome136',
    timeout=20,
)
# → 200 OK, ~150 KB JSON, 20-40 events with full markets
```

**Key data paths in Eurobet API response:**
- `result.dataGroupList[*].itemList[*].eventInfo` — event metadata (teams, competition, kickoff)
- `result.dataGroupList[*].itemList[*].betGroupList[*].oddGroupList[*]` — markets and odds
- Odds are in **centesimi** (`oddValue` 142 = 1.42)
- Start time is **milliseconds since epoch** (`eventData` 1781204400000)

See `references/eurobet-api-endpoints.md` for the complete endpoint catalog, response schema, and meeting-slug discovery procedure.

**Path B: Next.js SSR fallback (slower, only if API blocked)**

If the API endpoint returns non-1 code or the meeting slug is unknown, fall back to Playwright non-headless with Xvfb to capture the Next.js `__NEXT_DATA__` payload embedded in the HTML.

- Standard Playwright headless → 0 events (Cloudflare challenge)
- Playwright **non-headless** with **Xvfb** (`DISPLAY=:99`) → captures `__NEXT_DATA__` Next.js SSR payload
- The payload is a large JSON embedded in the HTML; parse it for `props.pageProps.competitionEvents.events`

**Do not waste time tuning delays or stealth scripts alone.** The real fix is at the TLS layer (curl_cffi) or the rendering layer (non-headless + xvfb), not in wait times or user-agent rotation.

### 5. Non-Headless on WSL — The Display Problem

The user may demand `--no-headless` (visible browser) believing it will bypass anti-bot. In a WSL2 environment this is **almost always impossible** without a display server. Observed outcomes:

| Environment | `--no-headless` result | Fix |
|---|---|---|
| WSL2 without WSLg | Browser launches invisible, page loads but still 0 events (anti-bot unaffected) | Install WSLg or use `xvfb-run` (see below) |
| WSL2 with WSLg | Browser window appears on Windows host; still 0 events from Italian bookmakers (IP/datacenter block) | None; switch to `the-odds-api.com` |
| Native Windows + Chrome | May work for some bookmakers (e.g. Eurobet) after cookie challenge; still fails for SNAI (TLS sinkhole) | Use `the-odds-api.com` for SNAI |

**Key insight**: `--no-headless` does NOT change the IP address or the TLS fingerprint. It only helps with Cloudflare JavaScript challenges that detect `navigator.webdriver`. In the SNAI case, the failure is at the TCP/TLS layer — headless vs visible is irrelevant.

**If the user insists on non-headless on WSL:**

1. **Check WSLg availability** (`ls /mnt/wslg/`). If present, the browser window will render on the Windows host automatically.
2. **If WSLg is missing**, `xvfb-run` can simulate a virtual display so Playwright doesn't crash:
   ```bash
   xvfb-run --server-args="-screen 0 1920x1080x24" \
     uv run scripts/bookmaker_scraper.py scrape \
     --bookmaker eurobet --sport calcio --no-headless --output /tmp/out.json
   ```
   Even with xvfb, the same anti-bot blocks apply — it only prevents the "no display" crash.
3. **TigerVNC + OpenBox** for a full virtual desktop with real mouse/keyboard events. This is the only WSL configuration that has a realistic chance of solving JavaScript challenges. See `references/wsl-browser-reality.md` for the full setup.

**Recommendation**: when the user says "use non-headless", first explain that WSL lacks a display by default, and that the real block is IP/TLS, not headless detection. Offer `the-odds-api.com` as the only reliable data source from WSL.

### 6. Cross-Bookmaker Surebet Detection Requires Name Normalization

When detecting surebets across Italian bookmakers (which use `1`/`X`/`2` outcome codes) and The Odds API (which uses team names like `"Mexico"`, `"Draw"`), you MUST normalize before comparison:

1. **Team names** — IT/EN synonyms: Mexico→Messico, USA→StatiUniti, South Africa→Sudafrica, South Korea→Corea del Sud. Strip diacritics via `unicodedata.normalize("NFKD", ...)`.
2. **Outcome codes** — Map h2h `outcomes[*].name` to `"1"`/`"X"`/`"2"` by comparing normalized name to the match's `home_team`/`away_team`, OR by checking if the name is in `{Draw, X, Pareggio}`.
3. **Match keying** — Build `normalize(home) | normalize(away)` as the cross-bookmaker key. NEVER use raw strings.

Without these steps, 0 surebets are detected even when 50+ exist in the data. The user's 1-hour session was lost to this exact bug.

### 7. The Odds API `btts` Market Returns 422

The Both Teams To Score (`btts`) market is NOT supported by the Soccer World Cup endpoint. Calling it returns `INVALID_MARKET` 422. Always use `h2h` + `totals` only. See `references/the-odds-api-integration.md` for the full list of safe markets.

### 8. Hermes Tool Guard Blocks `pkill` / `kill` Without Verified PID

When the WinBet Flask dashboard server (port 8080) needs restart after a template change, do NOT use `pkill -f dashboard.py` — Hermes blocks it as a "destructive action". Instead:
```bash
ps aux | grep dashboard.py | grep -v grep   # find PIDs first
kill 23549 23559                            # kill specific PIDs only
```
Or use `process(action='kill', session_id=...)` for Hermes-tracked background processes.

### 9. Existing Flask Infrastructure May Be Already Running

Before starting a new server, check if one is already bound to the port:
```bash
ss -tlnp 2>/dev/null | grep ":8080"
# If a python process is listed, it owns the port — find it via /proc/<pid>/cwd
```
WinBet already has `execution/dashboard.py` running on port 8080. Modifying `templates/index.html` does NOT auto-reload — Flask must be restarted to pick up template changes (unless running with `debug=True`).

### 10. SQL Aggregation Anti-Pattern for Odds Comparison Views

**Wrong** (returns only the best bookmaker per selection — UI shows just one bookmaker per cell):
```sql
SELECT market_type, selection_name, MIN(odds_value) as best_odds,
       (SELECT bookmaker_id FROM odds
        WHERE match_id = ? AND market_type = o.market_type
          AND selection_name = o.selection_name
        ORDER BY odds_value DESC LIMIT 1) as best_bookmaker
FROM odds o
WHERE match_id = ?
GROUP BY market_type, selection_name
```

**Right** (returns ALL bookmakers per selection — UI can show full table with `★` on best):
```sql
SELECT bookmaker_id, market_type, selection_name, selection_label, odds_decimal
FROM odds
WHERE match_id = ?
ORDER BY market_type, selection_name, odds_decimal DESC
-- Then in Python: for each (market, selection) group, mark max(odds) as best.
```

The grouping version is a classic mistake when porting SQL to comparison UIs. The right design: return all rows, do the `★ best` annotation in Python where you can also build `all_bookmakers: [{bk, odds}, ...]` for template rendering. See `references/winbet-sqlite-schema-gotchas.md` for the full WinBet schema and the `all_bookmakers` Flask response pattern.

### 11. Opaque Source Codes (SNAI `codiceManifestazione` etc.) Have No Public Lookup

SNAI's `flutterseatech.it` API returns `codiceManifestazione` (numeric, e.g. `765`) but **no human-readable league name**. Probing `/manifestazione/{code}`, `/manifestazioni`, `/palinsesto/prematch/v1/manifestazioni`, `/calcio`, `/categorie` all return 404. The site has no public league-list endpoint.

**Solution**: maintain a static dict mapping `(codiceDisciplina, codiceManifestazione) → "Leggibile"`, with a `resolve_competition_name()` fallback that returns `"Disciplina X (manifestazione Y)"` for unknown codes so they still show up in the UI. Update the dict as new leagues are observed in the wild.

```python
SNAI_COMPETITION_MAP = {
    (1, 765): "Amichevoli Internazionali",
    (1, 768): "Serie A",
    (1, 770): "Champions League",
    # ...
}
def resolve_competition_name(discipline_code, competition_code):
    return SNAI_COMPETITION_MAP.get((discipline_code, competition_code),
        f"Calcio (manifestazione {competition_code})" if discipline_code == 1 else "")
```

When a new code appears in the DB (e.g. `(1, 999) → "Calcio (manifestazione 999)"`), you can see it needs labeling without breaking the UI. See `references/snai-competition-code-mapping.md` for the discovery script and the full code→name table.

### 2. OddsPortal "Events" Are Not Real Data

If `dom_parse` returns events from OddsPortal but the matches are from minor leagues (e.g., Cobresal vs Nublense) and markets are empty, you are reading the static SEO shell — not the real odds. Switch to `the-odds-api.com` or reverse-engineer the internal API endpoints via CDP (`Network.enable`).

### 3. undetected-chromedriver Does Not Work on Python 3.12

As of 2026-05, `undetected-chromedriver` fails on Python 3.12 because it imports `distutils.version.LooseVersion`, which was removed in Python 3.12. Do not attempt this as a workaround.

### 4. Discovery Mode Crashes on Large JSON Bodies

`cmd_discover` calls `_truncate(r["body"])` where `r["body"]` is a dict. The current `_truncate` implementation round-trips through `json.dumps` then string-slices, which often produces malformed JSON and crashes with `JSONDecodeError`. A safer `_truncate` would check if the input is already a dict/list and deep-truncate strings inside it.

## Recommended Architecture for Production

| Option | Description | Required |
|---|---|---|
| `--output FILE` | Path to write JSON results | ✅ Yes (all subcommands) |
| `--bookmaker NAME` | Bookmaker key (e.g. snai, eurobet) | ✅ Yes (`scrape`, `discover`) |
| `--bookmakers A,B,C` | Comma-separated bookmaker keys | ✅ Yes (`compare`) |
| `--sport SPORT` | Sport category (default: `calcio`) | No |
| `--competition COMP` | Competition key (e.g., `serie-a`) | No |
| `--headless / --no-headless` | Run browser in headless mode (default) or visible | No |

## Integration with WinBet / Data Pipeline

When this skill is used inside a **WinBet** or similar betting-odds pipeline, use the deterministic bridge pattern rather than ad-hoc scraping logic.

### Bridge Pattern

`winbet_skill_bridge.py` (see `templates/winbet_skill_bridge.py`) acts as the adapter:
- Calls `bookmaker_scraper.py` via subprocess (never import; keeps execution deterministic).
- Parses the `ScrapeResult` JSON.
- Inserts/updates `matches` and `odds` tables in the project's SQLite DB.
- Maps `market_type` values: `match_result` → `1x2`, `over_under` → `ou25`.
- Generates deterministic `match_id` as `{league_id}_{home}_{away}_{date}`.

### The Odds API Bridge (WinBet-specific)

For multi-bookmaker aggregation via `the-odds-api.com`, see `references/the-odds-api-integration.md` for the endpoint, response schema, and SQL upsert mapping. Key point: the API returns team names as `h2h` selections (not `1`/`X`/`2`), so downstream surebet detection must do the IT/EN name normalization + outcome code mapping described in pitfall #6.

### DEMO vs LIVE Mode

| Mode | Data Source | Use When |
|------|-------------|----------|
| **LIVE** | `bookmaker_scraper.py` skill → real bookmaker pages | API key available, network OK, no CAPTCHA |
| **LIVE (aggregator)** | `the-odds-api.com` REST → 80+ bookmakers | Italian bookmakers blocked from WSL/datacenter IP |
| **DEMO** | `scraper.py` with seeded random variations | No API key, IP blocked, or testing dashboard/surebet engine |

The bridge reads `mode` from `winbet_config.json`. When `DEMO`, it skips the skill entirely and lets the project's internal demo generator run.

### Cronjob Integration

```bash
# Wrapper script used by Hermes cronjob
winbet_scrape_cycle.sh:
  if [ "$(jq -r .mode winbet_config.json)" = "LIVE" ]; then
    python3 execution/winbet_skill_bridge.py   # calls this skill
  else
    python3 execution/scraper.py               # DEMO variation engine
  fi
  python3 execution/surebet_detector.py
  python3 execution/notifications.py
```

### Anti-Bot Reality Check (Italian Bookmakers, May 2026)

Real-world observations when scraping Italian bookmakers from a residential Italian IP:
- **SNAI / Eurobet**: TCP sinkhole — TLS handshake succeeds, HTTP layer receives **zero bytes** and times out. This is active TLS fingerprint filtering, NOT an IP block. The site's public odds pages redirect or 404 when accessed without a real browser session.
- **OddsPortal**: Pure SPA (React app). HTML contains zero odds; all data loaded via JS `fetch()`. Requires either CDP interception or the site's own internal API (which may be rate-limited and geo-checked).
- **Bet365**: Aggressive anti-bot (TLS fingerprinting + sticky sessions + datacenter IP block). WebSocket-based data delivery. Highest failure rate.

**Implication**: the skill's fallback strategies (`api_intercept` → `dom_parse` → `websocket`) are ordered by likelihood of success. But when a site implements app-level anti-bot (SNAI-style sinkhole), the **only reliable path** is:
1. Run a real browser inside a virtual desktop (TigerVNC + OpenBox + Chrome).
2. Use CDP (`Network.enable`) to capture the internal JSON endpoints.
3. Once endpoints are known, replicate requests directly (matching headers/cookies).
4. If that also fails, activate **DEMO mode** so the rest of the pipeline (dashboard, surebet, notifications) continues to function.

See `references/bookmaker-anti-bot-notes.md` for the full diagnostic transcript.

## Legal Disclaimer

This tool is provided for **educational and personal research purposes only**. Scraping bookmaker websites may violate their Terms of Service. Users are solely responsible for ensuring their use of this tool complies with all applicable laws and regulations in their jurisdiction. The authors accept no liability for misuse.
