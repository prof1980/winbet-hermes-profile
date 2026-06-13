---
name: python-project-replication-package
description: >
  Produce a self-contained, redistributable ZIP of a Python project so it can be
  replicated on another machine in three commands. Use when the user asks to
  "package the project", "create a replica", "send a copy", "ship the codebase",
  or "make it installable elsewhere". Triggers on: replication requests, handoff
  to a new machine, archiving a working session, sending source to a colleague.
---

# Python Project Replication Package

A reproducible workflow for turning a working Python project into a self-contained
ZIP that another machine can `unzip → install.sh → .env` on. Covers the cleanup
rules, the boilerplate files (`.env.example`, `requirements.txt`, `install.sh`,
`REPLICA_SETUP.md`), the exclusion list, and the size budget. The workflow was
designed for `winbet/` but applies to any Python project with a venv, a `.env`,
and a SQLite DB.

## When to use

- User asks to package/ship/replicate/zip a project
- User wants to send "a copy of all the files" to another machine
- User mentions a fresh install on a new system
- Session ends with a working system that should be preserved for the future

## The 3-step workflow

### Step 1 — Cleanup (mandatory before zipping)

Strip every file that is regenerable, environment-specific, or sensitive.

| Category | Examples | Action |
|---|---|---|
| **Venv** | `venv/`, `.venv/`, `env/` | **Exclude** (241 MB for a typical project) |
| **Credentials** | `.env` | **Exclude** (ship `.env.example` instead) |
| **Database** | `*.db`, `*.sqlite`, `*.sqlite3` | **Exclude** (regenerated on first run) |
| **Cache** | `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.pytest_cache/` | **Exclude** |
| **Logs** | `*.log`, `logs/` | **Exclude** (or include only `logs/.gitkeep`) |
| **Temp/debug files** | `tmp/`, `debug_*.py`, `test_*.sh`, `inspect*.py` | **Exclude** |
| **Empty junk** | `1`, `WRAPPER_EOF`, zero-byte files | **Delete** |
| **Generated artifacts** | `dashboard.html` (regenerated), `*.jsonl`, build output | **Exclude** |

Use `find` or `search_files` to identify candidates, then `terminal(rm)` or
`write_file` to delete. Show the user a summary table before deleting so they
can object.

### Step 2 — Boilerplate (always include these 5 files)

Even if the project never had them, the ZIP must include:

1. **`README.md`** — updated with the current state (or a fresh project description if there is none).
2. **`REPLICA_SETUP.md`** — explicit 3-command setup for the new machine:
   ```bash
   unzip ProjectName_*.zip
   cd ProjectName
   ./install.sh
   # then: cp .env.example .env && nano .env
   ```
3. **`.env.example`** — every variable in `.env` with a placeholder value and a comment explaining what goes there. Never commit the real `.env`.
4. **`requirements.txt`** — every pip dep. Use `pip freeze > requirements.txt` against the working venv, or hand-curate if the project uses `# /// script` blocks.
5. **`install.sh`** — executable bash that:
   - Creates venv (`python3 -m venv venv`)
   - Installs deps (`pip install -r requirements.txt`)
   - Installs any system bits (`playwright install chromium`, etc.)
   - Creates `.env` from `.env.example` if missing
   - Creates output directories
   - Prints "next steps" with the test commands to verify the install

Optional but recommended:
- **`winbet_config.json` (or project equivalent)** — included with a sensible default (e.g. `mode: LIVE`) so the replica works without a config step.
- **Scripts directory** — keep at least one canonical entry-point script per CLI command the project exposes.

### Step 3 — Zip (with explicit exclusion list)

