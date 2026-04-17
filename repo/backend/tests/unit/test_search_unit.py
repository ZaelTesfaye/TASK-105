"""
Unit tests for SearchService — all calls go directly to the service layer, no HTTP.

Covered:
  - Product search with keyword, filters, and empty results
  - Autocomplete with partial input
  - Trending query aggregation logic
  - History recording and deletion
"""
import uuid

import pytest

from app.services.auth_service import AuthService
from app.services.search_service import SearchService
from app.extensions import db
from app.models.catalog import Product, TrendingCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _u(prefix="srch"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _pw():
    return "ValidPass1234!"


def _create_product(name="Test Product", brand="TestBrand", price=9.99):
    """Insert a product directly into the DB (must be called inside app_context)."""
    p = Product(
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        name=name,
        brand=brand,
        category="General",
        description=f"Description for {name}",
        price_usd=price,
    )
    db.session.add(p)
    db.session.commit()
    return p


# ---------------------------------------------------------------------------
# search_products
# ---------------------------------------------------------------------------

class TestSearchProducts:

    def test_search_returns_results(self, app):
        """search_products with a matching keyword returns items."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            unique_name = f"UniqueWidget_{uuid.uuid4().hex[:6]}"
            _create_product(name=unique_name, brand="WidgetCo")
            result = SearchService.search_products({"q": unique_name}, user)
            assert result["total"] >= 1
            assert any(unique_name in item["name"] for item in result["items"])

    def test_search_empty_results(self, app):
        """search_products with a non-matching keyword returns zero items."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            result = SearchService.search_products(
                {"q": f"nonexistent_{uuid.uuid4().hex}"}, user
            )
            assert result["total"] == 0
            assert result["items"] == []

    def test_search_filter_by_brand(self, app):
        """search_products brand filter narrows results."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            unique_brand = f"Brand_{uuid.uuid4().hex[:6]}"
            _create_product(name="BrandFilter Test", brand=unique_brand)
            result = SearchService.search_products({"brand": unique_brand}, user)
            assert result["total"] >= 1
            assert all(unique_brand.lower() in item["brand"].lower() for item in result["items"])

    def test_search_filter_by_price_range(self, app):
        """search_products with min_price/max_price returns only matching items."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            _create_product(name=f"Cheap_{uuid.uuid4().hex[:6]}", price=5.00)
            _create_product(name=f"Expensive_{uuid.uuid4().hex[:6]}", price=500.00)
            result = SearchService.search_products(
                {"min_price": 400, "max_price": 600}, user
            )
            for item in result["items"]:
                assert 400 <= item["price_usd"] <= 600

    def test_search_pagination(self, app):
        """search_products respects page and page_size."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            result = SearchService.search_products({"page": 1, "page_size": 2}, user)
            assert result["page"] == 1
            assert result["page_size"] == 2
            assert len(result["items"]) <= 2


# ---------------------------------------------------------------------------
# autocomplete
# ---------------------------------------------------------------------------

class TestAutocomplete:

    def test_autocomplete_returns_suggestions(self, app):
        """autocomplete with partial input returns matching product names."""
        with app.app_context():
            unique_prefix = f"AutoComp_{uuid.uuid4().hex[:6]}"
            _create_product(name=f"{unique_prefix}_Widget")
            result = SearchService.autocomplete(unique_prefix)
            assert "suggestions" in result
            assert any(unique_prefix in s for s in result["suggestions"])

    def test_autocomplete_empty_query(self, app):
        """autocomplete with empty input returns no suggestions."""
        with app.app_context():
            result = SearchService.autocomplete("")
            assert result["suggestions"] == []


# ---------------------------------------------------------------------------
# trending
# ---------------------------------------------------------------------------

class TestTrending:

    def test_get_trending_returns_structure(self, app):
        """get_trending returns a dict with a 'trending' list."""
        with app.app_context():
            result = SearchService.get_trending()
            assert "trending" in result
            assert isinstance(result["trending"], list)

    def test_get_trending_with_cache_entries(self, app):
        """get_trending includes items from TrendingCache."""
        with app.app_context():
            term = f"trend_{uuid.uuid4().hex[:6]}"
            cache_entry = TrendingCache(term=term, score=42.0)
            db.session.add(cache_entry)
            db.session.commit()

            result = SearchService.get_trending()
            terms = [t["term"] for t in result["trending"]]
            assert term in terms


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

class TestSearchHistory:

    def test_history_recorded_after_search(self, app):
        """After a search, get_history includes the query."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            query_text = f"historytest_{uuid.uuid4().hex[:6]}"
            SearchService.search_products({"q": query_text}, user)
            history = SearchService.get_history(user)
            assert "history" in history
            queries = [h["query"] for h in history["history"]]
            assert query_text in queries

    def test_clear_history(self, app):
        """clear_history removes all entries for the user."""
        with app.app_context():
            user = AuthService.register(_u(), _pw(), role="Member")
            SearchService.search_products({"q": "clearme"}, user)
            SearchService.clear_history(user)
            history = SearchService.get_history(user)
            assert len(history["history"]) == 0
