# WinBet DB Schema — Gotchas Osservati in Produzione

Riferimento rapido per debug di query SQLite nel progetto WinBet.
Pattern collaudati durante merge di 42 partite duplicate cross-bookmaker
(148 → 106 partite, 2517 quote preservate, 0 duplicati residui).

## Comando diagnostico da eseguire SEMPRE prima di scrivere query

```python
import sqlite3
conn = sqlite3.connect("/mnt/c/Users/angel/WinBet/winbet.db")
c = conn.cursor()

# 1. Schema di una tabella
c.execute("PRAGMA table_info(<table_name>)")
for col in c.fetchall():
    print(f"  {col[1]} ({col[2]})")

# 2. Sample di righe
c.execute("SELECT * FROM <table_name> LIMIT 3")
for row in c.fetchall():
    print(repr(row))

# 3. Cerca duplicati (post-merge verification)
c.execute("""
    SELECT home_team, away_team, match_date, COUNT(*) as n
    FROM matches
    GROUP BY home_team, away_team, match_date
    HAVING n > 1
""")
```

## Tabelle critiche e gotchas

### `matches`

| Colonna | Tipo | Note |
|---|---|---|
| `id` | INTEGER | PK autoincrement |
| `match_id` | TEXT | Identificativo esterno (es. `snai-36241-6645`, `eb_36241_14693`, `toa_<uuid>`) — UNIQUE |
| `league_id` | TEXT | **NON `league`**. Contiene il nome leggibile ("FIFA World Cup", "Amichevoli Nazionali") |
| `home_team`, `away_team` | TEXT | Nomi localizzati (italiano per SNAI/Eurobet, inglese per The Odds API) |
| `match_date` | TEXT | ISO date `YYYY-MM-DD` |
| `match_time` | TEXT | `HH:MM` — può essere vuoto per alcune fonti |
| `status` | TEXT | "scheduled", "live", "finished" |

**Pattern di merge cross-bookmaker**:
```python
# Mappa league non canoniche -> canoniche
LEAGUE_EQUIVALENCES = {
    "Amichevoli Internazionali": "Amichevoli Nazionali",
    "Mondiali 2026": "FIFA World Cup",
}
# Mappa nomi squadra IT/EN
TEAM_NORMALIZE = {
    "messico": "mexico", "sudafrica": "south africa",
    "stati uniti": "usa", "bosnia-erzegovina": "bosnia & herzegovina",
    # ... ~80 entry vedi execution/dedupe_matches.py
}

# Chiave di raggruppamento
key = (normalize_team(home), normalize_team(away), date, canonical_league(league))
```

### `odds`

| Colonna | Tipo | Note |
|---|---|---|
| `id` | INTEGER | PK |
| `match_id` | TEXT | FK matches.match_id |
| `bookmaker_id` | TEXT | es. "snai", "eurobet", "pinnacle" |
| `market_type` | TEXT | "1X2", "GG/NG", "OU25", "DC", "HANDICAP" — **DOPO normalizzazione** |
| `selection_name` | TEXT | "1", "X", "2", "GOAL", "NOGOAL", "OVER", "UNDER" |
| `selection_label` | TEXT | "Casa", "Pareggio", "Trasferta", "Over 1.5" |
| `odds_value` | REAL | Quota in centesimi (es. 108 = 1.08) per SNAI/Eurobet, decimale per The Odds API |
| `odds_decimal` | REAL | Quota decimale (es. 1.08) — colonna canonica per display |
| `scraped_at`, `updated_at` | TEXT | ISO timestamp |

**Constraint UNIQUE**: `(match_id, bookmaker_id, market_type, selection_name)`.

Per INSERT sicuri dopo merge, fare sempre pre-check con SELECT:
```python
c.execute("SELECT id FROM odds WHERE match_id = ? AND bookmaker_id = ? "
          "AND market_type = ? AND selection_name = ?",
          (mid, bm, mkt, sel))
if not c.fetchone():
    # INSERT
```

### `odds_history`

