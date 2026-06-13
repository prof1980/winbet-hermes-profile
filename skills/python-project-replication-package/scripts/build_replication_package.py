#!/usr/bin/env python3
"""Build a replication package (ZIP) of a Python project.

Self-contained: takes a project root and a destination path, applies the
standard exclusion list, writes the ZIP, and runs a verify pass.

Usage:
    python scripts/build_replication_package.py /path/to/project /tmp/out.zip
    python scripts/build_replication_package.py . /tmp/winbet.zip --dry-run
"""
import argparse
import sys
import zipfile
from pathlib import Path


# Standard exclusion set (see ../SKILL.md for rationale)
EXCLUDE_DIRS = {
    "venv", "__pycache__", ".git", ".tmp", "tmp", "node_modules",
    ".pytest_cache", ".mypy_cache", ".venv", "env", "logs",
    "dist", "build", "*.egg-info",
}
EXCLUDE_FILES = {
    ".env", "*.db", "*.pyc", "*.log", ".DS_Store", "Thumbs.db",
    "*.swp", "*.swo", "*~", "*.pid",
}
EXCLUDE_EXTENSIONS = {".pyc", ".db", ".log", ".tmp", ".pid", ".swp"}

# Files that MUST appear in the package
CRITICAL_FILES = {
    "README.md", "REPLICA_SETUP.md", "requirements.txt",
    "install.sh", ".env.example",
}


def should_exclude(p: Path, root: Path) -> bool:
    """Return True if path should be excluded from the ZIP."""
    try:
        parts = set(p.relative_to(root).parts)
    except ValueError:
        return True
    if parts & EXCLUDE_DIRS:
        return True
    if p.name in EXCLUDE_FILES:
        return True
    if p.suffix in EXCLUDE_EXTENSIONS:
        return True
    # Allow .env.example and .gitignore, exclude other dotfiles
    if p.name.startswith(".") and p.name not in {".env.example", ".gitignore"}:
        return True
    return False


def build_zip(project_root: Path, output: Path, dry_run: bool = False) -> int:
    project_root = project_root.resolve()
    if not project_root.exists():
        print(f"❌ Project root not found: {project_root}")
        return 1
    if not project_root.is_dir():
        print(f"❌ Not a directory: {project_root}")
        return 1

    candidates = sorted(
        f for f in project_root.rglob("*")
        if f.is_file() and not should_exclude(f, project_root)
    )

    # Verify critical files
    names = [f.relative_to(project_root).as_posix() for f in candidates]
    missing = []
    for c in CRITICAL_FILES:
        if not any(n == c or n.endswith(f"/{c}") for n in names):
            missing.append(c)
    if missing:
        print(f"⚠ Missing critical files: {missing}")
        print("  The package will still build, but replication will be harder.")

    # Compute size
    total_bytes = sum(f.stat().st_size for f in candidates)
    print(f"📦 Project: {project_root}")
    print(f"   Files to include: {len(candidates)}")
    print(f"   Uncompressed size: {total_bytes/1024:.1f} KB")
    print(f"   Output: {output}")

    if dry_run:
        print("\n[DRY-RUN] Would include these files:")
        for n in names[:30]:
            print(f"   {n}")
        if len(names) > 30:
            print(f"   ... ({len(names) - 30} more)")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in candidates:
            arcname = f.relative_to(project_root)
            zf.write(f, arcname)

    zip_size = output.stat().st_size
    ratio = (zip_size / total_bytes * 100) if total_bytes else 0
    print(f"\n✅ ZIP written: {output}")
    print(f"   Compressed size: {zip_size/1024:.1f} KB ({ratio:.1f}% of original)")

    if zip_size > 5 * 1024 * 1024:
        print(f"⚠ ZIP > 5 MB — check that venv/, .env, *.db were excluded")

    # Verify pass
    print("\n🔍 Verifying ZIP contents...")
    with zipfile.ZipFile(output) as zf:
        znames = zf.namelist()
        leaks = []
        for n in znames:
            if n == ".env" or n.endswith("/.env"):
                leaks.append(f"   ❌ LEAKED .env: {n}")
            if n.startswith("venv/") or "/venv/" in n:
                leaks.append(f"   ❌ LEAKED venv/: {n}")
            if n.endswith(".db"):
                leaks.append(f"   ❌ LEAKED .db: {n}")
        if leaks:
            for l in leaks:
                print(l)
            return 2
        else:
            print("   ✅ No .env, venv, or .db leaks detected")
            print(f"   ✅ {len(znames)} files in archive")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a replication ZIP of a Python project")
    parser.add_argument("project_root", help="Path to the project to package")
    parser.add_argument("output", help="Output ZIP path")
    parser.add_argument("--dry-run", action="store_true",
                        help="List files without creating the ZIP")
    args = parser.parse_args()

    return build_zip(
        Path(args.project_root),
        Path(args.output),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
