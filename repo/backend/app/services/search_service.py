"""
Search service.
Full-text search via SQLite FTS5 (virtual table products_fts created in migration).
Trending scores are read from TrendingCache (precomputed by background job).
Search history is capped at 50 entries per user (oldest evicted).
"""
from difflib import get_close_matches

from flask import current_app
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models.catalog import Product, ProductAttribute, ProductTag, SearchLog, TrendingCache
from app.models.user import User

_HISTORY_CAP = 50
_DISTINCT_BRAND_TAG_CAP = 2000


def _fts5_available() -> bool:
    """One-time probe per Flask app — avoids a redundant round-trip on every search."""
    app = current_app._get_current_object()
    slot = app.extensions.setdefault("_search_fts5", {"checked": False, "ok": False})
    if slot["checked"]:
        return slot["ok"]
    try:
        db.session.execute(db.text("SELECT 1 FROM products_fts LIMIT 0"))
        slot["ok"] = True
    except OperationalError:
        db.session.rollback()
        slot["ok"] = False
    slot["checked"] = True
    return slot["ok"]


class SearchService:

    @staticmethod
    def search_products(params: dict, user: User) -> dict:
        q_text = params.get("q", "").strip()
        page = params.get("page", 1)
        page_size = params.get("page_size", 20)

        query = Product.query.filter(Product.deleted_at.is_(None))

        # Keyword filter — FTS5 MATCH query; falls back to ILIKE when the
        # products_fts virtual table has not yet been created (pre-migration).
        if q_text:
            if _fts5_available():
                fts_condition = db.text(
                    "products.rowid IN "
                    "(SELECT rowid FROM products_fts WHERE products_fts MATCH :fts_q)"
                ).bindparams(fts_q=q_text)
                query = query.filter(fts_condition)
            else:
                like = f"%{q_text}%"
                query = query.filter(
                    db.or_(Product.name.ilike(like), Product.brand.ilike(like),
                           Product.description.ilike(like))
                )

        if params.get("brand"):
            query = query.filter(Product.brand.ilike(f"%{params['brand']}%"))
        if params.get("min_price") is not None:
            query = query.filter(Product.price_usd >= params["min_price"])
        if params.get("max_price") is not None:
            query = query.filter(Product.price_usd <= params["max_price"])
        if params.get("tags"):
            tag_list = [t.strip() for t in params["tags"].split(",") if t.strip()]
            query = query.join(
                ProductTag, Product.product_id == ProductTag.product_id
            ).filter(ProductTag.tag.in_(tag_list))

        # Attribute filters: attributes={key: value, ...}
        if params.get("attributes"):
            for attr_key, attr_value in params["attributes"].items():
                attr_alias = db.aliased(ProductAttribute)
                query = query.join(
                    attr_alias, Product.product_id == attr_alias.product_id
                ).filter(attr_alias.key == attr_key, attr_alias.value == attr_value)

        # Deduplicate rows produced by tag/attribute joins
        query = query.distinct()

        sort = params.get("sort", "new_arrivals")
        sort_map = {
            "sales_volume": Product.sales_volume.desc(),
            "price_asc": Product.price_usd.asc(),
            "price_desc": Product.price_usd.desc(),
            "new_arrivals": Product.created_at.desc(),
        }
        query = query.order_by(sort_map.get(sort, Product.created_at.desc()))

        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()

        # Log search
        SearchService._log_search(user, q_text, total)

        zero_guidance = None
        if total == 0 and q_text:
            zero_guidance = SearchService._zero_result_guidance(q_text)

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [p.to_dict() for p in items],
            "zero_result_guidance": zero_guidance,
        }

    @staticmethod
    def _log_search(user: User, query: str, result_count: int) -> None:
        if not query:
            return
        # Cap at 50 — single DELETE when at capacity (faster than count + ORM fetch)
        uid = str(user.user_id)
        db.session.execute(
            text(
                """
                DELETE FROM search_logs WHERE log_id IN (
                    SELECT log_id FROM search_logs WHERE user_id = :uid
                    ORDER BY searched_at ASC LIMIT 1
                ) AND (SELECT COUNT(*) FROM search_logs WHERE user_id = :uid) >= :cap
                """
            ),
            {"uid": uid, "cap": _HISTORY_CAP},
        )
        log = SearchLog(user_id=user.user_id, query=query, result_count=result_count)
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def _fuzzy_pick(query: str, choices: list[str], n: int = 3) -> list[str]:
        """Rank known strings by fuzzy similarity (typos, near-miss spellings)."""
        if not query or not choices:
            return []
        q = query.strip().lower()
        canon = {}
        for c in choices:
            key = c.lower()
            if key not in canon:
                canon[key] = c
        pool = list(canon.keys())
        # cutoff ~0.45 catches single-char typos on medium-length tokens
        picks = get_close_matches(q, pool, n=n, cutoff=0.45)
        return [canon[p] for p in picks]

    @staticmethod
    def _zero_result_guidance(query: str) -> dict:
        brands_raw = [
            r[0]
            for r in db.session.query(Product.brand)
            .filter(Product.deleted_at.is_(None))
            .distinct()
            .limit(_DISTINCT_BRAND_TAG_CAP)
            .all()
        ]
        tags_raw = [
            r[0]
            for r in db.session.query(ProductTag.tag).distinct().limit(_DISTINCT_BRAND_TAG_CAP).all()
        ]
        brands = SearchService._fuzzy_pick(query, brands_raw, n=3)
        tags = SearchService._fuzzy_pick(query, tags_raw, n=3)
        return {"closest_brands": brands, "closest_tags": tags}

    @staticmethod
    def autocomplete(q: str) -> dict:
        if not q:
            return {"suggestions": []}
        like = f"{q}%"
        names = [r[0] for r in db.session.query(Product.name)
                 .filter(Product.name.ilike(like)).distinct().limit(10).all()]
        return {"suggestions": names}

    @staticmethod
    def get_trending() -> dict:
        rows = TrendingCache.query.order_by(TrendingCache.score.desc()).limit(20).all()
        return {"trending": [{"term": r.term, "score": r.score} for r in rows]}

    @staticmethod
    def get_history(user: User) -> dict:
        logs = (db.session.query(SearchLog)
                .filter(SearchLog.user_id == user.user_id)
                .order_by(SearchLog.searched_at.desc())
                .limit(_HISTORY_CAP).all())
        return {"history": [{"query": entry.query, "searched_at": entry.searched_at.isoformat()} for entry in logs]}

    @staticmethod
    def clear_history(user: User) -> None:
        db.session.query(SearchLog).filter(SearchLog.user_id == user.user_id).delete()
        db.session.commit()
