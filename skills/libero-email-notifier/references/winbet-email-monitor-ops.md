# WinBet Email Monitor — Checklist Operativa

Riferimento operativo per il monitor IMAP/SMTP del progetto WinBet. Utile come template per qualsiasi monitor email con supervisor bash.

## Stato processi

```bash
# Supervisor e monitor
ps aux | grep -E "supervisor_bg|winbet_email_handler" | grep -v grep

# Solo il monitor Python
pgrep -f "winbet_email_handler.py monitor"

# PID file (stale lock detection)
cat /mnt/c/Users/angel/WinBet/execution/.winbet_email_handler.pid
ps -p $(cat /mnt/c/Users/angel/WinBet/execution/.winbet_email_handler.pid) -o pid,etime,cmd
```

## Log principali

| File | Contenuto |
|---|---|
| `logs/monitor_supervisor_YYYYMMDD.log` | Supervisor: avvio, riavvio, errori |
| `logs/winbet_email_monitor.log` | Monitor: connessioni IMAP, comandi ricevuti |
| `logs/winbet_email.log` | Vecchio file log del loop di riavvio (crash loop) |
| `logs/supervisor_YYYYMMDD.log` | Altro supervisor legacy |

Comando rapido:
```bash
tail -n 50 logs/monitor_supervisor_$(date +%Y%m%d).log
tail -n 50 logs/winbet_email_monitor.log
```

## Health-check IMAP (una tantum)

```python
import sys, logging
sys.path.insert(0, '/mnt/c/Users/angel/WinBet/execution')
logging.basicConfig(level=logging.WARNING)
from libero_notifier import LiberoNotifier
n = LiberoNotifier()
msgs = n.fetch_inbox(unseen_only=True, limit=20)
print(f"Nuove email non lette: {len(msgs)}")
for m in msgs:
    print(f"  - Da: {m.from_addr} | Oggetto: {m.subject}")
```

Salva come `execution/check_inbox_tmp.py` ed esegui:
```bash
cd /mnt/c/Users/angel/WinBet && ./venv/bin/python execution/check_inbox_tmp.py
```

## Architettura supervisione

```
┌────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│ supervisor_bg.sh   │──▶  │ winbet_email_handler│──▶  │ IMAP/SMTP Libero.it │
│ (PID 99282)        │     │ (PID variabile)     │     │ watson.ag@libero.it │
│ loop ogni 60s      │     │ poll ogni 300s      │     │                     │
│ riavvia se morto   │     │ esegue comandi DB   │     │                     │
└────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

Il supervisor **non** usa `nohup` internamente: il monitor è un processo figlio dello shell del supervisor. Se il supervisor muore, il monitor continua a girare (non c'è SIGHUP perché nohup lo shielda), ma il riavvio automatico si ferma.

## Pattern: verifica PID prima di avviare (anti-duplicazione)

Quando un cronjob Hermes deve garantire che il monitor sia sempre attivo, **non avviare ciecamente**: prima controlla se esiste già un processo sano.

### Comando di verifica
```bash
PID=$(cat /path/to/.monitor.pid 2>/dev/null)
if [ -n "$PID" ] && ps -p "$PID" -o pid= >/dev/null 2>&1; then
    echo "Monitor già attivo (PID $PID) — skip avvio"
    exit 0
fi
# Se arriviamo qui, il processo è morto o il PID file è stale → avvia
```

### Cosa accade se si salta il check
- Il cronjob avvia una seconda istanza del monitor Python
- Entrambe fanno IMAP polling sulla stessa inbox → race condition su `mark_as_read`
- Entrambe possono rispondere alla stessa email → doppie risposte all'utente
- Consumo doppio di connessioni IMAP/SMTP verso Libero.it (risk rate-limit)
- PID file sovrascritto con il nuovo PID, rendendo difficile tracciare il processo originale

### Recovery se duplicato
```bash
# 1. Trova tutti i processi
pgrep -f "winbet_email_handler.py monitor" -a

# 2. Identifica il più vecchio (quello sano) e i duplicati
ps -eo pid,lstart,cmd | grep winbet_email_handler | grep -v grep

# 3. Uccidi i duplicati (i più recenti), mantieni il più vecchio
kill <PID_DUPLICATO1> <PID_DUPLICATO2>