| Colonna | Tipo | Note |
|---|---|---|
| `id` | INTEGER | PK |
| `match_id` | TEXT | FK |
| `bookmaker_id` | TEXT | |
| `market_type` | TEXT | |
| `selection_name` | TEXT | |
| `odds_value` | REAL | **NON ha `odds_decimal`** |
| `recorded_at` | TEXT | ISO timestamp — **NON `created_at` o `scraped_at`** |

**⚠️ Quando si fa merge tra `odds` e `odds_history`, le colonne differiscono.** Non cercare di fare `INSERT INTO odds_history ... SELECT ... FROM odds` con tutte le colonne — `selection_label` e `odds_decimal` non esistono lì.

### `scrape_log`

| Colonna | Tipo | Note |
|---|---|---|
| `id` | INTEGER | PK |
| `bookmaker_id` | TEXT | |
| `league_id` | TEXT | |
| `matches_found` | INTEGER | |
| `odds_found` | INTEGER | |
| `started_at`, `completed_at` | TEXT | |
| `errors` | TEXT | **NON ha colonna `status`**. Successo = `errors IS NULL OR errors = ''` |

Per contare scrape riusciti:
```sql
SELECT COUNT(*) FROM scrape_log WHERE errors IS NULL OR errors = '';
```

### `surebets`

| Colonna | Tipo | Note |
|---|---|---|
| `id` | INTEGER | PK |
| `match_id` | TEXT | FK |
| `market_type` | TEXT | es. "1X2", "gng", "ou15" — **pre-normalizzazione!** contiene varianti |
| `selections` | TEXT | **JSON serializzato**. Struttura: `[{"selection": "1", "label": "Casa", "odds": 7.96, "bookmaker": "eurobet"}, ...]` |
| `profit_percent` | REAL | |
| `total_implied_prob` | REAL | |
| `detected_at` | TEXT | |
| `notified` | INTEGER | 0/1 |
| `status` | TEXT | "active" / "expired" |

**Chiavi JSON osservate in `selections`**: la chiave è `selection` (NON `outcome`), il label leggibile è `label`. Esempio reale dal DB:
```json
[
  {"selection": "1", "label": "Casa", "odds": 7.96, "bookmaker": "eurobet"},
  {"selection": "2", "label": "Trasferta", "odds": 5.4, "bookmaker": "oddsportal"},
  {"selection": "X", "label": "Pareggio", "odds": 6.22, "bookmaker": "oddsportal"}
]
```

Per estrarre in query:
```python
import json
c.execute("SELECT selections FROM surebets WHERE ...")
sels_json = c.fetchone()[0]
sels = json.loads(sels_json)
for s in sels:
    label = s.get("label", s.get("selection", s.get("outcome", "?")))
    odds = s.get("odds", 0)
    bookmaker = s.get("bookmaker", "?")
```

## Verifica post-merge

Dopo qualsiasi merge o normalizzazione:
```sql
-- Conta duplicati
SELECT home_team, away_team, match_date, COUNT(*)
FROM matches
GROUP BY home_team, away_team, match_date
HAVING COUNT(*) > 1;
-- Deve ritornare 0 righe

-- Conta mercati non normalizzati
SELECT market_type, COUNT(*) FROM odds
GROUP BY market_type
ORDER BY COUNT(*) DESC;
-- Deve mostrare solo i market_type canonici (1X2, GG/NG, OU25, DC, HANDICAP, h2h, h2h_lay, totals)
```

## Quando una colonna sembra mancare

Errore tipo `sqlite3.OperationalError: no such column: X`:
1. Non assumere — esegui `PRAGMA table_info(table_name)`
2. Controlla se la colonna ha un nome simile (es. `odds_value` vs `odds_decimal`, `errors` vs `status`, `recorded_at` vs `created_at`)
3. In schema DB legacy/vintage, i nomi possono essere inconsistenti tra tabelle simili (`odds` vs `odds_history` hanno colonne diverse)

## Cronjob e monitoring

Le tabelle `notifications` e `scrape_log` sono popolate dai cronjob. Per audit:
```sql
-- Ultimi 10 scrape per bookmaker
SELECT bookmaker_id, MAX(completed_at) as last, errors
FROM scrape_log
GROUP BY bookmaker_id
ORDER BY last DESC
LIMIT 10;
```
