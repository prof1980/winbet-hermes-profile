# WinBet Email Monitor — Deployment Session 2026-06-09

Session cronjob: avvio del monitor email WinBet con supervisione continua.

## Scenario

Task: mantenere in esecuzione `winbet_email_handler.py monitor --interval 300` (IMAP polling del casella watson.ag@libero.it ogni 5 minuti). Se il processo termina, riavviarlo.

## Tentativo 1: esecuzione diretta in background (non ottimale)

```bash
cd /mnt/c/Users/angel/WinBet && ./venv/bin/python execution/winbet_email_handler.py monitor --interval 300
```

Avviato con `background=true`, PID 23749. Lo script crea un PID file `.winbet_email_handler.pid`. Monitor eseguito correttamente (connesso a imapmail.libero.it:993) ma:
- Process `proc_1c32df3dce48` era il monitor stesso (no supervisor separato)
- `process(action="log")` non mostrava output — stdout rediretto implicitamente? In realtà, il monitor NON produce output su stdout (usa solo `logging.FileHandler` o simile), rendendo il polling del processo inutile per il debug operativo.

Decisione: kill e passare al supervisor dedicato del progetto.

## Tentativo 2: supervisor script (`run_email_monitor.py`)

Lo script `run_email_monitor.py` era presente nella root del progetto:

```python
#!/usr/bin/env python3
CMD = ["./venv/bin/python", "execution/winbet_email_handler.py", "monitor", "--interval", "300"]
LOG = "/mnt/c/Users/angel/WinBet/email_handler.log"
PIDFILE = "/mnt/c/Users/angel/WinBet/email_handler.pid"
WORKDIR = "/mnt/c/Users/angel/WinBet"

def main():
    while True:
        with open(LOG, "a") as logf:
            logf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Avvio monitor...\n")
            proc = subprocess.Popen(CMD, cwd=WORKDIR,
                stdout=logf, stderr=subprocess.STDOUT, preexec_fn=os.setsid)
            write_pid(proc.pid)
            ret = proc.wait()
            logf.write(f"Processo terminato con codice {ret}. Riavvio tra 5s...\n")
        time.sleep(5)
```

Vantaggi rispetto all'esecuzione diretta:
- PID file `email_handler.pid` con il child PID (quello del monitor, facile kill)
- Log persistita su file (append), facile controllo stato
- Auto-riavvio su crash con 5 secondi di attesa
- Parent process è solo supervisor; il child gestisce IMAP e non interferisce con il terminale

Avvio:
```bash
cd /mnt/c/Users/angel/WinBet && ./venv/bin/python run_email_monitor.py
```

background=true, PID parent 23856. Child PID: 23869.

## Verifica stato operativo

File di log (`email_handler.log`) usato come ground truth:
```
[2026-06-09 23:24:42] Avvio monitor winbet_email_handler
PID 23869
2026-06-09 23:24:42 [INFO] libero_notifier: LiberoNotifier inizializzato per watson.ag@libero.it
2026-06-09 23:24:42 [INFO] winbet_email_handler: WinBetEmailHandler pronto (sender autorizzati: ['watson.ag@libero.it'])
2026-06-09 23:24:42 [INFO] libero_notifier: Avvio monitor inbox (intervallo: 300s)
2026-06-09 23:24:42 [INFO] libero_notifier: IMAP connesso a imapmail.libero.it:993
```

Dopo 40 secondi: processo ancora running (uptime_seconds 40). Database `winbet.db` presente (118M, aggiornato Jun 9 22:48).

## Stato finale consegnato

| Componente | PID | Ruolo |
|---|---|---|
| Supervisor (`run_email_monitor.py`) | 23856 | Loop infinito, riavvia child su crash |
| Monitor (`winbet_email_handler.py`) | 23869 | IMAP ogni 300s, callback comandi email |

- Email monitorato: watson.ag@libero.it via IMAP SSL
- Comandi supportati: status, surebet, matches, odds, stop, start, help
- DB attivo: winbet.db (118M)
- Log operativo: /mnt/c/Users/angel/WinBet/email_handler.log

## Lezione per sessioni future

1. **Cerca sempre uno script supervisor prima di backgroundare direttamente**: `run_email_monitor.py` è scritto specificamente per questo compito.
2. **Non fare affidamento su process(action="log")** quando il target scrive su file di log: ispeziona il file direttamente con `cat` / `tail`.
3. **Il monitor usa FileHandler** (non stdout), quindi il parent supervisor deve usare `stdout=logf, stderr=STDOUT` su un file persistente.
4. **Il PID del supervisor (parent) ≠ PID del monitor (child)**. Il file `email_handler.pid` contiene il child, quello che importa per il debug operativo.
