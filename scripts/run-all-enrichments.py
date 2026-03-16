#!/usr/bin/env python3
"""
Auto-resume enrichment runner — runs all enrichment scripts in sequence
until each reports scan complete for today.

Handles rate limiting with inter-batch delays and a max-iterations
safety valve to prevent runaway execution.

Usage:
  python scripts/run-all-enrichments.py                    # run all
  python scripts/run-all-enrichments.py --batch-size 200   # smaller batches
  python scripts/run-all-enrichments.py --sources subjects,gutenberg  # specific sources
  python scripts/run-all-enrichments.py --status           # show scan status only
"""

import subprocess
import sys
import time
from pathlib import Path

from enrichment_state import EnrichmentState

SCRIPTS_DIR = Path(__file__).parent

# Source → script mapping (order matters — subjects first since it's fastest)
ENRICHMENT_SOURCES = {
    "gap-filler": {
        "script": "enrich-gaps.py",
        "args": ["--field", "subjects"],
        "description": "Subjects from Open Library",
    },
    "gutenberg": {
        "script": "enrich-gutenberg.py",
        "args": [],
        "description": "Project Gutenberg free reading links",
    },
    "librivox": {
        "script": "enrich-librivox.py",
        "args": [],
        "description": "LibriVox free audiobook links",
    },
    "hathitrust": {
        "script": "enrich-hathitrust.py",
        "args": [],
        "description": "HathiTrust digitized texts",
    },
}

# Safety limits
MAX_ITERATIONS = 20  # Max loops before forced stop
INTER_BATCH_DELAY = 10  # Seconds between batches (rate limit courtesy)
DEFAULT_BATCH_SIZE = 500


def show_status() -> None:
    """Display current scan status for all sources."""
    all_state = EnrichmentState.load_all()
    print(f"\n{'Source':<15} {'Scanned':>8} {'Matched':>8} {'Date':<12} {'Last Slug':<30}")
    print("-" * 75)
    for source, info in ENRICHMENT_SOURCES.items():
        s = all_state.get(source, {})
        scanned = s.get("total_scanned", 0)
        matched = s.get("total_matched", 0)
        scan_date = s.get("scan_date", "never")
        last = s.get("last_scanned_slug", "")[:28]
        total = s.get("total_books", "?")
        print(f"{source:<15} {scanned:>8} {matched:>8} {scan_date:<12} {last:<30}")
    print()


def run_source(source: str, info: dict, batch_size: int) -> bool:
    """Run one enrichment script. Returns True if it had work to do."""
    state = EnrichmentState(source)
    if state.is_complete:
        print(f"  [{source}] ✓ Already complete for today")
        return False

    script = SCRIPTS_DIR / info["script"]
    cmd = [sys.executable, str(script), "--limit", str(batch_size)] + info["args"]

    print(f"  [{source}] Running {info['script']} --limit {batch_size}...")
    result = subprocess.run(cmd, cwd=str(SCRIPTS_DIR.parent))

    if result.returncode != 0:
        print(f"  [{source}] ✗ Script exited with code {result.returncode}")
        return False

    # Check if complete after run
    state_after = EnrichmentState(source)
    if state_after.is_complete:
        print(f"  [{source}] ✓ Scan complete!")
        return False

    return True  # More work to do


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Run all enrichment scripts to completion")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--sources", type=str, help="Comma-separated source names")
    parser.add_argument("--status", action="store_true", help="Show status only")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    # Filter sources if specified
    sources = ENRICHMENT_SOURCES
    if args.sources:
        requested = set(args.sources.split(","))
        sources = {k: v for k, v in sources.items() if k in requested}

    print(f"Running {len(sources)} enrichment sources (batch size: {args.batch_size})")
    print(f"Safety limits: max {MAX_ITERATIONS} iterations, {INTER_BATCH_DELAY}s between batches\n")

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"--- Iteration {iteration}/{MAX_ITERATIONS} ---")
        any_work = False

        for source, info in sources.items():
            had_work = run_source(source, info, args.batch_size)
            if had_work:
                any_work = True
                print(f"  Waiting {INTER_BATCH_DELAY}s before next source...")
                time.sleep(INTER_BATCH_DELAY)

        if not any_work:
            print("\n✓ All sources complete for today!")
            break

        print(f"\n  Waiting {INTER_BATCH_DELAY}s before next iteration...\n")
        time.sleep(INTER_BATCH_DELAY)
    else:
        print(f"\n⚠ Reached max iterations ({MAX_ITERATIONS}). Some sources may be incomplete.")

    print("\nFinal status:")
    show_status()


if __name__ == "__main__":
    main()
