# Eurobet Internal API Endpoints — Discovered 2026-05-31

## Discovery Context

Eurobet's public website is a Next.js SPA that aggressively blocks headless browsers (Cloudflare loop, TLS fingerprint rejection). However, the site's **internal detail-service API** serves JSON directly and is reachable via `curl_cffi` TLS impersonation — bypassing the anti-bot layer entirely. These endpoints were discovered by monitoring XHR traffic during a Playwright `discover` pass with non-headless browser.

## Base URL

```
https://www.eurobet.it
```

## Endpoint Patterns

### Meeting-level (specific competition)

```
/detail-service/sport-schedule/services/meeting/{discipline}/{meeting}?prematch=1&live=0
```

| Meeting | Slug | Example |
|---|---|---|
| Mondiali 2026 | `wd-mondiali-calcio` | `.../meeting/calcio/wd-mondiali-calcio?prematch=1&live=0` |
| Amichevoli Nazionali | `wd-amichevoli-nazionali` | `.../meeting/calcio/wd-amichevoli-nazionali?prematch=1&live=0` |

### Discipline-level (all calcio today)

```
/detail-service/sport-schedule/services/discipline/calcio?prematch=1&live=0&temporalFilter=TEMPORAL_FILTER_OGGI
```

Returns ALL calcio events for today across all competitions (~440KB response).

### Response Schema

```json
{
  "code": 1,
  "description": "ok",
  "result": {
    "dataGroupList": [
      {
        "date": "2026-06-11T00:00:00+02:00",
        "itemList": [
          {
            "eventInfo": {
              "programCode": 36241,
              "eventCode": 2037,
              "eventDescription": "Messico - Sudafrica",
              "eventData": 1781204400000,
              "meetingDescription": "Mondiali 2026",
              "teamHome": {"description": "Messico", "tmId": 4202},
              "teamAway": {"description": "Sudafrica", "tmId": 6378},
              "live": false,
              "betsNumber": 754
            },
            "betGroupList": [
              {
                "betDescription": "SCOMMESSE TOP",
                "oddGroupList": [
                  {
                    "oddGroupDescription": "1X2",
                    "oddList": [
                      {"boxTitle": "1", "oddValue": 142},
                      {"boxTitle": "X", "oddValue": 430},
                      {"boxTitle": "2", "oddValue": 720}
                    ]
                  },
                  {
                    "oddGroupDescription": "U/O GOAL 2,5",
                    "oddList": [
                      {"boxTitle": "UNDER", "oddValue": 172},
                      {"boxTitle": "OVER", "oddValue": 199}
                    ]
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

### Key Data Paths

| Field | Path | Notes |
|---|---|---|
| Teams | `eventInfo.teamHome.description` / `teamAway.description` | Always present |
| Start time | `eventInfo.eventData` | Milliseconds since epoch; divide by 1000 for unix timestamp |
| Competition | `eventInfo.meetingDescription` | e.g. "Mondiali 2026" |
| Market name | `oddGroupList[*].oddGroupDescription` | e.g. "1X2", "U/O GOAL 2,5" |
| Selection name | `oddList[*].boxTitle` | e.g. "1", "X", "2", "UNDER", "OVER" |
| Odds value | `oddList[*].oddValue` | **Centesimi** — divide by 100 for decimal odds (142 → 1.42) |
| Event ID | `eventInfo.eventCode` + `eventInfo.programCode` | Composite: `eb_{program}_{event}` |

### Headers Required

```python
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.eurobet.it/it/scommesse",
    "Origin": "https://www.eurobet.it",
}
```

### curl_cffi Call

```python
from curl_cffi import requests

resp = requests.get(
    "https://www.eurobet.it/detail-service/sport-schedule/services/meeting/calcio/wd-mondiali-calcio?prematch=1&live=0",
    headers=HEADERS,
    impersonate="chrome136",
    timeout=20,
)
# resp.json() → code:1, result.dataGroupList[...].itemList[...]
```

## Comparison with Next.js SSR Fallback

| Approach | Speed | Reliability | Anti-bot |
|---|---|---|---|
| **API-first** (this doc) | ~1s | ✅ High | Bypassed via TLS impersonation |
| Next.js SSR (`__NEXT_DATA__`) | ~8s | ⚠️ Medium | Needs non-headless + Xvfb |
| Playwright DOM parsing | ~12s | ❌ Low | Cloudflare blocks headless |

**Recommendation**: Always try API-first. Fall back to Next.js SSR only if the API endpoint returns a non-1 code or the meeting slug changes.

## Pitfall: Meeting Slugs Change

The `meeting` slug (e.g. `wd-mondiali-calcio`) is derived from Eurobet's internal classification. It may change between seasons or if the competition is rebranded. To discover current slugs:

1. Load `https://www.eurobet.it/it/scommesse/calcio` in a real browser.
2. Intercept the call to `/prematch-menu-service/api/v2/sport-schedule/services/sport-list/calcio`.
3. The response contains `meetingList[*].aliasUrl` with the current slugs.

Example discovery response:
```json
{
  "code": 1,
  "result": {
    "meetingList": [
      {"aliasUrl": "wd-mondiali-calcio", "description": "Mondiali 2026"},
      {"aliasUrl": "wd-amichevoli-nazionali", "description": "Amichevoli Nazionali"},
      {"aliasUrl": "it-serie-a", "description": "Serie A"}
    ]
  }
}
```
