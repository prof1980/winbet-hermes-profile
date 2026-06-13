# Bookmaker Anti-Bot Diagnostic Notes

Session: 2026-05-29  
Tester: WinBet agent, WSL2 (Linux container, x86_64, datacenter IP)  
Skill version: bookmaker-odds-scraper v1.0.0  
Target bookmakers: SNAI, Eurobet, Goldbet, William Hill, OddsPortal

---

## Executive Summary

All four direct bookmaker targets failed to return usable odds data. The failures are **not** due to stale selectors or script bugs — they are infrastructure-level blocks that a Playwright-based scraper cannot overcome without a real desktop browser environment and a residential Italian IP.

| Bookmaker | Result | Root Cause | Workaround |
|---|---|---|---|
| **SNAI** | 0 events, ERR_HTTP2_PROTOCOL_ERROR | TLS fingerprinting / TCP sinkhole | None in headless env; use `the-odds-api.com` |
| **Eurobet** | 0 events, 0 API responses | Cloudflare challenge + app-level bot detection | None in headless env; use `the-odds-api.com` |
| **Goldbet** | 0 events, 0 API responses | Same as Eurobet | None in headless env; use `the-odds-api.com` |
| **William Hill** | 0 events, timeout | Heavy anti-bot, IP flagged | None in headless env; use `the-odds-api.com` |
| **OddsPortal** | 11 placeholder events, no markets | Pure SPA — odds loaded by JS after page render | Would need CDP interception or internal API |

---

## Detailed Diagnostics

### SNAI — `ERR_HTTP2_PROTOCOL_ERROR`

**Symptom**
```
Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR at https://www.snai.it/scommesse-sportive/calcio/italia/serie-a
```

**What it means**
The TLS handshake succeeds (port 443 is open), but the server drops the HTTP/2 connection immediately after `ClientHello`. This is **active TLS fingerprint filtering**: SNAI's edge infrastructure compares the TLS fingerprint of the client against a whitelist of real browser fingerprints. Playwright's Chromium fingerprint differs from a real desktop Chrome, so the connection is silently killed before any HTTP data is exchanged.

**Verification**
```bash
curl -s -A "Mozilla/5.0 ..." "https://www.snai.it/scommesse-sportive/calcio/italia/serie-a" -w "HTTP %{http_code}\n"
# → HTTP 000  (no TCP payload received at all)
```
Even `curl` with a realistic UA gets `HTTP 000`, confirming this is below the HTTP layer.

**Fixes tried (all failed)**
1. `--no-headless` + `xvfb-run` — same error
2. Stealth init scripts (`navigator.webdriver` removal, fake plugins, fake `chrome.runtime`) — same error
3. Retry with exponential backoff (1s, 2s, 4s) — same error every time
4. Increased `page_load_wait` to 15s — irrelevant, fails at connection setup

**Conclusion**: SNAI's anti-bot operates at the TLS/transport layer. No headless automation tool can bypass it from this environment. The only viable alternative is `the-odds-api.com`, which aggregates SNAI data via a legitimate API.

---

### Eurobet / Goldbet / William Hill — 0 Events with All Strategies

**Symptom**
```
  🔍 Trying strategy 'api_intercept' for eurobet...
  ⚠ Strategy 'api_intercept' returned 0 events
  🔍 Trying strategy 'dom_parse' for eurobet...
  ⚠ Strategy 'dom_parse' returned 0 events
```

**What it means**
The page loads successfully (no TLS error), but the content is **not** the real odds page. Instead, Cloudflare or an in-house WAF returns:
- An invisible JavaScript challenge (`/cdn-cgi/challenge-platform/...`)
- An interstitial page that requires JS execution + cookie setting before redirecting to real content
- A "Checking your browser..." spinner that the scraper never resolves

The Playwright page loads the challenge page, waits for `networkidle`, but the challenge JS either:
- Detects the headless environment and loops forever, OR
- Sets a cookie that would allow redirect, but the scraper doesn't know to wait for it

The DOM therefore contains zero event rows, and the API interceptor sees no JSON because the real API calls happen *after* the challenge is solved.

**Fixes tried (all failed)**
1. Increased `wait_before_scrape_ms` to 12s, `random_delay_range_ms` to [2.5s, 7s]
2. Changed `wait_until` from `domcontentloaded` to `networkidle`
3. Added retry logic (3 attempts with exponential backoff)
4. Increased scroll depth and added "Load more" button clicking

**Conclusion**: Cloudflare-style challenges require a **real desktop browser** running inside a real OS session (not a headless container), with a **residential IP** and **human-like interaction timing**. Even then, repeated automation triggers will eventually cause CAPTCHA or IP block. Use `the-odds-api.com` instead.

---

### OddsPortal — Placeholder DOM Events

