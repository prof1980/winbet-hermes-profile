# HTML Email Report Styling — Patterns riusabili

Reference concreta per `render_html_report()` in progetti che generano report automatici via email. Estratta dall'esperienza WinBet (Giugno 2026) — inviati a `angelo.bruno80@gmail.com` ogni mattina alle 8:00.

## CSS inline minimo per email HTML

Le email HTML richiedono CSS inline-friendly (no external stylesheet, no `&lt;style&gt;` blocks in alcune caselle come Outlook desktop). Il pattern "hybrid" usato da WinBet:

```html
&lt;!DOCTYPE html&gt;
&lt;html&gt;&lt;head&gt;&lt;meta charset="utf-8"&gt;
&lt;style&gt;
    body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 0 auto;
           padding: 20px; background: #f5f5f5; color: #333; }
    .header { background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
              color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
    .header h1 { margin: 0; font-size: 24px; }
    .header .meta { opacity: 0.9; font-size: 14px; margin-top: 5px; }
    .card { background: white; padding: 15px 20px; border-radius: 8px;
            margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .card h2 { margin-top: 0; font-size: 18px; color: #1e3a8a; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
    th { background: #f8fafc; font-weight: 600; color: #1e3a8a; }
    .stat { display: inline-block; margin-right: 30px; }
    .stat-label { font-size: 12px; color: #64748b; text-transform: uppercase; }
    .stat-value { font-size: 24px; font-weight: bold; color: #1e3a8a; }
    .profit { color: #16a34a; font-weight: bold; }
    .profit-high { color: #dc2626; font-weight: bold; }
    .footer { text-align: center; color: #64748b; font-size: 12px; margin-top: 30px; }
&lt;/style&gt;
&lt;/head&gt;&lt;body&gt;
```

## Stat boxes (KPI in una riga)

```python
stats_html = f"""
&lt;div style="display: flex; flex-wrap: wrap; gap: 20px; margin: 15px 0;"&gt;
    &lt;div class="stat"&gt;
        &lt;div class="stat-label"&gt;Partite&lt;/div&gt;
        &lt;div class="stat-value"&gt;{stats.get('total_matches', 0)}&lt;/div&gt;
    &lt;/div&gt;
    &lt;div class="stat"&gt;
        &lt;div class="stat-label"&gt;Quote&lt;/div&gt;
        &lt;div class="stat-value"&gt;{stats.get('total_odds', 0):,}&lt;/div&gt;
    &lt;/div&gt;
    &lt;div class="stat"&gt;
        &lt;div class="stat-label"&gt;Surebet&lt;/div&gt;
        &lt;div class="stat-value"&gt;{stats.get('total_surebets', 0)}&lt;/div&gt;
    &lt;/div&gt;
    &lt;div class="stat"&gt;
        &lt;div class="stat-label"&gt;Profittevoli (&ge;1%)&lt;/div&gt;
        &lt;div class="stat-value profit"&gt;{stats.get('surebets_profitable', 0)}&lt;/div&gt;
    &lt;/div&gt;
    &lt;div class="stat"&gt;
        &lt;div class="stat-label"&gt;Alta Priorit&agrave; (&ge;5%)&lt;/div&gt;
        &lt;div class="stat-value profit-high"&gt;{stats.get('surebets_high_profit', 0)}&lt;/div&gt;
    &lt;/div&gt;
&lt;/div&gt;
"""
```

## Tabella con riga per record

```python
rows = ""
for entry in data:
    profit_class = "profit-high" if entry["profit"] &gt;= 5 else "profit"
    rows += f"""
    &lt;tr&gt;
        &lt;td&gt;&lt;span class="{profit_class}"&gt;{entry['profit']:.2f}%&lt;/span&gt;&lt;/td&gt;
        &lt;td&gt;{entry['name']}&lt;/td&gt;
        &lt;td&gt;{entry['market']}&lt;/td&gt;
        &lt;td&gt;&lt;small&gt;{entry['detail']}&lt;/small&gt;&lt;/td&gt;
    &lt;/tr&gt;
    """

html_table = f"""
&lt;table&gt;
    &lt;thead&gt;
        &lt;tr&gt;&lt;th&gt;Profitto&lt;/th&gt;&lt;th&gt;Evento&lt;/th&gt;&lt;th&gt;Mercato&lt;/th&gt;&lt;th&gt;Note&lt;/th&gt;&lt;/tr&gt;
    &lt;/thead&gt;
    &lt;tbody&gt;{rows or '&lt;tr&gt;&lt;td colspan="4"&gt;Nessun dato&lt;/td&gt;&lt;/tr&gt;'}&lt;/tbody&gt;
&lt;/table&gt;
"""
```

