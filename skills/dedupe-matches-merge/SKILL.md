---
name: dedupe-matches-merge
description: >
  Pattern riusabile per fondere partite duplicate in WinBet quando più bookmaker
  (SNAI, Eurobet, The Odds API, ecc.) inseriscono lo stesso evento con match_id
  diversi, leghe scritte in modo differente, e nomi squadra localizzati.
---

# Deduplica e Merge Partite Duplicati WinBet

## Quando usare

Quando più fonti (SNAI, Eurobet, The Odds API) salvano la stessa partita con `match_id` diversi nel DB WinBet. Sintomo: query come `SELECT home_team, away_team, match_date, COUNT(*) FROM matches GROUP BY ... HAVING COUNT(*) > 1` ritorna gruppi.

## Riferimenti utili in questa skill

- `references/winbet-sqlite-schema-actual.md` — schema DB WinBet reale, nomi colonne corretti (`league_id` non `league`, `odds_decimal` non `odds_value`, `errors` non `status`, `recorded_at` non `created_at`), struttura JSON `selections` nei surebets. **Leggi PRIMA di scrivere query.**

## Problema tipico

- **SNAI**: `league_id='Amichevoli Internazionali'`, nomi italiani ("Spagna", "Perù", "Stati Uniti")
- **Eurobet**: `league_id='Amichevoli Nazionali'`, nomi italiani ("Spagna", "Perù")
- **The Odds API**: `league_id='FIFA World Cup'`, nomi inglesi ("Spain", "Peru", "USA")
- **Eurobet mondiali**: `league_id='Mondiali 2026'`, nomi italiani

→ Stessa partita, **3-4 record diversi** nel DB con quote distribuite.

## Procedura di Merge

### 1. Backup pre-merge (SEMPRE)
```python
import shutil
shutil.copy("/path/to/winbet.db", "/tmp/winbet_pre_merge.db")
```

### 2. Definire equivalenze leghe
```python
LEAGUE_EQUIVALENCES = {
    "Amichevoli Internazionali": "Amichevoli Nazionali",
    "Amichevoli Nazionali": "Amichevoli Nazionali",  # canonica
    "Mondiali 2026": "FIFA World Cup",
    "FIFA World Cup": "FIFA World Cup",  # canonica
}
```

### 3. Definire mappatura nomi squadre localizzati
File: `execution/team_normalize.json` (o dict Python). Formato:
```python
TEAM_NORMALIZE = {
    # Eurobet/SNAI italiano -> The Odds API inglese
    "messico": "mexico",
    "sudafrica": "south africa",
    "stati uniti": "usa",
    "bosnia-erzegovina": "bosnia & herzegovina",
    "repubblica di corea": "south korea",
    "repubblica ceca": "czech republic",
    "capo verde": "cabo verde",
    "costa d'avorio": "ivory coast",
    "olanda": "netherlands",
    "paesi bassi": "netherlands",
    "arabia saudita": "saudi arabia",
    "emirati": "united arab emirates",
    "emirati arabi uniti": "united arab emirates",
    "cambogia u23": "cambodia u23",
    "perù": "peru",
    # ... molte altre
}
```

### 4. Funzione di normalizzazione
```python
def normalize_team(name):
    n = name.strip().lower()
    n = n.replace("'", "").replace("'", "").replace("`", "")
    n = " ".join(n.split())
    return TEAM_NORMALIZE.get(n, n)
```

### 5. Trova gruppi duplicati
```python
from collections import defaultdict
groups = defaultdict(list)
for m in all_matches:
    h = normalize_team(m[2])
    a = normalize_team(m[3])
    league_canon = LEAGUE_EQUIVALENCES.get(m[1], m[1])
    key = (h, a, m[4], league_canon)  # squadre normalizzate + data + lega canonica
    groups[key].append(m)
duplicates = {k: v for k, v in groups.items() if len(v) > 1}
```

### 6. Scegli match canonico per ogni gruppo
Criterio: **quello con più quote**.
```python
counts = []
for m in matches:
    c.execute("SELECT COUNT(*) FROM odds WHERE match_id = ?", (m[0],))
    counts.append((m[0], c.fetchone()[0], m))
