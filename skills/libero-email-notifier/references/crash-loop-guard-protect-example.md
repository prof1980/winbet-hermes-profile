# Session Log: Crash Loop and Guard Self-Protection in WinBet Email Monitor

Date: 2026-06-09 ~11:30-11:45 UTC
Context: Hermes cron job checking on WinBet email monitor. Supervisor bash script with guard circuit breaker.

## Actual log excerpt (from `/mnt/c/Users/angel/WinBet/execution/winbet_email_handler.log`)

```
2026-06-09 05:55:55 [INFO] libero_notifier: Email inviata a watson.ag@libero.it | subject='RE: status'
2026-06-09 05:55:55 [INFO] libero_notifier: IMAP connesso a imapmail.libero.it:993
2026-06-09 05:55:55 [INFO] libero_notifier: Email 305 segnata come letta
2026-06-09 05:55:57 [GUARD] Monitor terminato con exit code 143 — riavvio tra 10s
2026-06-09 05:56:07 [GUARD] Trovato monitor attivo con PID 1844 — lo ucciderò prima di avviare nuovo
2026-06-09 05:56:09 [GUARD] Avvio monitor Python: execution/winbet_email_handler.py monitor --interval 300
2026-06-09 05:56:09 [INFO] libero_notifier: LiberoNotifier inizializzato per watson.ag@libero.it
...
2026-06-09 06:01:11 [INFO] libero_notifier: Email 353 segnata come letta
2026-06-09 06:07:23 [GUARD] Monitor terminato con exit code 143 — riavvio tra 10s
2026-06-09 06:07:33 [GUARD] Trovato monitor attivo con PID 2364 — lo ucciderò prima di avviare nuovo
2026-06-09 06:07:35 [GUARD] Avvio monitor Python: execution/winbet_email_handler.py monitor --interval 300
...
2026-06-09 06:08:12 [GUARD] Monitor terminato con exit code 143 — riavvio tra 10s
2026-06-09 06:08:22 [GUARD] Trovato monitor attivo con PID 2463 — lo ucciderò prima di avviare nuovo
2026-06-09 06:08:24 [GUARD] Avvio monitor Python: ...
2026-06-09 06:08:46 [GUARD] Avvio monitor Python: ...
2026-06-09 06:09:12 [GUARD] Monitor terminato con exit code 137 — riavvio tra 10s
2026-06-09 06:09:22 [GUARD] Trovato monitor attivo con PID 2620 — lo ucciderò prima di avviare nuovo
2026-06-09 06:09:24 [GUARD] Avvio monitor Python: ...
2026-06-09 06:10:05 [GUARD] Monitor terminato con exit code 137 — riavvio tra 10s
2026-06-09 06:10:15 [GUARD] Trovato monitor attivo con PID 2797 — lo ucciderò prima di avviare nuovo
2026-06-09 06:10:17 [GUARD] Avvio monitor Python: ...
2026-06-09 06:10:30 [GUARD] Monitor terminato con exit code 137 — riavvio tra 10s
2026-06-09 06:10:40 [GUARD] Trovato monitor attivo con PID 2866 — lo ucciderò prima di avviare nuovo
2026-06-09 06:10:42 [GUARD] Troppi riavvii rapidi (6). Fermato per sicurezza.
```

## Observations from this session

1. **Exit 143 (SIGTERM) pattern**: The process is being killed by another supervisor (likely a second cronjob or a second supervisor shell). The guard detects the old PID is still alive, kills it, then restarts.

2. **Escalation to exit 137 (SIGKILL)**: After the third cycle, the kill becomes more aggressive (-9 instead of -15). This suggests competing supervisors are fighting over the process.

3. **Guard circuit breaker triggers at 6 restarts**: Within ~3-4 minutes, 6 restarts occur. The guard correctly stops.

4. **Recovery happens hours later**: The log shows the guard restarts at 09:39 (3 hours later), suggesting a manual or external cronjob triggered a fresh start after the circuit breaker tripped.

5. **Current stable state**: At 11:37, a new process (PID 9141) was running for ~13 minutes under supervisor PID 9000, indicating the system recovered and stabilized.

## Pattern for future sessions

When investigating a "monitor not responding" report:
1. Always check the log for `[GUARD] Troppi riavvii rapidi` — if present, the guard is stopped and will NOT auto-restart.
2. Check `ps aux | grep supervisor` to see if there are multiple supervisor instances.
3. If the guard is stopped, the fix is manual: kill all monitor processes, remove PID file, restart ONE supervisor.
