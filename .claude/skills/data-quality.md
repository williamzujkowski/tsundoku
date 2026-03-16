---
name: data-quality
description: Review and report on tsundoku data quality, coverage, and gaps
triggers:
  - data quality
  - data review
  - coverage report
  - gap analysis
  - check data
---

# Data Quality Review

Analyze the tsundoku book collection for data completeness, accuracy, and improvement opportunities.

## Steps

### 1. Run gap report

```bash
cd ~/git/tsundoku
python3 scripts/enrich-gaps.py --report
```

This shows missing counts for: description, subjects, pages, isbn, cover_url.

### 2. Check copyright distribution

```bash
python3 scripts/enrich-copyright.py --report
```

Shows: public_domain, likely_public_domain, in_copyright, undetermined.

### 3. Check category distribution

```bash
python3 scripts/enrich-categories.py --report
```

Shows all categories with book counts. Flag categories with fewer than 10 books.

### 4. Check enrichment scan progress

```bash
python3 scripts/run-all-enrichments.py --status
```

Shows scan positions and match rates per source.

### 5. Check author coverage

```bash
# Count authors with/without bios and photos
cd ~/git/tsundoku
echo "Total authors: $(ls src/content/authors/ | wc -l)"
echo "With bio: $(grep -rl '\"bio\"' src/content/authors/ | wc -l)"
echo "With photo: $(grep -rl 'photo_url' src/content/authors/ | wc -l)"
```

### 6. Check free reading link coverage

```bash
echo "Gutenberg: $(grep -rl gutenberg_url src/content/books/ | wc -l)"
echo "LibriVox: $(grep -rl librivox_url src/content/books/ | wc -l)"
echo "HathiTrust: $(grep -rl hathitrust_url src/content/books/ | wc -l)"
echo "WorldCat: $(grep -rl worldcat_url src/content/books/ | wc -l)"
```

### 7. Report findings

Present a summary table to the user with:
- Total books, categories, authors
- Field completeness percentages
- Copyright status breakdown
- Enrichment scan positions (which letter of alphabet each source has reached)
- Top improvement opportunities

### 8. Suggest actions

Based on the gaps found, suggest which enrichment scripts to run next.
Prioritize: subjects (enables category enrichment) > descriptions > free reading links.
