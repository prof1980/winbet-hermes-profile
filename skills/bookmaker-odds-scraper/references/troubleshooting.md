# Troubleshooting Guide — Bookmaker Odds Scraper

This document covers common issues, debugging techniques, and best practices for maintaining the bookmaker odds scraper.

---

## Common Issues

### 1. Playwright Not Installed

**Symptom**: Error message like `playwright._impl._errors.Error: Executable doesn't exist` or `browserType.launch: Browser is not installed`.

**Fix**:
```bash
playwright install chromium
```

If `playwright` itself is not found, ensure dependencies were installed via `uv run` first:
```bash
uv run scripts/bookmaker_scraper.py list-bookmakers --output /tmp/test.json
# This triggers dependency installation, then:
playwright install chromium
```

---

### 2. Cloudflare / CAPTCHA Blocking

**Symptom**: Empty results, HTTP 403 responses, or the page loads a Cloudflare challenge screen instead of odds data.

**Fixes** (try in order):

1. **Use visible browser mode** to manually solve the CAPTCHA once:
   ```bash
   uv run scripts/bookmaker_scraper.py scrape \
     --bookmaker <name> --sport calcio --no-headless \
     --output /tmp/debug.json
   ```

2. **Increase page load delays** in `bookmakers.json`:
   ```json
   {
     "delays": {
       "page_load_wait": 10000,
       "between_requests": 5000
     }
   }
   ```

3. **Try again later** — some protections are time-based and relax after a cooldown period.

4. **Switch network** — your current IP may be flagged. Try a different connection.

---

### 3. Empty Results (No Events Found)

**Symptom**: The scrape completes without errors but `events` array is empty.

**Possible causes**:
- The bookmaker changed their frontend structure (selectors are stale).
- No events are currently listed for the requested competition.
- The page didn't fully load before scraping began.

**Fixes**:

1. **Verify events exist** — open the bookmaker site manually in a browser and confirm odds are displayed for the requested competition.

2. **Run discovery** to detect updated endpoints/selectors:
   ```bash
   uv run scripts/bookmaker_scraper.py discover \
     --bookmaker <name> --sport calcio \
     --output /tmp/discovery.json
   ```