counts.sort(key=lambda x: -x[1])  # più quote prima
canonical_id = counts[0][0]
duplicates_ids = [x[0] for x in counts[1:]]
```

### 7. Merge quote (mantieni la migliore per duplicati)
```python
for dup_id in duplicates_ids:
    c.execute("SELECT bookmaker_id, market_type, selection_name, selection_label, "
              "odds_value, odds_decimal, scraped_at, updated_at "
              "FROM odds WHERE match_id = ?", (dup_id,))
    for odd in c.fetchall():
        bookmaker, market, sel_name, sel_label, odds_val, odds_dec, scraped, updated = odd
        c.execute("""
            SELECT id, odds_decimal FROM odds
            WHERE match_id = ? AND bookmaker_id = ? AND market_type = ? AND selection_name = ?
        """, (canonical_id, bookmaker, market, sel_name))
        ex = c.fetchone()
        if ex:
            ex_id, ex_dec = ex
            if odds_dec and ex_dec and odds_dec > ex_dec:
                c.execute("UPDATE odds SET odds_decimal = ? WHERE id = ?", (odds_dec, ex_id))
        else:
            c.execute("""INSERT INTO odds (match_id, bookmaker_id, market_type, selection_name,
                          selection_label, odds_value, odds_decimal, scraped_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (canonical_id, bookmaker, market, sel_name, sel_label,
                       odds_val, odds_dec, scraped, updated))
```

### 8. Trasferisci anche odds_history e surebets
- `odds_history`: INSERT IGNORE su (match_id, bookmaker_id, market_type, selection_name, recorded_at)
- `surebets`: UPDATE match_id + market_type, o DELETE se già presente

### 9. Elimina record duplicati
```python
c.execute("DELETE FROM odds WHERE match_id = ?", (dup_id,))
c.execute("DELETE FROM odds_history WHERE match_id = ?", (dup_id,))
c.execute("DELETE FROM matches WHERE match_id = ?", (dup_id,))
```

### 10. Commit e verifica
```python
conn.commit()

# Verifica nessun duplicato residuo
c.execute("""SELECT home_team, away_team, match_date, COUNT(*) FROM matches
             GROUP BY home_team, away_team, match_date HAVING COUNT(*) > 1""")
remaining = c.fetchall()
assert len(remaining) == 0, f"Duplicati residui: {remaining}"
```

## Pitfall

- **Mai merge senza backup**: il backup `/tmp/winbet_pre_merge.db` è essenziale per rollback
- **Quota migliore in caso di conflitto**: se due bookmaker hanno la stessa selezione ma quote diverse, mantieni la più alta (per massimizzare il profitto su surebet)
- **UNIQUE constraint su odds**: assicurati di fare INSERT con IGNORE-like logic, altrimenti errore "UNIQUE constraint failed"
- **Time zones**: se un bookmaker dà `2026-06-09 02:00` (Europe/Rome = UTC+2) e l'altro `2026-06-09 00:00` (UTC), sono la stessa partita — verifica con data completa + ora
- **match_id format diversi**: SNAI usa `snai-{pal}-{avv}`, Eurobet `eb_{pal}_{avv}`, The Odds API UUID. La normalizzazione non può basarsi su match_id
- **odds_history senza odds_decimal**: vecchie entry potrebbero non avere la colonna, controlla schema con `PRAGMA table_info(odds_history)`
- **surebets con selezioni JSON**: dopo merge, le selezioni fanno riferimento al nuovo match_id, non aggiornare le stringhe JSON interne (sono descrittive)

## Metriche di successo

- ✅ Zero partite duplicate post-merge (`HAVING COUNT(*) > 1` ritorna 0)
- ✅ Quote preservate (nessuna quota persa, anzi trasferite)
- ✅ Bookmaker per partita aumentato (es. Spagna-Perù: 1 bm → 2 bm)
- ✅ Surebet detection cross-bookmaker funzionante (es. rileverà mismatch SNAI vs Eurobet)

## Estensioni future

- **Match per orario**: aggiungere tolleranza ±1h per gestire timezone diversi
- **Fuzzy matching squadre**: usare `difflib.SequenceMatcher` per nomi scritti diversamente ("USA" vs "United States")
- **Auto-merge su insert**: trigger SQLite che chiama `merge_matches(new_match_id)` se trova duplicati
- **Refresh rate**: ri-eseguire il merge dopo ogni scrape (cron) per gestire partite aggiunte incrementalmente

## Seconda passata obbligatoria: normalizzazione market_type

Dopo il merge delle partite, eseguire SEMPRE una **seconda passata** per normalizzare i `market_type`. Le tre fonti (SNAI, Eurobet, The Odds API) usano nomenclature diverse per lo stesso mercato:

```python
MARKET_NORMALIZE = {
    "1x2": "1X2", "1X2": "1X2",
    "GG/NG": "GG/NG", "gol_nogol": "GG/NG",
    "U/O GOAL 2,5": "OU25", "U/O GOAL 2.5": "OU25", "over_under": "OU25",
    "doppia_chance": "DC",
    "market_30562": "HANDICAP",  # ipotesi — verificare mapping SNAI
    "h2h": "1X2",  # The Odds API h2h = 1X2 per WinBet
    "h2h_lay": "1X2_LAY",  # exchange betting, raro
    "totals": "OU25",  # The Odds API totals = over/under generico
}

# Per ogni coppia (vecchio, nuovo), trasferisci quote ed elimina duplicati
for old, new in MARKET_NORMALIZE.items():
    if old == new: continue
    c.execute("SELECT id, match_id, bookmaker_id, selection_name, odds_decimal, scraped_at "
              "FROM odds WHERE market_type = ?", (old,))
    for row in c.fetchall():
        oid, mid, bm, sel, dec, scraped = row
        # Controlla se esiste già (mid, bm, new, sel) — se sì, tieni il migliore
        c.execute("SELECT id, odds_decimal FROM odds "
                  "WHERE match_id = ? AND bookmaker_id = ? AND market_type = ? AND selection_name = ?",
                  (mid, bm, new, sel))
        ex = c.fetchone()
        if ex:
            ex_id, ex_dec = ex
            if dec and ex_dec and dec > ex_dec:
                c.execute("UPDATE odds SET odds_decimal = ? WHERE id = ?", (dec, ex_id))
            c.execute("DELETE FROM odds WHERE id = ?", (oid,))
        else:
            c.execute("UPDATE odds SET market_type = ? WHERE id = ?", (new, oid))

# Stessa cosa per odds_history e surebets (stesse colonne market_type)
# ⚠️ odds_history NON ha colonna selection_label (controlla schema con PRAGMA)
```

**Perché serve**: dopo il merge, la dashboard mostra "1X2" per SNAI/Eurobet ma "h2h" per The Odds API. Senza normalizzazione, surebet detection cross-bookmaker non riesce a fare match (es. quota SNAI 1X2 vs The Odds API h2h sono la stessa cosa ma appaiono come mercati diversi).

## Schema DB WinBet — colonne da conoscere

Il DB WinBet ha schema non-standard in alcuni punti. Mappatura osservata (vedi anche `references/winbet-sqlite-schema-gotchas.md`):

| Tabella | Colonne critiche | Gotcha |
|---|---|---|
| `matches` | `league_id` (NON `league`) | Contiene direttamente il nome leggibile |
| `odds` | `odds_decimal` (NON `odds_value` come colonna primaria per display) | ENIQUE constraint su (match_id, bookmaker_id, market_type, selection_name) |
| `odds_history` | `recorded_at` (NON `created_at`/`scraped_at`) | NON ha `odds_decimal` né `selection_label` |
| `scrape_log` | `errors` (NON `status`) | Successo = `errors IS NULL OR errors = ''` |
| `surebets` | `selections` (JSON TEXT) | Chiavi JSON: `selection`, `label`, `odds`, `bookmaker` |

**Prima di scrivere query**: eseguire sempre `PRAGMA table_info(table_name)` per verificare lo schema reale. Il codice dead ("no such column: X") è un sintomo classico di mismatch tra query scritta e schema reale.

## Script CLI pronto all'uso

Lo script completo con CLI `--dry-run` e `--backup` è in:
```
winbet/execution/dedupe_matches.py
```

Per adattarlo a un altro progetto, copia `scripts/dedupe_matches.py.template` (in questa skill) nel tuo `execution/` e modifica:
- `DB_PATH` → path al tuo SQLite
- `LEAGUE_EQUIVALENCES` → mappa leghe del tuo dominio
- `TEAM_NORMALIZE` → nomi squadra localizzati del tuo dominio
- `MARKET_NORMALIZE` → varianti nomi mercato

Uso:
```bash
# Preview senza modifiche
./venv/bin/python execution/dedupe_matches.py --dry-run

# Esegui merge con backup automatico
./venv/bin/python execution/dedupe_matches.py --backup
```

Lo script contiene:
- Backup automatico a `/tmp/winbet_pre_merge.db`
- Trova gruppi duplicati con chiave `(squadre_normalizzate, data, lega_canonica)`
- Sceglie canonico = quello con più quote
- Merge quote con regola "mantieni la migliore in caso di conflitto"
- Trasferisce odds_history (con check su colonne mancanti) e surebets
- Verifica finale `HAVING COUNT(*) > 1` ritorna 0
- Stampa statistiche (n. quote trasferite, n. partite eliminate, n. gruppi fusi)