# 4. Aggiorna il PID file con il PID sano
echo <PID_SANO> > /path/to/.monitor.pid
```

---

## Crash loop e guard self-protection

Quando un supervisor shell avvia un processo Python long-running, un pattern comune è il **crash loop** seguito dal **fermo di sicurezza del guard**.

### Sintomo nei log

```
[GUARD] Monitor terminato con exit code 143 — riavvio tra 10s
[GUARD] Trovato monitor attivo con PID 1237 — lo ucciderò prima di avviare nuovo
[GUARD] Avvio monitor Python: ...
...
[GUARD] Monitor terminato con exit code 137 — riavvio tra 10s
...
[GUARD] Troppi riavvii rapidi (6). Fermato per sicurezza.
```

### Significato degli exit code

| Exit code | Causa tipica | Azione del guard |
|---|---|---|
| **143** | SIGTERM (kill -15) | Riavvia dopo 10s |
| **137** | SIGKILL (kill -9) | Riavvia dopo 10s |
| 1, 2, ... | Eccezione Python | Riavvia dopo 10s |

### Perché il guard si ferma

Il guard implementa un **circuit breaker** semplice: max 5 riavvii in 600s. Se il processo viene killato più volte in rapida successione, il guard assume che ci sia una condizione persistente (es. conflitto di porte, DB corrotto, dipendenza mancante) e **si ferma per evitare di spammare il sistema**.

### Root cause comuni

1. **Doppio supervisor**: un cronjob Hermes avvia un secondo supervisor mentre il primo è ancora attivo. Il nuovo supervisor uccide il vecchio processo Python (exit 143), avvia il suo, poi il vecchio supervisor uccide il nuovo → loop infinito di SIGTERM.
2. **OOM o resource limit**: il processo Python viene killato dal kernel (SIGKILL 137) per esaurimento memoria.
3. **IMAP idle timeout**: connessione IMAP bloccata, processo ucciso da un watchdog esterno.

### Diagnostica

```bash
# 1. Verifica se esiste più di un processo/supervisor
ps aux | grep -E "winbet_email_handler|supervisor|guard" | grep -v grep

# 2. Controlla chi ha killato il processo (WSL/Linux)
dmesg | grep -i "killed process" | tail -5

# 3. Verifica se il PID file è stale
cat /path/to/.monitor.pid
ps -p $(cat /path/to/.monitor.pid) -o pid,etime,cmd 2>/dev/null || echo "PID stale"
```

### Recovery manuale quando il guard è fermo

```bash
# 1. Uccidi tutti i processi orfani del monitor
pgrep -f "winbet_email_handler.py monitor" | xargs -r kill -9 2>/dev/null

# 2. Rimuovi il PID file stale
rm -f /path/to/.monitor.pid

# 3. Riavvia il supervisor da zero
nohup /path/to/supervisor.sh >/dev/null 2>&1 &
```

### Prevenzione

- **Un solo meccanismo di supervisione per processo**: se usi un supervisor shell con guard interno, NON avviare anche un cronjob Hermes che tenta di riavviare lo stesso processo. Usa il cronjob solo per health-check passivi (report di stato), mai per riavvio forzato.
- **Intervallo di polling conservativo**: 300s (5 min) per IMAP è abbastanza reattivo e non stressa il server.
- **Singolo PID file**: tutti i meccanismi di avvio devono usare lo stesso `.monitor.pid` in modo che il guard possa rilevare duplicati.

---

## Pitfall operativi

1. **Doppio PID file stale**: se il monitor crasha senza rimuovere `.winbet_email_handler.pid`, il successivo avvio esce con "Monitor già in esecuzione". Il supervisor gestisce questo con `cleanup_stale()` che fa `rm -f` prima del riavvio.

2. **IMAP connesso ma nessun comando**: il log mostra solo `IMAP connesso a imapmail.libero.it:993` ripetuto → vuol dire che non ci sono email non lette, non che il monitor è rotto.

3. **Log rotazione manuale**: dopo settimane di uptime, `winbet_email_monitor.log` cresce indefinitamente. Sposta/rotazione:
   ```bash
   mv logs/winbet_email_monitor.log logs/winbet_email_monitor_$(date +%Y%m%d).log
   ```
   Il monitor ricrea il file append.

4. **Fusi orari**: le email IMAP sono UTC dal server; il subject del report ha la data locale del client che genera il report. Non c'è inconsistency, ma è utile sapere che `completed_at` nel DB è UTC.
