"""
Search service.
Full-text search via SQLite FTS5 (virtual table products_fts created in migration).
Trending scores are read from TrendingCache (precomputed by background job).
Search history is capped at 50 entries per user (oldest evicted).
"""
from sqlalchemy import literal_column
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models.catalog import Product, ProductAttribute, ProductTag, SearchLog, TrendingCache
from app.models.user import User

_HISTORY_CAP = 50


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
            try:
                fts_rows = db.session.execute(
                    db.text(
                        "SELECT rowid FROM products_fts WHERE products_fts MATCH :q LIMIT 10000"
                    ),
                    {"q": q_text},
                ).fetchall()
                if fts_rows:
                    rowid_col = literal_column("rowid")
                    query = query.filter(rowid_col.in_([r[0] for r in fts_rows]))
                else:
                    query = query.filter(db.false())
            except OperationalError:
                # products_fts table not yet created; fall back to ILIKE
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
        # Cap at 50 — evict oldest if needed
        # Note: SearchLog has a column named "query" which shadows Model.query; use db.session.query() instead
        sl_q = db.session.query(SearchLog).filter(SearchLog.user_id == user.user_id)
        count = sl_q.count()
        if count >= _HISTORY_CAP:
            oldest = sl_q.order_by(SearchLog.searched_at.asc()).first()
            if oldest:
                db.session.delete(oldest)
        log = SearchLog(user_id=user.user_id, query=query, result_count=result_count)
        db.session.add(log)
        db.session.commit()

    @staticmethod
    def _zero_result_guidance(query: str) -> dict:
        # Scaffold: simple prefix/contains match; full trigram similarity in implementation phase
        like = f"%{query}%"
        brands = [r[0] for r in db.session.query(Product.brand)
                  .filter(Product.brand.ilike(like)).distinct().limit(3).all()]
        tags = [r[0] for r in db.session.query(ProductTag.tag)
                .filter(ProductTag.tag.ilike(like)).distinct().limit(3).all()]
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
