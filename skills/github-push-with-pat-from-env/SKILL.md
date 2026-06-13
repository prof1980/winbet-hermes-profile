---
name: github-push-with-pat-from-env
description: >
  Pattern per pubblicare un progetto su GitHub evitando che il PAT venga
  mascherato/redatto dalla chat AI. Il token deve essere letto dal filesystem
  (.env) perché ogni condivisione via chat viene automaticamente troncata.
  Include setup di auto-sync con cronjob.
---

# GitHub Push con PAT da .env

## Problema

Quando condividi un Personal Access Token GitHub in chat (o in log), il sistema
di sicurezza **maschera automaticamente** la parte centrale con `...`:

```
Token reale:    ghp_XX...XXXX  (40 char)
Token visibile: ghp_XX...XXXX                            (13 char) ← INUTILE
```

Il risultato: ogni push fallisce con 401 "Bad credentials" non perché il token
è sbagliato, ma perché è stato **troncato**.

## Soluzione

**Salvare il PAT in un file `.env` e leggerlo da lì** per ogni operazione git.

### Setup

```bash
# 1. Aggiungi al file .env
echo "GITHUB_PAT=ghp_XX...XXXX" >> /mnt/c/Users/angel/WinBet/.env
chmod 600 /mnt/c/Users/angel/WinBet/.env
```

### Script askpass che legge da .env

```bash
#!/bin/bash
# .git-askpass-helper.sh
case "$1" in
    *Username*|*username*) echo "x-access-token" ;;
    *Password*|*password*) grep "^GITHUB_PAT=" /mnt/c/Users/angel/WinBet/.env | cut -d= -f2 ;;
    *) echo "x-access-token" ;;
esac
```

### Push da terminale

```python
import subprocess
from pathlib import Path
import os

# 1. Crea askpass che legge da file (NON in chiaro)
askpass = repo / ".askpass.sh"
askpass.write_text(f"""#!/bin/bash
case "$1" in
    *Username*) echo "x-access-token" ;;
    *Password*) grep "^GITHUB_PAT=" /path/to/.env | cut -d= -f2 ;;
    *) echo "x-access-token" ;;
esac
""")
askpass.chmod(0o700)

env = os.environ.copy()
env["GIT_ASKPASS"] = str(askpass)
env["GIT_TERMINAL_PROMPT"] = "0"

# 2. Pull rebase (per gestire commit remoti)
subprocess.run(["git", "pull", "--rebase", "origin", "main"],
               cwd=repo, env=env, check=True)

# 3. Push
result = subprocess.run(
    ["git", "push", "origin", "main"],
    cwd=repo, env=env, capture_output=True, text=True
)
print(result.stdout, result.stderr)
```

## Push via API REST (alternativa)

Per bypassare del tutto `git push`, puoi usare le API REST:

```python
import requests
from pathlib import Path

# Leggi PAT da .env
for line in Path(".env").read_text().split("\n"):
    if line.startswith("GITHUB_PAT="):
        token = line.split("=", 1)[1].strip()
        break

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json"
}

# Crea repo
r = requests.post(
    "https://api.github.com/user/repos",
    headers=headers,
    json={
        "name": "my-repo",
        "description": "...",
        "private": False
    },
    timeout=15
)

# Upload file
import base64
content_b64 = base64.b64encode(content.encode()).decode()
r = requests.put(
    f"https://api.github.com/repos/user/my-repo/contents/{path}",
    headers=headers,
    json={
        "message": "Upload file",
        "content": content_b64
    },
    timeout=10
)
```

**Limite API**: 5000 richieste/ora per utente autenticato, 60/ora senza auth.

## Scope PAT richiesti

| Scope | Operazioni | Obbligatorio |
|---|---|---|
| `repo` | Push, pull, fetch, API read/write contenuti | ✅ SÌ |
| `workflow` | Aggiungere/modificare `.github/workflows/*.yml` | Solo per CI |
| `admin:org` | Gestire organization | Solo per org |
| `delete_repo` | Eliminare repository | Solo se necessario |

**Per il pattern WinBet**: `repo` + `workflow` (se vuoi GitHub Actions).

## Workaround per scope `workflow` mancante

Se il PAT non ha scope `workflow`, il push di `.github/workflows/*.yml` viene
rifiutato con:
```
! [remote rejected] main -> main (refusing to allow a Personal Access Token
to create or update workflow `.github/workflows/ci.yml` without `workflow` scope)
```

**Soluzioni**:
1. **Tenere il file CI in `docs/`** (non in `.github/workflows/`) come esempio
2. **Pushare via web**: GitHub web UI accetta workflow anche senza scope `workflow`
3. **Rigenerare il PAT** con scope `workflow` aggiunto
4. **Usare SSH keys** (hanno automaticamente permessi completi per le operation Git)

