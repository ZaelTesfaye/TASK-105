"""
Precomputes trending search terms from the last 7 days.
Score = frequency / (1 + hours_since_first_in_window / 168.0)
Writes results to TrendingCache table.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from flask import g
from sqlalchemy import func

from app.extensions import db
from app.models.catalog import SearchLog, TrendingCache

logger = logging.getLogger(__name__)
_WINDOW_DAYS = 7


def precompute_trending() -> None:
    cid = getattr(g, "correlation_id", "")
    cutoff = datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)

    rows = (
        db.session.query(
            SearchLog.query,
            func.count(SearchLog.log_id).label("freq"),
            func.min(SearchLog.searched_at).label("first_seen"),
        )
        .filter(SearchLog.searched_at >= cutoff)
        .group_by(SearchLog.query)
        .all()
    )

    now = datetime.now(timezone.utc)
    TrendingCache.query.delete()
    for term, freq, first_seen in rows:
        hours_since_first = (now - first_seen.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        score = freq / (1 + hours_since_first / 168.0)
        db.session.add(TrendingCache(term=term, score=score))

    db.session.commit()
    logger.info(json.dumps({"event": "trending_precomputed", "term_count": len(rows), "correlation_id": cid}))