3. **Update selectors** in `bookmakers.json` based on discovery output (see [How to Update Selectors](#how-to-update-selectors) below).

4. **Increase `page_load_wait`** — the page may need more time to render dynamic content.

---

### 4. Timeout Errors

**Symptom**: `TimeoutError: page.wait_for_selector: Timeout 30000ms exceeded` or similar.

**Fixes**:

1. **Increase wait times** in `bookmakers.json`:
   ```json
   {
     "delays": {
       "page_load_wait": 15000,
       "element_wait": 10000
     }
   }
   ```

2. **Check your internet connection** — slow connections cause legitimate timeouts.

3. **Try `--no-headless`** to visually verify what the browser is seeing.

4. **Check if the site is down** — visit the bookmaker URL manually.

---

### 5. IP Banned / Rate Limited

**Symptom**: Consistent HTTP 429 responses, connection resets, or permanent CAPTCHA loops.

**Fixes**:

1. **Wait** — most bans are temporary (30 minutes to 24 hours).

2. **Switch to a different network** (mobile hotspot, different WiFi, VPN).

3. **Reduce scraping frequency** — don't scrape the same bookmaker more than once every 15-30 minutes.

4. **Consider a proxy** — configure a residential proxy if needed for repeated use (not included in this tool).

---

## How to Update Selectors

When a bookmaker redesigns their website, CSS selectors break. Here's how to find the new ones:

### Step-by-Step

1. **Open the bookmaker website** in Google Chrome and navigate to the odds page for the sport/competition you want to scrape.

2. **Right-click on an odds element** (e.g., the "2.45" odds value) and select **Inspect** to open Chrome DevTools.

3. **Identify the CSS selector** for the odds element:
   - Look at the element's `class` attribute in the Elements panel.
   - Right-click the element in DevTools → **Copy** → **Copy selector** for a precise CSS selector.
   - Note the parent container that groups all selections for a single event.

4. **Identify the structural hierarchy**:
   - **Event container**: The element that wraps a single match (home team, away team, all markets).
   - **Team names**: Elements containing team names within the event container.
   - **Market container**: The element grouping selections for a single market (e.g., 1X2).
   - **Selection/odds value**: The element containing the numeric odds.

5. **Update `bookmakers.json`** with the new selectors:
   ```json
   {
     "key": "snai",
     "selectors": {
       "event_container": ".event-row",
       "home_team": ".event-row .team-home",
       "away_team": ".event-row .team-away",
       "market_container": ".odds-group",
       "odds_value": ".odds-group .odd-value",
       "event_date": ".event-row .event-date"
     }
   }
   ```

6. **Test** with a small scrape in visible mode:
   ```bash
   uv run scripts/bookmaker_scraper.py scrape \
     --bookmaker snai --sport calcio --competition serie-a \
     --no-headless --output /tmp/test.json
   ```

### Tips for Robust Selectors

- Prefer **data attributes** (e.g., `[data-type="odds"]`) over class names — they change less frequently.
- Use **structural selectors** (e.g., `nth-child`) as a fallback when class names are auto-generated.
- Avoid overly specific selectors — the shorter and more semantic, the more durable.

---

## How to Discover New API Endpoints

### Using the `discover` Command

The `discover` subcommand passively monitors all network traffic while loading a bookmaker's page:

```bash
uv run scripts/bookmaker_scraper.py discover \
  --bookmaker snai --sport calcio \
  --output /tmp/snai_discovery.json
```

This captures:
- **XHR/Fetch requests**: REST API calls the frontend makes to load odds data.
- **WebSocket connections**: Real-time data streams (common with Bet365).
- **Request/response payloads**: Sample data to understand the API schema.
- **URL patterns**: Regex patterns for API endpoint matching.

### Manual DevTools Inspection

For deeper investigation:

1. Open Chrome DevTools (**F12**) → **Network** tab.
2. Navigate to the bookmaker's odds page.
3. Filter by **XHR/Fetch** to see API calls.
4. Look for requests that return JSON with odds data — these are your targets.
5. Note:
   - The **URL pattern** (e.g., `/api/v1/events?sport=calcio`).
   - **Headers** — especially any required `Authorization`, `X-API-Key`, or session tokens.
   - **Response structure** — map fields to the `ScrapeResult` schema.

6. For **WebSocket** data:
   - Switch to the **WS** filter in the Network tab.
   - Look for frames containing odds data in JSON format.
   - Note the WebSocket URL and any subscription messages needed.

7. Update `bookmakers.json` with the discovered `api_patterns`:
   ```json
   {
     "api_patterns": [
       {
         "url_pattern": "/api/v1/sport-events*",
         "method": "GET",
         "response_type": "json",
         "data_path": "data.events"
       }
     ]
   }
   ```

---

## Anti-Bot Best Practices

Bookmaker websites employ various anti-bot measures. Follow these practices to minimize detection and blocking:

### Timing & Frequency

- **Space requests**: Wait at least 3-5 seconds between page loads. The default delays in `bookmakers.json` are tuned for this — don't reduce them.
- **Limit frequency**: Don't scrape the same bookmaker more than once every 15-30 minutes.
- **Avoid patterns**: Don't scrape at exact intervals (e.g., every 60 seconds). Add random jitter to timing.
- **Off-peak hours**: Scraping during low-traffic hours (late night/early morning) is less likely to trigger protections.

### Browser Behavior

- **Use realistic viewport sizes**: The scraper uses standard desktop resolutions by default.
- **Mimic human interaction**: The scraper includes random mouse movements and scroll patterns. Don't disable these.
- **Accept cookies**: The scraper handles cookie banners automatically.
- **Use a persistent browser context**: Reusing browser profiles avoids fingerprint changes that trigger detection.

### Network

- **Residential IPs**: If you need sustained scraping, residential IPs are far less likely to be blocked than datacenter IPs.
- **Rotate user agents**: The scraper rotates user-agent strings automatically.
- **Respect `robots.txt`**: While not legally binding in all jurisdictions, respecting `robots.txt` is good practice.

### What NOT to Do

- ❌ Don't run parallel scrapes against the same bookmaker.
- ❌ Don't reduce configured delays below recommended minimums.
- ❌ Don't scrape during major live events (highest protection levels).
- ❌ Don't use the same IP to scrape all bookmakers in rapid succession.

---

## Legal Disclaimer

> **⚠️ Important**: This tool is provided for **educational and personal research purposes only**.

- Scraping bookmaker websites may violate their **Terms of Service (ToS)**.
- The legality of web scraping varies by jurisdiction. In some regions, scraping publicly available data is permitted; in others, it may be restricted.
- **You are solely responsible** for ensuring your use of this tool complies with all applicable laws, regulations, and the Terms of Service of the websites you access.
- The authors of this tool **accept no liability** for any legal consequences, account bans, IP blocks, or other damages resulting from its use.
- This tool does **not** access any authenticated or protected content — it only reads publicly visible odds data.
- If a bookmaker explicitly prohibits automated access, **respect their wishes**.
