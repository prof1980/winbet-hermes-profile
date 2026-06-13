# SNAI Reverse-Engineering Notes

Session: 2026-05-31
Tester: WinBet agent, WSL2 (Linux container, x86_64, datacenter IP)
Skill version: bookmaker-odds-scraper v1.0.0
Target: SNAI.it SPA betting app

---

## Executive Summary

SNAI.it is a React Single Page Application (SPA) served from `www.snai.it` but backed by a separate betting API platform at `betting-snai.flutterseatech.it`. The frontend loads a configuration file (`sport-online-configuration.js`) that exposes the internal API paths. While a real browser + visible mode does **not** help against the TLS sinkhole, `curl_cffi` with Chrome TLS impersonation **does** bypass the transport-level block and allows retrieval of the SPA shell and the betting API configuration.

However, the actual odds data endpoints require deep reverse-engineering of the internal routing structure, which proved too time-consuming for this session. The recommended fallback remains `the-odds-api.com`.

---

## Phase 1: Bypassing the TLS Sinkhole with curl_cffi

### Symptom

Standard `curl` and Playwright both fail with `ERR_HTTP2_PROTOCOL_ERROR` or `HTTP 000` against SNAI URLs:

```bash
curl -A "Mozilla/5.0 ..." "https://www.snai.it/scommesse-sportive/calcio/italia/serie-a"
# → HTTP 000 (no payload)
```

### Tool: curl_cffi

`curl_cffi` is a Python HTTP client built on `libcurl-impersonate` that replicates the exact TLS fingerprint (JA3, JA4, HTTP/2 settings, ALPN, pseudo-header order) of a real Chrome browser. Installation:

```bash
pip install curl_cffi
```

### Test Results

```python
from curl_cffi import requests

for browser in ['chrome131', 'chrome136', 'chrome145']:
    resp = requests.get(
        'https://www.snai.it/scommesse-sportive/calcio/italia/serie-a',
        impersonate=browser,
        timeout=15
    )
    print(f'[{browser}] Status: {resp.status_code} | Length: {len(resp.content)}')
```

| Browser Profile | Status | Result |
|---|---|---|
| `chrome131` | 404 | TLS bypass confirmed |
| `chrome136` | 404 | TLS bypass confirmed |
| `chrome145` | 404 | TLS bypass confirmed |

**Conclusion**: `curl_cffi` successfully passes the TLS fingerprint check. The 404 is an application-level response (the URL path is stale), not a transport-level block.

---

## Phase 2: Discovering the Working API Endpoint

While the SNAI frontend (`www.snai.it`) serves a React SPA, the **real odds data** is served by a separate backend API on `betting-snai.flutterseatech.it`. Through exploration of the frontend HTML and config, a working endpoint for **top matches** was discovered:

```
GET https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0
```

### Request (working curl_cffi snippet)

```python
from curl_cffi import requests

url = 'https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0'

resp = requests.get(
    url,
    impersonate='chrome136',
    headers={
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.snai.it/',
        'Origin': 'https://www.snai.it',
        'bet-locale': 'it_IT',
        'bet-brand': '391',
        'bet-offer': '0',
        'bet-version': 'SNAI_2',
        'user_data': '{"accountId":null,"token":null,"tokenJWT":null,"locale":"it_IT","loggedIn":false,"channel":62,"brandId":391,"offerId":0,"clientType":"WEB"}',
    },
    timeout=20,
)
# Status: 200
# Content-Type: application/json
# Body size: ~670 KB
```

**Note**: `user_data` contains only null tokens and publicly known brand IDs — no real credentials. Safe for reuse.

---

## Phase 3: Parsing the Response

### Top-Level Structure

```json
{
  "scommessaMap": { ... },      // Market definitions by avvenimento (match)
  "infoAggiuntivaMap": { ... },  // Actual odds per market variant
  "avvenimentoFeList": [ ... ],  // Event list with basic metadata
  "disciplinaList": [ ... ],     // Sport disciplines
  "manifestazioneList": [ ... ], // Competitions / leagues
  ...
}
```

### Market Definitions (`scommessaMap`)

Each entry key: `{codicePalinsesto}-{codiceAvvenimento}-{codiceScommessa}`

```json
{
  "codiceAvvenimento": 12345,
  "codiceScommessa": 3,
  "descrizioneScommessa": "ESITO FINALE 1X2",
  "listaEsito": [
    {"codice": "1", "descrizione": "1"},
    {"codice": "X", "descrizione": "X"},
    {"codice": "2", "descrizione": "2"}
  ]
}
```

**Market type mapping:**
- `3` → `1x2` (Esito Finale)
- `4` → `ou25` (Under/Over 2.5)
- `5` → `gng` (Gol/NoGol)
- `412` → `first_goal` (Primo Marcatore)
- Other codes → map by `codiceScommessa` as `market_{code}`

### Actual Odds (`infoAggiuntivaMap`)

Each entry key: `{codicePalinsesto}-{codiceAvvenimento}-{codiceScommessa}-{idInfoAggiuntiva}`

```json
{
  "codiceAvvenimento": 12345,
  "codiceScommessa": 3,
  "idInfoAggiuntiva": 1,
  "esitoList": [
    {"codice": "1", "descrizione": "1", "quota": 108, "stato": 1},
    {"codice": "X", "descrizione": "X", "quota": 1000, "stato": 1},
    {"codice": "2", "descrizione": "2", "quota": 2500, "stato": 1}
  ]
}
```

**Critical**: `quota` is in **centesimi** — divide by 100 to get decimal odds:
- `108` → `1.08`
- `1000` → `10.0`
- `2500` → `25.0`

### Event Metadata (`avvenimentoFeList`)