## Pitfall con HTML in email

### `&lt;` e `&gt;` nei template literal

Quando generi HTML dentro un template literal Python, NON usare `&lt;` e `&gt;` come escape — quelli sono entit&agrave; HTML. Usa direttamente `<` e `>` come caratteri, MA assicurati che le `{}` expressions non contengano caratteri che confondono il parser f-string.

**Errore tipico**: scrivere in un file .md di documentazione `&lt;style&gt;` (escaped) pensando di mostrarlo come codice. In realt&agrave; in una f-string Python vera, devi usare i caratteri letterali:

```python
# CORRETTO (in codice Python reale):
html = f"&lt;tr&gt;&lt;td&gt;{value}&lt;/td&gt;&lt;/tr&gt;"

# In un .md che mostra codice Python, scrivi:
html = f"&lt;tr&gt;&lt;td&gt;{value}&lt;/td&gt;&lt;/tr&gt;"
# (i &lt; e &gt; sono letterali, non entit&agrave;)
```

### Subject con caratteri accentati

```python
# OK
subject = f"[WinBet] Report {datetime.now():%Y-%m-%d}"

# MEGLIO: includi il giorno in italiano per leggibilit&agrave;
from datetime import datetime
giorni = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
subject = f"[WinBet] Report {giorni[datetime.now().weekday()]} {datetime.now():%Y-%m-%d}"
# → [WinBet] Report venerdì 2026-06-05
```

### F-string e backslash

Le f-string Python NON ammettono `\` nell'expression part. Vedi `data-science/winbet-odds-pipeline` pitfall #12 (skill sezione Dashboard) per il workaround completo. Per HTML generation:

```python
# BAD: SyntaxError
html = f"&lt;a href='{url.replace('&', '&amp;')}'&gt;"

# GOOD: pre-processa
safe_url = url.replace('&', '&amp;')
html = f"&lt;a href='{safe_url}'&gt;link&lt;/a&gt;"
```

## Pattern di scheduling con cronjob

```bash
# Report giornaliero 8:00 UTC
hermes cronjob create --name "Daily Report 8:00" \
  --schedule "0 8 * * *" \
  --prompt "Esegui: cd /PROJ && ./venv/bin/python execution/daily_report.py --to DEST"

# Report settimanale (lunedì 9:00)
hermes cronjob create --name "Weekly Report" \
  --schedule "0 9 * * 1" \
  --prompt "Esegui: cd /PROJ && ./venv/bin/python execution/daily_report.py --to DEST --days 7"
```

Per ricevere il riepilogo in chat dopo l'invio automatico, l'opzione `deliver: "origin"` (default) recapita l'output dell'LLM del cronjob. Per recapito silenzioso (solo email, niente chat noise): `deliver: "local"`.

## Esempio completo: WinBet daily report

Il file `execution/winbet_daily_report.py` (17.5 KB) contiene:
- `collect_db_stats()`: 7 query SQLite per stato sistema
- `collect_system_health()`: disco + DB size + config
- `render_text_report()`: 100+ righe formattate con sezioni e tabelle ASCII
- `render_html_report()`: dual format con CSS inline, 6 sezioni
- CLI: `--to`, `--days`, `--subject-prefix`, `--dry-run`
- Sanitizzazione credenziali automatica (via LiberoNotifier)

Output tipico (testato 5 Giugno 2026):
```
======================================================================
📊 WINBET REPORT GIORNALIERO
📅 Generato: 2026-06-05 21:23:59 UTC
🗄️  Database: 199 partite, 3656 quote, 1088 surebet
======================================================================

🖥️  STATO SISTEMA
----------------------------------------------------------------------
  • Database: 117.22 MB
  • Disco libero: 935.9 GB (2.0% usato)
  • Intervallo scraping: 120 minuti
  • Bookmaker abilitati: snai, eurobet, goldbet, williamhill, sisal, lottomatica, bet365, oddsportal
  • Modalità: LIVE
  • Quote aggiornate oggi: 3126

💰 SUREBET RILEVATE
----------------------------------------------------------------------
  • Totale con profitto &gt;= 1%: 977
  • Totale con profitto &gt;= 5%: 70
  • Profitto massimo rilevato: 61.40%
```
