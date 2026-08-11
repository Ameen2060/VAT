"""Official-source change detection.

Fetches a monitored source, fingerprints its readable text, and compares against the
last-seen fingerprint. A change is recorded as an *informational signal* (a NEW
change-log entry) for human review — it is never treated as a legal change on its own
(requirement #10). Fetching is best-effort and fully network-guarded.
"""

from __future__ import annotations

import hashlib
import re
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FtaSource, FtaUpdate

_UA = "Mozilla/5.0 (compatible; VAT-Compliance-Monitor/1.0; +https://tax.gov.ae)"
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _fingerprint(html: str) -> str:
    # Reduce to readable text so cosmetic markup changes don't create false signals.
    text = _TAG.sub(" ", html)
    text = _WS.sub(" ", text).strip().lower()
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def _fetch(url: str, timeout: float = 15.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — official https sources
        raw = resp.read(2_000_000)  # cap at 2 MB
    return raw.decode("utf-8", "ignore")


def check_source(db: Session, source: FtaSource) -> dict:
    """Check one source. On a content change, records a NEW informational signal."""
    now = datetime.now(timezone.utc)
    result = {"id": source.id, "name": source.name, "status": "unchanged", "signal_id": None}
    try:
        html = _fetch(source.url)
        fp = _fingerprint(html)
    except Exception as e:  # noqa: BLE001 — network/site errors are expected and non-fatal
        source.last_status = "error"
        source.last_checked_at = now
        source.note = f"Fetch error: {type(e).__name__}: {e}"[:1000]
        db.commit()
        result["status"] = "error"
        result["detail"] = str(e)
        return result

    changed = source.content_hash is not None and source.content_hash != fp
    first_time = source.content_hash is None
    source.content_hash = fp
    source.last_checked_at = now
    source.last_status = "changed" if changed else "unchanged"
    source.note = None

    if changed:
        signal = FtaUpdate(
            title=f"Source content changed: {source.name}",
            update_type="source_signal",
            classification="informational",   # a page change is NOT a legal change
            status="new",
            critical=False,
            publication_date=now.date().isoformat(),
            affected_module="(to be assessed)",
            source_ref=source.url,
            source_id=source.id,
            new_rule="The monitored official page changed. Review the source to determine "
                     "whether this is an informational, guidance, or legally-effective change.",
            created_by="system:monitor",
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        result["signal_id"] = signal.id
    else:
        db.commit()

    result["status"] = "changed" if changed else ("first_seen" if first_time else "unchanged")
    return result


def check_all_sources(db: Session) -> dict:
    sources = list(db.execute(select(FtaSource).where(FtaSource.is_active.is_(True))).scalars())
    results = [check_source(db, s) for s in sources]
    return {
        "checked": len(results),
        "changed": sum(1 for r in results if r["status"] == "changed"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }
