#!/usr/bin/env python3
"""Discover SNAI (codiceDisciplina, codiceManifestazione) tuples in current feed.

Run when SNAI changes its catalog to find new league codes. Output is human-
readable and easy to paste into SNAI_COMPETITION_MAP in execution/snai_scraper.py.

Usage:
    python scripts/discover_snai_codes.py
    python scripts/discover_snai_codes.py --project-root /path/to/WinBet

Outputs:
    - Prints distinct (discipline, manifestazione) tuples with sample match names
    - Prints total events per discipline
    - Flags any codiceManifestazione NOT in the current SNAI_COMPETITION_MAP
"""
import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover SNAI competition codes")
    parser.add_argument("--project-root", default=".",
                        help="Path to WinBet project root (default: cwd)")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    execution = project_root / "execution"
    if not execution.exists():
        print(f"❌ execution/ not found at {execution}")
        return 1

    sys.path.insert(0, str(execution))
    try:
        from dotenv import load_dotenv
        load_dotenv(project_root / ".env")
        from snai_scraper import HEADERS, API_BASE, ENDPOINT_TOP_MATCH
    except ImportError as e:
        print(f"❌ Could not import snai_scraper: {e}")
        print("   Make sure dependencies are installed: pip install -r requirements.txt")
        return 1

    try:
        from curl_cffi import requests
    except ImportError:
        print("❌ curl_cffi not installed. Run: pip install curl-cffi")
        return 1

    print(f"📡 GET {API_BASE + ENDPOINT_TOP_MATCH}")
    resp = requests.get(
        API_BASE + ENDPOINT_TOP_MATCH,
        headers=HEADERS,
        impersonate="chrome136",
        timeout=20,
    )
    print(f"   Status: {resp.status_code}, size: {len(resp.content)} bytes")
    if resp.status_code != 200:
        print(f"❌ Non-200 response — API may be down or blocked")
        return 1

    data = resp.json()
    events = data.get("avvenimentoFeList", [])
    print(f"   Total events: {len(events)}\n")

    # Group by (codiceDisciplina, codiceManifestazione)
    by_code = defaultdict(list)
    by_discipline = defaultdict(int)
    for ev in events:
        cd = ev.get("codiceDisciplina")
        cm = ev.get("codiceManifestazione")
        by_code[(cd, cm)].append(ev.get("descrizione", ""))
        by_discipline[cd] += 1

    print("=" * 60)
    print("DISTINCT (codiceDisciplina, codiceManifestazione) TUPLES")
    print("=" * 60)
    for (cd, cm), matches in sorted(by_code.items()):
        print(f"\n  ({cd}, {cm}): {len(matches)} events")
        for m in matches[:3]:
            print(f"     - {m}")
        if len(matches) > 3:
            print(f"     ... ({len(matches) - 3} more)")

    print("\n" + "=" * 60)
    print("EVENTS BY DISCIPLINE")
    print("=" * 60)
    for cd, n in sorted(by_discipline.items()):
        print(f"  codiceDisciplina={cd}: {n} events")

    # Optional: compare to known SNAI_COMPETITION_MAP
    try:
        from snai_scraper import SNAI_COMPETITION_MAP
        known_keys = set(SNAI_COMPETITION_MAP.keys())
        observed_keys = set(by_code.keys())
        new_keys = observed_keys - known_keys
        if new_keys:
            print("\n" + "=" * 60)
            print("⚠ NEW CODES NOT IN SNAI_COMPETITION_MAP")
            print("=" * 60)
            print("Add these to SNAI_COMPETITION_MAP in execution/snai_scraper.py:\n")
            for cd, cm in sorted(new_keys):
                sample = by_code[(cd, cm)][0]
                print(f'    ({cd}, {cm}): "...",  # TODO: e.g. {sample!r}')
        else:
            print("\n✅ All observed codes are already in SNAI_COMPETITION_MAP")
    except ImportError:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
