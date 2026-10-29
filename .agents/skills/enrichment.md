---
name: enrichment
description: Run and manage the book/author enrichment pipeline
triggers:
  - enrich
  - enrichment
  - scan books
  - run enrichment
  - fill gaps
---

# Enrichment Workflow

Run the tsundoku enrichment pipeline to fill data gaps across the book collection.

## Steps

### 1. Check current status

```bash
cd ~/git/tsundoku
python3 scripts/run-all-enrichments.py --status
python3 scripts/enrich-gaps.py --report
python3 scripts/enrich-copyright.py --report
```

Report the current scan positions and data gap percentages to the user.

### 2. Run enrichment

For a **full automated scan** (all sources, auto-resume):

```bash
python3 scripts/run-all-enrichments.py --batch-size 500
```

For **targeted enrichment** of specific gaps:

```bash
# Fill missing subjects (highest priority — enables category enrichment)
python3 scripts/enrich-gaps.py --limit 500 --field subjects

# Fill missing descriptions
python3 scripts/enrich-gaps.py --limit 200 --field description

# Scan for free reading links
python3 scripts/enrich-gutenberg.py --limit 500
python3 scripts/enrich-librivox.py --limit 500

# Scan for HathiTrust digitized texts (requires OCLC or ISBN)
python3 scripts/enrich-hathitrust.py --limit 500

# Enrich author bios from Wikipedia
python3 scripts/enrich-authors.py --limit 200
```

Use background execution for long-running scans. Run multiple sources in parallel when possible (they hit different APIs).

### 3. Post-enrichment steps

After enrichment completes:

```bash
# Recompute copyright status from new metadata
python3 scripts/enrich-copyright.py --apply

# Check if subjects suggest category changes
python3 scripts/enrich-categories.py

# Regenerate stats and search index
python3 scripts/generate-stats.py
python3 scripts/generate-search-index.py
```

### 4. Commit results

Commit enrichment data with a descriptive message showing counts:

```
feat(data): subjects 1,761→X, Gutenberg Y, LibriVox Z
```

Include the enrichment field counts in the commit message.

### 5. State tracking

- State is in `data/enrichment-state.json` (gitignored)
- Each source tracks: last_scanned_slug, scan_date, total_scanned, total_matched
- Scripts automatically resume from last position on same day
- New day = fresh scan from the beginning
- `is_complete` flag tracks when all books have been processed

### Key rates

- Open Library: 1.0s between requests
- Google Books: 1.0s (rate limited at ~1000/day without API key)
- Gutenberg (Gutendex): 0.5s
- LibriVox: 1.0s
- HathiTrust: 0.5s

### Enrichment priority matrix

| Missing field | Best source | Fallback |
|---|---|---|
| subjects | Open Library | Google Books, Gutendex |
| description | Google Books | Open Library |
| pages | Open Library | Google Books |
| isbn | Open Library | Google Books |
| cover_url | Open Library | — |
| reading links | Gutenberg, LibriVox | HathiTrust |
| author bio | Wikipedia | Open Library |
