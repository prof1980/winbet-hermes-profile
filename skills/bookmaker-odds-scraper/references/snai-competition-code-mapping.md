# SNAI Competition Code Mapping (2026-06-08)

## The problem

SNAI's `betting-snai.flutterseatech.it` API returns a numeric
`codiceManifestazione` (and `codiceDisciplina`) for each event but **no human-
readable league name**. The `descrizione` field contains the *match* (e.g.
`"Spagna - Perù"`), not the league.

There is no public endpoint to look up the league by code. All of the following
return 404:

- `GET /api/lettura-palinsesto-sport/manifestazione/{code}`
- `GET /api/lettura-palinsesto-sport/manifestazioni`
- `GET /api/lettura-palinsesto-sport/palinsesto/prematch/v1/manifestazioni`
- `GET /api/lettura-palinsesto-sport/calcio/manifestazioni`
- `GET /api/lettura-palinsesto-sport/calcio`
- `GET /api/lettura-palinsesto-sport/categorie`
- `GET /api/lettura-palinsesto-sport/calcio/{code}`

## The fix

Maintain a static dict in the scraper and discover codes empirically by
fetching the API and looking at distinct `(codiceDisciplina, codiceManifestazione)`
tuples. This file is the canonical mapping as of 2026-06-08.

## Code → name (verified live)

### Calcio (codiceDisciplina = 1)

| codiceManifestazione | League name | Notes |
|---|---|---|
| 765 | Amichevoli Internazionali | The only one currently active in top-match feed (June 2026) |
| 766 | Qualificazioni Mondiali | placeholder, not yet seen |
| 767 | Qualificazioni Europei | placeholder |
| 768 | Serie A | placeholder |
| 769 | Serie B | placeholder |
| 770 | Champions League | placeholder |
| 771 | Europa League | placeholder |
| 772 | Conference League | placeholder |
| 773 | Premier League | placeholder |
| 774 | La Liga | placeholder |
| 775 | Bundesliga | placeholder |
| 776 | Ligue 1 | placeholder |

> Codes 766–776 are speculative placeholders. Add the real ones when observed.
> Until then, unknown codes fall through to `"Calcio (manifestazione {code})"`
> so they still appear in the UI with a discoverable label.

### Basket (codiceDisciplina = 2)

| codiceManifestazione | League name |
|---|---|
| 1200 | Basket Italia |
| 1246 | WNBA |

### Tennis (codiceDisciplina = 3)

| codiceManifestazione | League name |
|---|---|
| 1679 | Tennis ATP |
| 1866 | Tennis ATP |

### Ciclismo (codiceDisciplina = 11)

| codiceManifestazione | League name |
|---|---|
| 2793 | Ciclismo su strada |

## Reference implementation

```python
SNAI_COMPETITION_MAP = {
    (1, 765): "Amichevoli Internazionali",
    (1, 766): "Qualificazioni Mondiali",
    (1, 767): "Qualificazioni Europei",
    (1, 768): "Serie A",
    (1, 769): "Serie B",
    (1, 770): "Champions League",
    (1, 771): "Europa League",
    (1, 772): "Conference League",
    (1, 773): "Premier League",
    (1, 774): "La Liga",
    (1, 775): "Bundesliga",
    (1, 776): "Ligue 1",
    (2, 1200): "Basket Italia",
    (2, 1246): "WNBA",
    (3, 1679): "Tennis ATP",
    (3, 1866): "Tennis ATP",
    (11, 2793): "Ciclismo su strada",
}

def resolve_competition_name(discipline_code, competition_code):
    if competition_code is None:
        return ""
    try:
        dc, cc = int(discipline_code), int(competition_code)
    except (TypeError, ValueError):
        return ""
    name = SNAI_COMPETITION_MAP.get((dc, cc))
    if name:
        return name
    # Fallback so unknown leagues still show up in the UI
    fallback = {1: "Calcio", 2: "Basket", 3: "Tennis", 11: "Ciclismo"}
    label = fallback.get(dc, f"Disciplina {dc}")
    return f"{label} (manifestazione {cc})"
```

## Discovery script (run periodically)

When SNAI changes the catalog, you can find new codes by hitting the top-match
endpoint and collecting distinct tuples. Save as `scripts/discover_snai_codes.py`:

```python
#!/usr/bin/env python3
"""Discover SNAI (codiceDisciplina, codiceManifestazione) tuples in current feed."""
import sys
from collections import defaultdict
sys.path.insert(0, "execution")
from dotenv import load_dotenv
load_dotenv(".env")
from snai_scraper import HEADERS, API_BASE, ENDPOINT_TOP_MATCH
from curl_cffi import requests

resp = requests.get(API_BASE + ENDPOINT_TOP_MATCH, headers=HEADERS,
                    impersonate="chrome136", timeout=20)
data = resp.json()

by_code = defaultdict(list)
for ev in data.get("avvenimentoFeList", []):
    key = (ev.get("codiceDisciplina"), ev.get("codiceManifestazione"))
    by_code[key].append(ev.get("descrizione"))

print("Distinct (codiceDisciplina, codiceManifestazione) in current top-match feed:\n")
for (cd, cm), matches in sorted(by_code.items()):
    print(f"  ({cd}, {cm}): {len(matches)} events")
    for m in matches[:2]:
        print(f"     - {m}")
    if len(matches) > 2:
        print(f"     ... ({len(matches) - 2} more)")
```

Run output (2026-06-08) showed only `(1, 765)` for calcio and the basketball/
tennis/cycling codes above. As soon as SNAI starts serving Serie A or other
domestic leagues, the script will reveal the new code → add it to
`SNAI_COMPETITION_MAP`.

## How to use the mapping in the scraper

In `parse_snai_data()`, add the code to the event dict:

```python
event = {
    "source": "snai",
    "event_id": f"snai-{pal}-{avv_code}",
    "match_code": f"{pal}-{avv_code}",
    "home_team": "",
    "away_team": "",
    "competition": "",
    "competition_code": avv.get("codiceManifestazione"),  # NEW
    "discipline": discipline.get(disc_code, "Sconosciuta"),
    "discipline_code": disc_code,                          # NEW
    "start_time": avv.get("data", ""),
    ...
}
```

In `store_in_db()`, resolve before INSERT:

```python
league_id = resolve_competition_name(
    ev.get("discipline_code"),
    ev.get("competition_code"),
)
if not league_id:
    league_id = ev.get("competition", "")
```

This way the DB always has a human-readable `league_id` (or the discoverable
`"Calcio (manifestazione 999)"` fallback) instead of empty string. Empty
`league_id` made matches invisible in the dashboard (which filters on the column).
