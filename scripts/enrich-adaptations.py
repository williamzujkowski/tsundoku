#!/usr/bin/env python3
"""Wikidata-driven adaptations enrichment for books — issue #184.

Populates the `adaptations` field on books from Wikidata property P144
("based on"). A film / TV series / play / radio drama / opera that adapts a
book carries `P144 → <the book's work QID>`. For every book with a
`wikidata_qid` and no adaptations yet, we query Wikidata for items pointing
at it via P144, classify each by its P31 (instance-of) into the schema's
type enum {film, tv, stage, radio, opera, other}, and read title + year.

Queries are BATCHED (VALUES ?book { wd:Q1 wd:Q2 ... }, ~40 books/request)
via scripts/wikidata.adaptations_for_batch — one request per batch, not per
book — and cached on disk, so re-runs are free and rate-limit friendly. A
batch that fails transiently (rate-limit/timeout) stops the run cleanly so a
re-run resumes at exactly that batch.

Writes are additive (never overwrite a non-empty `adaptations`) and tag
provenance as `wikidata_adaptations_v1`.

Resumable: extends EnrichmentScript, so it records scan position per book
slug in data/enrichment-state.json under source `wikidata_adaptations` and
resumes where it left off on the next run.

Usage:
  python scripts/enrich-adaptations.py                 # process all candidates
  python scripts/enrich-adaptations.py --limit 100     # first validation batch
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_base import EnrichmentScript
from enrichment_state import EnrichmentState
from json_merge import provenance_merge, save_json
from wikidata import adaptations_for_batch, ADAPTATIONS_BATCH_SIZE


SOURCE = "wikidata_adaptations_v1"  # provenance tag
BATCH_BOOKS = ADAPTATIONS_BATCH_SIZE  # books/request (small → fast queries, no hang)
# Stop the run after this many consecutive failed batches (sustained WDQS
# outage). The scan is resumable, so a re-run picks up where it left off.
MAX_CONSECUTIVE_FAILURES = 3


class AdaptationsEnrichment(EnrichmentScript):
    """Populate `adaptations` from Wikidata P144 (batched SPARQL)."""

    @property
    def source_name(self) -> str:
        # State key (distinct from the provenance tag SOURCE).
        return "wikidata_adaptations"

    @property
    def enrichment_field(self) -> str:
        return "adaptations"

    def search(self, book: dict):
        """Unused — we override run() to batch. Kept to satisfy the ABC."""
        return None

    def filter_unenriched(self, books):
        """Only books that have a wikidata_qid and no adaptations yet."""
        return [
            (bp, b)
            for bp, b in books
            if b.get("wikidata_qid") and not b.get("adaptations")
        ]

    def run(self, limit: int = 0) -> None:
        """Batched main loop with state tracking and additive merge.

        Overrides the base per-book loop: P144 lookups are far cheaper when
        batched, so we resolve adaptations for ~40 books per SPARQL request,
        then apply results book-by-book (recording scan state for resume).
        """
        state = EnrichmentState(self.source_name)
        all_books = self.load_books()
        state.set_total_books(len(all_books))

        unenriched = self.filter_unenriched(all_books)
        candidates = [
            (bp, b) for bp, b in unenriched
            if state.should_scan(b.get("slug", ""))
        ]
        # Keep alphabetical (slug) order so resume-by-slug stays monotonic.
        candidates.sort(key=lambda pb: pb[1].get("slug", ""))

        print(f"[{self.source_name}] {len(unenriched)} books with wikidata_qid "
              f"and no {self.enrichment_field}")
        if len(candidates) < len(unenriched):
            print(f"  Resuming from '{state.last_scanned_slug}' "
                  f"({len(unenriched) - len(candidates)} already scanned today)")

        if limit > 0:
            candidates = candidates[:limit]

        found = 0
        total_adaptations = 0
        processed = 0
        failed_batches = 0
        consecutive_failures = 0
        # The resume pointer may only advance through the contiguous prefix of
        # successfully-queried books. Once any batch fails we stop recording
        # scans so a re-run retries from the first un-queried book — even
        # though we keep processing later batches (their writes are additive
        # and safe). `seen_failure` latches that state.
        seen_failure = False

        for start in range(0, len(candidates), BATCH_BOOKS):
            batch = candidates[start:start + BATCH_BOOKS]
            qid_to_books: dict[str, list[tuple[Path, dict]]] = {}
            for bp, b in batch:
                qid_to_books.setdefault(b["wikidata_qid"], []).append((bp, b))

            print(f"  [{processed + 1}-{processed + len(batch)}/{len(candidates)}] "
                  f"querying P144 for {len(qid_to_books)} QIDs...", flush=True)

            try:
                results = adaptations_for_batch(list(qid_to_books.keys()))
            except Exception as e:  # unexpected — treat as a batch failure
                self._log_error("search_error", f"batch@{start}", str(e))
                results = None

            if results is None:
                # Transient failure (rate-limit / timeout — now bounded by the
                # http_retry timeout, so this returns rather than hanging).
                # Dead-letter the batch, skip it, and keep going; but latch
                # seen_failure so the resume pointer never advances past these
                # un-queried books. A long outage trips the consecutive-failure
                # cap and stops the run cleanly.
                failed_batches += 1
                consecutive_failures += 1
                processed += len(batch)
                self._log_error("rate_limited", f"batch@{start}",
                                "SPARQL batch failed; dead-lettered, will retry on resume")
                self._deadletter(
                    url=f"sparql:P144:batch@{start}",
                    status=0,
                    error_type="rate_limited",
                    message=f"adaptations batch of {len(batch)} books failed",
                )
                seen_failure = True
                print(f"      … batch failed (transient); dead-lettered, "
                      f"will retry on resume")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"      ✗ {MAX_CONSECUTIVE_FAILURES} consecutive "
                          f"failures — stopping. Re-run to resume.")
                    break
                time.sleep(self.rate_limit)
                continue

            consecutive_failures = 0
            for bp, b in batch:
                processed += 1
                qid = b["wikidata_qid"]
                adaptations = results.get(qid)
                matched = False
                if adaptations:
                    changed, _audit = provenance_merge(
                        b, {"adaptations": adaptations}, source=SOURCE,
                    )
                    if changed:
                        save_json(bp, b)
                        found += 1
                        total_adaptations += len(adaptations)
                        matched = True
                        types = ",".join(sorted({a["type"] for a in adaptations}))
                        print(f"      ✓ {b['slug'][:40]}: "
                              f"{len(adaptations)} ({types})")
                # Advance the resume pointer only while we're still in the
                # contiguous successful prefix (no earlier batch failed).
                if not seen_failure:
                    state.record_scan(b.get("slug", ""), matched=matched)

            state.save()  # checkpoint after each batch so resume is cheap
            time.sleep(self.rate_limit)

        state.save()
        print(f"\nDone: {found} books got adaptations "
              f"({total_adaptations} total) out of {processed} scanned; "
              f"{failed_batches} batch(es) deferred")
        print(state.summary())


if __name__ == "__main__":
    AdaptationsEnrichment.cli()
