# curl_cffi Anti-Bot Pattern — TLS Fingerprint Bypass

Generic technique for scraping sites that block headless browsers via TLS/HTTP2 fingerprinting (JA3, JA4, HTTP/2 SETTINGS, ALPN, pseudo-header order).

## When to Use

Use `curl_cffi` when you see any of these signals:
- `ERR_HTTP2_PROTOCOL_ERROR` in Playwright
- `HTTP 000` from raw `curl` (no payload at all)
- Connection reset immediately after TLS handshake
- Site works in your desktop Chrome but fails in any headless tool

These are **not** CAPTCHA or JavaScript challenges — they are transport-layer blocks that happen before HTTP headers are even sent.

## Installation

```bash
pip install curl_cffi
```

## Basic Pattern

```python
from curl_cffi import requests

resp = requests.get(
    url,
    impersonate='chrome136',   # or chrome131, chrome145, edge101, safari17_0
    timeout=15,
)
# resp.status_code, resp.json(), resp.text all work like requests
```

## Advanced Pattern (Headers + JSON POST)

```python
from curl_cffi import requests

resp = requests.get(
    'https://api.target-site.com/internal/endpoint',
    impersonate='chrome136',
    headers={
        'Accept': 'application/json',
        'Referer': 'https://www.target-site.com/',
        'Origin': 'https://www.target-site.com',
        'X-Some-Token': 'public-token-or-null',
    },
    timeout=20,
)
```

## Key Differences from `requests`

| Feature | `requests` | `curl_cffi` |
|---|---|---|
| TLS fingerprint | Default (python-urllib3) | Chrome/Edge/Safari exact match |
| HTTP/2 handling | Often disabled or different | Same as real browser |
| ALPN / pseudo-headers | Library defaults | Browser-matched |
| Cookie jar | `requests.Session` | `requests.Session` (same API) |
| Performance | Pure Python | libcurl (C), faster |

## Common Impersonate Profiles

| Profile | Use When |
|---|---|
| `chrome136` | Default for 2026; matches latest stable Chrome |
| `chrome131` | Slightly older; use if 136 is blocked |
| `chrome145` | Canary/dev; try if stable is blocked |
| `edge101` | Microsoft Edge fingerprint |
| `safari17_0` | Safari on macOS |

## Warnings

1. **Not a silver bullet**: `curl_cffi` bypasses TLS fingerprinting but NOT Cloudflare JavaScript challenges. If the site uses JS challenge loops, you still need a real browser (Playwright non-headless + xvfb).
2. **Rate limits still apply**: The site can still throttle or ban your IP based on request frequency.
3. **Terms of Service**: Some sites explicitly prohibit automated access. Use responsibly.
4. **Session context**: `curl_cffi` does not execute JavaScript. For SPAs that load data via `fetch()` after hydration, you may need to discover the internal API endpoints first (via CDP on a real browser), then replicate them with `curl_cffi`.

## Complementary Tools

| Problem | Tool |
|---|---|
| TLS fingerprint block | `curl_cffi` |
| Cloudflare JS challenge | Playwright non-headless + xvfb |
| SPA internal API discovery | Chrome DevTools CDP `Network.enable` |
| IP reputation ban | Residential proxy, VPN, or wait cooldown |
| Geo-blocking | Geo-targeted proxy in target country |

## One-Liner Test

```bash
python3 -c "from curl_cffi import requests; r = requests.get('https://www.snai.it', impersonate='chrome136', timeout=10); print(r.status_code, len(r.content))"
```

If this returns `200` and a non-zero length while raw `curl` returns `000`, you have confirmed a TLS fingerprint block.
