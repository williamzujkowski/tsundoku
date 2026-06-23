"""Dead-letter log for permanently-failed enrichment requests.

When an HTTP request can't be satisfied — a 404, a non-retryable 4xx, a
network error that survives every retry, or a 429/503 that exhausts the
backoff budget — the record is otherwise silently lost for the run. This
module appends a single JSON line per such failure to
``data/enrichment-deadletter.jsonl`` so the loss is auditable and a later
re-run can target the failed set.

Design notes:
  * Best-effort: ``write_deadletter`` never raises. A logging failure must
    never abort an enrichment run.
  * One JSON object per line (JSONL) — append-only, cheap to tail.
  * Uses real wall-clock timestamps. These are ordinary enrichment scripts,
    not deterministic workflow scripts, so ``datetime.now()`` is fine.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Optional

from enrichment_config import DEADLETTER_LOG


def write_deadletter(
    *,
    source: str,
    url: str,
    status: int,
    error_type: str,
    message: str = "",
    path: Optional[Path] = None,
) -> None:
    """Append one dead-letter record. Never raises.

    Args:
        source: enricher / source name (e.g. "gutenberg", "hathitrust").
        url: the request URL that permanently failed.
        status: HTTP status code (0 for network errors / no response).
        error_type: short classification ("not_found", "http_error",
            "rate_limited", "connection_error", "parse_error", ...).
        message: optional human-readable detail (truncated).
        path: override the log path (used by tests); defaults to
            ``DEADLETTER_LOG``.
    """
    target = path if path is not None else DEADLETTER_LOG
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "source": source,
        "url": url[:1000],
        "status": status,
        "error_type": error_type,
        "message": message[:500],
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # Best-effort: never fail enrichment because of a log write.