```python
import zipfile
from pathlib import Path

root = Path("/path/to/project")
zip_path = Path("/tmp/project_YYYYMMDD_HHMMSS.zip")

EXCLUDE_DIRS = {"venv", "__pycache__", ".git", ".tmp", "tmp", "node_modules",
                ".pytest_cache", ".mypy_cache", ".venv", "env", "logs"}
EXCLUDE_FILES = {".env", "*.db", "*.pyc", "*.log", ".DS_Store", "Thumbs.db"}
EXCLUDE_EXTENSIONS = {".pyc", ".db", ".log", ".tmp"}

def should_exclude(p: Path) -> bool:
    parts = set(p.relative_to(root).parts)
    if parts & EXCLUDE_DIRS: return True
    if p.name in EXCLUDE_FILES: return True
    if p.suffix in EXCLUDE_EXTENSIONS: return True
    if p.name.startswith(".") and p.name not in {".env.example", ".gitignore"}:
        return True
    return False

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for f in sorted(root.rglob("*")):
        if f.is_file() and not should_exclude(f):
            zf.write(f, f.relative_to(root))
```

Target size: **< 5 MB** after compression. A typical mid-size Python project
compresses to 100-500 KB. If the ZIP is > 10 MB, you forgot to exclude the
venv or DB.

## Pitfalls

### 1. Don't Skip the Cleanup

If you zip a project with `venv/` included, the result balloons to hundreds of
MB and the email fails. Always run the cleanup table first and verify with
`du -sh project/`.

### 2. Don't Ship Real Credentials in `.env.example`

`.env.example` is the single file most likely to be copied verbatim by a new
user. Use placeholder values like `your_api_key_here` or `***REDACTED***`,
never the real key. Document in a comment what value goes there.

### 3. Don't Forget `playwright install` etc.

If the project uses Playwright or other tooling that requires a post-install
step, `install.sh` must run it. `pip install -r requirements.txt` alone will
not download browser binaries.

### 4. Don't Use Markdown Headers in `install.sh` Comments That Look Like Commands

Users will copy-paste the `install.sh` examples from the README. Make the
shell script self-contained and the README examples match the script exactly.
Don't put a `bash` code block in the README that does something different
from `install.sh`.

### 5. Always Verify the ZIP After Creation

```python
import zipfile
with zipfile.ZipFile(zip_path) as zf:
    names = zf.namelist()
    assert ".env" not in names, "leaked .env!"
    assert not any(n.startswith("venv/") for n in names), "leaked venv!"
    assert not any(n.endswith(".db") for n in names), "leaked DB!"
    critical = ["README.md", ".env.example", "requirements.txt", "install.sh"]
    for c in critical:
        assert any(c in n for n in names), f"missing {c}"
```

A 30-line verify script catches 90% of packaging mistakes before they ship.

## Self-Test

After building the package, run this checklist:

```bash
# 1. Check size
ls -lh project.zip   # should be < 5 MB

# 2. Check exclusion worked
unzip -l project.zip | grep -E "\.env$|venv/|\.pyc$|\.db$"  # should be empty

# 3. Check critical files
unzip -l project.zip | grep -E "README|requirements.txt|install.sh|.env.example"

# 4. Extract to temp and try install.sh
mkdir /tmp/replica-test && cd /tmp/replica-test
unzip /path/to/project.zip
./install.sh
# (then verify a quick command runs without import errors)
```

If the self-test passes, the package is ready to ship via email, USB, or git.

## Bundled Helpers

This skill ships with reusable code so you don't have to rewrite the zip-build
exclusion logic each time:

- `scripts/build_replication_package.py` — CLI that takes a project root and
  an output path, applies the standard exclusion set, writes the ZIP, and
  runs the verify pass (catches leaks of `.env`, `venv/`, `*.db`).
  Usage: `python scripts/build_replication_package.py /path/to/project /tmp/out.zip`
- `templates/install.sh.template` — annotated starter `install.sh` with
  customization points (`PYTHON_MIN`, `POST_INSTALL` array, `TEST_CMD`). Copy,
  edit, ship.

When a future session asks "zip this project for replication", run
`build_replication_package.py` and you're done in one command.