## Pattern auto-sync con cronjob

```bash
#!/bin/bash
# scripts/winbet_sync_github.sh
# Auto-sync WinBet → GitHub, schedulato oppure manuale

REPO_LOCAL="${WINBET_REPO_PATH:-/tmp/winbet-repo}"
SRC="${WINBET_SRC_PATH:-/mnt/c/Users/angel/WinBet}"
ENV_FILE="$SRC/.env"
LOG_FILE="$SRC/.tmp/sync.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# Verifica credenziali
[ -f "$ENV_FILE" ] || { log "❌ .env non trovato"; exit 1; }
GITHUB_PAT=$(grep "^GITHUB_PAT=" "$ENV_FILE" | cut -d= -f2 | tr -d '\n\r')
[ -n "$GITHUB_PAT" ] || { log "❌ GITHUB_PAT vuoto"; exit 1; }

# Sync
log "🔄 Sync $SRC → $REPO_LOCAL"
rsync -a --delete \
    --exclude='venv/' --exclude='__pycache__/' \
    --exclude='*.pyc' --exclude='*.db' --exclude='*.log' \
    --exclude='*.pid' --exclude='*.zip' \
    --exclude='.env' --exclude='dashboard.html' \
    "$SRC/execution/" "$REPO_LOCAL/execution/"

rsync -a --delete "$SRC/directives/" "$REPO_LOCAL/directives/" 2>/dev/null || true
rsync -a --delete "$SRC/config/" "$REPO_LOCAL/config/" 2>/dev/null || true

# Skills
for skill in bookmaker-odds-scraper dedupe-matches-merge \
            libero-email-notifier python-project-replication-package; do
    [ -d "$HOME/.hermes/skills/$skill" ] && rsync -a --delete \
        "$HOME/.hermes/skills/$skill/" "$REPO_LOCAL/skills/$skill/"
done

# Git
cd "$REPO_LOCAL"
git add -A
git diff --cached --quiet && { log "✅ Nessuna modifica"; exit 0; }

git commit -m "chore: auto-sync $(date '+%Y-%m-%d %H:%M:%S')"

# Push con URL embedded (più affidabile di askpass per cronjob)
PUSH_URL="https://x-access-token:${GITHUB_PAT}@github.com/prof1980/winbet-agent.git"
git push "$PUSH_URL" main 2>&1 | tee -a "$LOG_FILE"
```

### Schedulazione con Hermes cronjob

```bash
hermes cronjob create \
  --name "WinBet GitHub Auto-Sync" \
  --schedule "every 6h" \
  --no-agent \
  --script "winbet_sync_github.sh" \
  --workdir "/mnt/c/Users/angel/WinBet"
```

## Pitfall

- **PAT in chat viene mascherato**: scrivi nel .env e leggi da lì, MAI in chat
- **PAT `*** redatto durante i commit: lo script askpass deve leggere il .env, non ricevere il token come variabile
- **Scope `workflow` mancante**: workflow files devono essere in `docs/` o pushati via web
- **Force push con `*** --force-with-lease`: solo se sei sicuro che il remote non ha commit importanti
- **PAT scaduti**: 90 giorni default. Controlla la data di scadenza
- **PAT con troppi permessi**: meglio PAT separati per repo diversi (fine-grained)
- **GITHUB_TOKEN environment variable di GitHub Actions ≠ PAT**: nelle action, `secrets.GITHUB_TOKEN` è gestito da GitHub, non è il tuo PAT
- **Rate limit API**: 5000/ora autenticato, 60/ora non autenticato. Per upload massivo, meglio git push

## Verifica post-push

```python
import requests

r = requests.get("https://api.github.com/repos/USER/REPO")
data = r.json()
print(f"  Pushed: {data['pushed_at']}")
print(f"  Size: {data['size']} KB")
print(f"  Default branch: {data['default_branch']}")

# Verifica assenza secrets
r2 = requests.get(
    "https://api.github.com/repos/USER/REPO/git/trees/main?recursive=1"
)
files = [t['path'] for t in r2.json()['tree'] if t['type'] == 'blob']

sensitive = ['.env', '*.db', 'venv/', '__pycache__/', '*.log', '*.pid']
for pat in sensitive:
    matches = [f for f in files if pat in f and pat != '.env.example']
    if matches:
        print(f"  ❌ {pat}: {len(matches)} file TROVATI")
    else:
        print(f"  ✅ {pat}: 0 file")
```

## Riferimenti

- [GitHub PAT docs](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
- [GitHub Actions permissions](https://docs.github.com/en/actions/security-guides/automatic-token-authentication)
- [git-credential-store](https://git-scm.com/docs/git-credential-store)