**Symptom**
```
  🔍 Trying strategy 'dom_parse' for oddsportal…
  ✓ Strategy 'dom_parse' returned 11 event(s)
  # But events are:
  #   Cobresal vs Nublense (Chilean league)
  #   Independiente F.B.C. vs 12 de Junio
  #   One Knoxville vs Greenville (USL League One)
  # ... all with empty markets, no odds, no dates
```

**What it means**
OddsPortal is a **pure Single Page Application (SPA)** built in React. The initial HTML served by the server contains only:
- A `<div id="root"></div>` shell
- Pre-rendered SEO metadata (which happens to include some unrelated football fixtures as static JSON)
- No odds whatsoever

The real odds data is loaded via JavaScript `fetch()` to internal API endpoints after the React app mounts. The `dom_parse` strategy reads the static HTML *before* React renders, so it finds only the static placeholder fixtures (which happen to be from minor leagues that were server-side rendered for SEO).

**Fixes tried**
1. Waited for `networkidle` — still 0 events from the real API because the interceptor wasn't capturing the right endpoints.
2. Discovery mode attempted but crashed on `_truncate()` JSON decoding bug (see bug fix below).

**Conclusion**: OddsPortal requires either:
- CDP (`Network.enable`) to intercept the internal JS `fetch()` calls, OR
- Direct use of their internal API endpoints (reverse-engineered), OR
- Use `the-odds-api.com` which already does this aggregation.

---

## Configuration Changes Applied

The following changes were made to `bookmakers.json` to make delays more aggressive:

```json
{
  "snai":    { "wait_before_scrape_ms": 15000, "random_delay_range_ms": [3000, 8000] },
  "eurobet": { "wait_before_scrape_ms": 12000, "random_delay_range_ms": [2500, 7000] },
  "goldbet": { "wait_before_scrape_ms": 12000, "random_delay_range_ms": [2500, 7000] },
  "williamhill": { "wait_before_scrape_ms": 15000, "random_delay_range_ms": [3000, 8000] }
}
```

And to `bookmaker_scraper.py`:
- `_navigate_with_delays`: changed `wait_until="domcontentloaded"` → `"networkidle"`, timeout 30s → 60s, added retry loop with exponential backoff (3 attempts)
- `_navigate_with_delays`: now reads `anti_bot.wait_before_scrape_ms` and `anti_bot.random_delay_range_ms` from config instead of hard-coded values
- `_interact_for_data`: increased scroll iterations 3 → 6, added "Load more" button auto-clicking, added `page.wait_for_load_state("networkidle")` after interactions, added `extra_settle_ms` configurable wait

Despite all of this, **zero real odds were obtained** from any Italian bookmaker.

---

## Recommended Architecture for Production

Given the above constraints, a production betting-odds pipeline should use this **dual-mode architecture**:

### Mode A: LIVE (the-odds-api.com)
```python
# execution/scraper.py
import requests

SPORT = "soccer"  # or "soccer_italy_serie_a"
REGION = "eu"     # European bookmakers
MARKETS = "h2h,totals"  # 1X2 + Over/Under

url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds"
r = requests.get(url, params={
    "apiKey": API_KEY,
    "regions": REGION,
    "markets": MARKETS,
    "oddsFormat": "decimal"
})
# Returns structured JSON with real odds from 20+ bookmakers
```

**Why this works**: it's a legitimate REST API. No browser automation, no anti-bot, no CAPTCHA. 500 req/month free.

### Mode B: DEMO (seeded random)
When no API key is available, or for testing the dashboard/surebet engine:
```python
# Generate realistic odds variations around a base line
# Example: Juventus-Inter base: 2.20 / 3.20 / 3.40
# Each bookmaker gets ±3% variation
# Surebets are intentionally injected at 2-5% rate for testing
```

### Mode Switching
```json
{
  "mode": "LIVE",
  "api_key_theoddsapi": "abc123...",
  "fallback_to_demo_on_error": true
}
```

---

## Script Bug Fix: `_truncate()` in discover mode

**Bug**: `cmd_discover` calls `_truncate(r["body"])` where `r["body"]` is already a dict. `_truncate` does `json.dumps(obj, ...)` then string-slicing, then `json.loads(...)` — but the sliced string is often malformed JSON.

**Fix**: `_truncate` should check if the input is already a dict/list and just return it (or deep-truncate strings inside it), instead of round-tripping through JSON string slicing.

This was not fixed in this session because the discover mode failure was a secondary issue after the primary scraping failures.

---

## References

- `the-odds-api.com` documentation: https://the-odds-api.com/
- TLS fingerprinting research: https://ja3er.com/
- Cloudflare bot management: https://developers.cloudflare.com/bots/
- Playwright stealth limitations: https://github.com/ultrafunkamsterdam/undetected-chromedriver