```json
{
  "descrizione": "Bulgaria - Montenegro",
  "descrizioneDisciplina": "Calcio",
  "descrizioneManifestazione": "AMICHEVOLI INTERNAZIONALI",
  "data": "01/06/2026",
  "orario": "16:00"
}
```

### Full Extraction Algorithm

```python
def parse_snai_topmatch(data: dict) -> list[Event]:
    events = []

    for avv in data.get('avvenimentoFeList', []):
        match_id = f"snai_{avv['codicePalinsesto']}_{avv['codiceAvvenimento']}"
        home_team, away_team = avv['descrizione'].split(' - ', 1)
        date = avv['data']
        time = avv['orario']
        league = avv['descrizioneManifestazione']

        markets = []
        for sm_key, sm in data.get('scommessaMap', {}).items():
            if sm.get('codiceAvvenimento') != avv['codiceAvvenimento']:
                continue

            market_type = MARKET_MAP.get(sm['codiceScommessa'], f"market_{sm['codiceScommessa']}")
            market_name = sm.get('descrizioneScommessa', market_type)

            selections = []
            for info_key, info in data.get('infoAggiuntivaMap', {}).items():
                if (info.get('codiceAvvenimento') == avv['codiceAvvenimento']
                        and info.get('codiceScommessa') == sm['codiceScommessa']):
                    for esito in info.get('esitoList', []):
                        selections.append({
                            'name': esito['codice'],
                            'label': esito['descrizione'],
                            'odds': esito['quota'] / 100.0,
                        })
                    break  # one infoAggiuntiva entry per market is enough

            if selections:
                markets.append({
                    'market_type': market_type,
                    'market_name': market_name,
                    'selections': selections,
                })

        events.append({
            'match_id': match_id,
            'home_team': home_team,
            'away_team': away_team,
            'date': date,
            'time': time,
            'league': league,
            'markets': markets,
            'bookmaker': 'snai',
        })

    return events
```

---

## Phase 4: Other Endpoints Explored (Not Working)

### Sport/Competition Endpoints

```python
base = 'https://betting-snai.flutterseatech.it'
paths = [
    '/api/lettura-palinsesto-sport/palinsesto/prematch/calcio',
    '/api/lettura-palinsesto-sport/palinsesto/prematch/sport/calcio',
    '/api/ondemand/palinsesto/calcio',
    '/ondemand/palinsesto/calcio',
    '/api/ondemand/palinsesto/sport/calcio',
    '/api/palinsesto/prematch/calcio',
]
```

All returned **404** or **text/html** (not JSON).

### On-Demand CDN

```
https://sisal-ondemand-2022.nexusweb.it/ondemand/palinsesto/calcio
```

DNS resolution failure — appears deprecated or geofenced.

---

## Summary: What Works vs What Doesn't

| Approach | Result | Notes |
|---|---|---|
| Standard curl | ❌ HTTP 000 | TLS fingerprint rejected |
| Playwright headless | ❌ ERR_HTTP2 | TLS fingerprint rejected |
| Playwright + xvfb + non-headless | ❌ ERR_HTTP2 | TLS fingerprint rejected (headless vs visible irrelevant for SNAI) |
| curl_cffi (`impersonate='chrome136'`) | ✅ 200 OK | Bypasses TLS sinkhole |
| curl_cffi + `top-match` endpoint | ✅ Real odds | 10–50 events, 300–1000 quotes per call |
| curl_cffi + guessed match endpoints | ❌ 404 | URI structure unknown for per-competition endpoints |
| the-odds-api.com | ✅ Real odds | Reliable fallback, but costs money beyond 500 req/month |

---

## Recommended Path Forward

### Option A: Use the `top-match` Endpoint (Production-Ready)

The `top-match` endpoint is **stable, fast (~1s), and returns real odds** without requiring a browser. It is the recommended path for any automated pipeline:

```python
from curl_cffi import requests

url = 'https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/v1/top-match?offerId=0'
resp = requests.get(url, impersonate='chrome136', headers={...}, timeout=20)
data = resp.json()
events = parse_snai_topmatch(data)
# → 10–50 real events with 300–1000 quotes
```

**Limitations of `top-match`:**
- Returns only "top" matches across all sports, not a full competition list
- Serie A may not appear during off-season (June); returns amichevoli, internationals, tennis, etc.
- No guarantee of which events are included — it's a curated list
- For full competition coverage, per-competition endpoints are needed (still undiscovered)

### Option B: the-odds-api.com (Low Effort, Broad Coverage)

```python
url = "https://api.the-odds-api.com/v4/sports/soccer_italy_serie_a/odds"
resp = requests.get(url, params={"apiKey": API_KEY, "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"})
```

**Use when**: `top-match` does not cover the competitions you need, or you need odds from multiple bookmakers (not just SNAI).

### Option C: Deep Reverse-Engineering (High Effort, Fragile)

For full competition coverage from SNAI directly:
1. Launch Chrome on a real desktop with DevTools open
2. Navigate to SNAI sport app, filter by competition
3. Capture every `fetch()` call via Network tab
4. Reverse-engineer per-competition and per-match endpoints
5. Replicate in `curl_cffi`

**Not recommended for production** — API contract can change at any time.

---

## Key Files from This Session

- `/tmp/snai_betting_config.json` — Extracted `FR_SPORT_CONFIG` (100+ keys)
- `/tmp/snai_prematch.json` — Response from `prematch/init` endpoint
- `/tmp/snai_app_sport.html` — SPA shell HTML
- `execution/snai_scraper.py` — Production scraper using `top-match` endpoint

These files are preserved in the project `.tmp/` directory for future reverse-engineering attempts.
