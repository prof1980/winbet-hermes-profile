# WSL Browser Reality — Non-Headless Scraping Italian Bookmakers

Session: 2026-05-31
Environment: WSL2 (x86_64, no WSLg), `uv` with Playwright, Chrome/Chromium via `playwright install chromium`
Skill: bookmaker-odds-scraper v1.0.0

---

## Context

The user demanded non-headless (visible browser) scraping of Italian bookmaker sites (SNAI, Eurobet, etc.) believing it would bypass anti-bot protections. This document records what actually happens on WSL2.

---

## 1. Non-Headless on WSL2 Without WSLg → Crash

```bash
$ uv run scripts/bookmaker_scraper.py scrape --bookmaker snai --sport calcio --no-headless
# → Playwright launches browser, but no display exists → invisible window
# → Page still loads, but same anti-bot blocks apply (see below)
```

With `xvfb-run`:
```bash
$ xvfb-run --server-args="-screen 0 1920x1080x24" uv run ... --no-headless
# → Xvfb provides virtual framebuffer → Playwright no longer crashes
# → Same results: 0 events from SNAI, 0 from Eurobet, 0 from OddsPortal
```

Conclusion: xvfb only prevents the "no display" crash. It does NOT change the anti-bot outcome.

---

## 2. SNAI — TLS Fingerprint Sinkhole (curl_cffi Solves This)

**Symptom**: `ERR_HTTP2_PROTOCOL_ERROR` at page.goto()

**What actually happens**: SNAI uses TLS fingerprint filtering (JA3/HTTP2). Playwright's Chromium fingerprint differs from real Chrome, so the connection is dropped before any HTTP data is exchanged.

**With xvfb + non-headless**:
Same `ERR_HTTP2`. Non-headless is irrelevant — the block is below the browser-visible layer.

**What actually works**:
`curl_cffi` with `impersonate='chrome136'` bypasses the TLS fingerprint check entirely. The SNAI backend (`betting-snai.flutterseatech.it`) then serves real odds JSON from the `top-match` endpoint:

```python
from curl_cffi import requests
resp = requests.get(
    'https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0',
    impersonate='chrome136',
    headers={
        'Referer': 'https://www.snai.it/',
        'Origin': 'https://www.snai.it',
        'user_data': '{"accountId":null,"token":null,"tokenJWT":null,"locale":"it_IT","loggedIn":false,"channel":62,"brandId":391,"offerId":0,"clientType":"WEB"}',
    },
    timeout=20,
)
# → 200 OK, ~670 KB JSON, 10–50 real events with 300–1000 quotes
```

**Conclusion**: for SNAI, do NOT use Playwright at all. Use `curl_cffi` directly against the backend API.

---

## 3. Eurobet / Goldbet — Cloudflare + Next.js SPA (Non-Headless + xvfb Helps)

**Symptom**: 0 events, 0 API responses, but HTTP 200-ish (no TLS error)

**What actually happens**: Eurobet is a Next.js SPA. The initial HTML served by the server may contain `__NEXT_DATA__` with the full SSR payload, but only when the request comes from a browser that Cloudflare deems legitimate. In pure headless mode, Cloudflare serves a challenge page and `__NEXT_DATA__` is absent.

**With xvfb + non-headless**:
```bash
# Terminal 1: start virtual display
Xvfb :99 -screen 0 1920x1080x24 -ac &
export DISPLAY=:99

# Terminal 2: run Playwright non-headless
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto('https://www.eurobet.it/it/scommesse/calcio', timeout=60000)
    html = page.content()
    print('__NEXT_DATA__' in html, len(html))
    browser.close()
"
# → True, 278496 bytes
```

The `__NEXT_DATA__` JSON contains the full Next.js SSR payload including competition events and odds. This **does** work with non-headless + xvfb, because Cloudflare sees a "real" browser window and serves the SSR payload instead of the challenge.

**Parsing Eurobet `__NEXT_DATA__`**:
```python
import json, re

match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
data = json.loads(match.group(1))
events = data['props']['pageProps']['competitionEvents']['events']
# Each event has: homeTeam, awayTeam, markets[0].selections with odds
```

**Note**: `xvfb-run` (the wrapper command) often fails with "Xvfb failed to start". Start Xvfb manually in the background and export `DISPLAY=:99` instead.

---

## 4. William Hill — Not Tested with Working Path

Likely similar to Eurobet (Cloudflare challenge + SPA). Try the Eurobet pattern first.

---

## 5. OddsPortal — Pure SPA, Neither Headless Nor curl_cffi Helps

**Symptom**: 11 "events" but all from minor leagues, empty markets, no odds

**What actually happens**: OddsPortal is a pure React SPA. The server-rendered HTML contains only static SEO fixtures. Real odds are loaded via JS `fetch()` after hydration.

**With xvfb + non-headless**: Same result. The SPA data loading is via `fetch()` regardless of headless mode. You need CDP (`Network.enable`) interception to capture the real API calls.

**No working `curl_cffi` path known** — the internal API endpoints are not publicly documented and would need CDP discovery on a real browser.

---

## 6. Lessons for Future Sessions

When scraping Italian bookmakers from WSL/datacenter IPs:

| Target | Tool to try first | Fallback |
|---|---|---|
| **SNAI** | `curl_cffi` with `impersonate='chrome136'` against `flutterseatech.it` API | the-odds-api.com |
| **Eurobet** | Playwright **non-headless** + **manual Xvfb** (`DISPLAY=:99`) | the-odds-api.com |
| **Goldbet** | Same as Eurobet | the-odds-api.com |
| **William Hill** | Same as Eurobet (untested) | the-odds-api.com |
| **OddsPortal** | CDP network interception on real desktop | the-odds-api.com |

**What NOT to do**:
- Do not spend time tuning delays, retries, or stealth scripts for SNAI — the block is TLS fingerprinting, not timing.
- Do not use `xvfb-run` wrapper — start Xvfb manually in background.
- Do not assume non-headless alone fixes anything — it helps Cloudflare but not TLS filtering.

**If user demands non-headless**: explain the real block (TLS or Cloudflare), then offer the specific working path for each target (curl_cffi for SNAI, xvfb+non-headless for Eurobet).
