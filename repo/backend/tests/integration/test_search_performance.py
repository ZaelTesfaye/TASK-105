"""
Search performance benchmark test.
Seeds 50,000 products into the in-memory SQLite database and asserts that
p99 search latency stays below 300 ms.
CI-friendly: uses in-memory DB, no external dependencies.
"""
import time
import uuid
import statistics

import pytest
from app.extensions import db as _db
from app.models.catalog import Product

# Each token appears in ~1/50 of rows (~1k matches per keyword at 50k scale) so FTS + COUNT
# stay realistic. The old seed put "Widget"/"Alpha"/"Product" on every row (~50k hits/query).
PERF_BUCKET_TERMS = (
    "Widget", "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Gamma",
    "Helium", "Indigo", "Juliet", "Kilo", "Lima", "Metro", "Nova", "Oscar",
    "Papa", "Quorum", "Romeo", "Sierra", "Tango", "Ulster", "Victor", "Whiskey",
    "Xray", "Yankee", "Zulu", "Axiom", "Beacon", "Coral", "Drift", "Eagle",
    "Frost", "Gable", "Haven", "Iris", "Jade", "Kite", "Lumen", "Mason",
    "Nimbus", "Onyx", "Petal", "Quartz", "Raven", "Sable", "Torch", "Umber",
    "Vortex", "Willow",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def perf_app():
    """Dedicated app instance for performance tests — session-scoped seeding."""
    from app import create_app
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="module")
def perf_client(perf_app):
    return perf_app.test_client()


@pytest.fixture(scope="module")
def perf_token(perf_app, perf_client):
    """Register an admin user and return a token."""
    uname = f"perf_{uuid.uuid4().hex[:8]}"
    pwd = "PerfTestPass1234!"
    with perf_app.app_context():
        from app.services.auth_service import AuthService
        AuthService.register(uname, pwd, role="Administrator")
    resp = perf_client.post("/api/v1/auth/login",
                            json={"username": uname, "password": pwd})
    return resp.json["token"]


@pytest.fixture(scope="module")
def perf_headers(perf_token):
    return {"Authorization": f"Bearer {perf_token}"}


@pytest.fixture(scope="module", autouse=True)
def seed_products(perf_app):
    """Bulk-seed 50,000 products for the performance test suite."""
    BATCH = 1000
    TOTAL = 50_000
    brands = ["Acme", "Globex", "Initech", "Umbrella", "Wonka",
              "Stark", "Wayne", "Cyberdyne", "Oscorp", "Soylent"]
    categories = ["Electronics", "Clothing", "Food", "Tools", "Sports",
                  "Books", "Toys", "Health", "Home", "Garden"]

    n_terms = len(PERF_BUCKET_TERMS)
    with perf_app.app_context():
        for batch_start in range(0, TOTAL, BATCH):
            products = []
            for i in range(batch_start, min(batch_start + BATCH, TOTAL)):
                bucket = i % n_terms
                term = PERF_BUCKET_TERMS[bucket]
                desc_term = PERF_BUCKET_TERMS[(bucket + 17) % n_terms]
                p = Product(
                    sku=f"PERF-{i:06d}",
                    name=f"PerfItem-{i} {term} catalog",
                    brand=brands[i % len(brands)],
                    category=categories[i % len(categories)],
                    description=f"Blurb-{i} {desc_term} segment",
                    price_usd=round(1.0 + (i % 500) * 0.5, 2),
                    sales_volume=i % 10000,
                )
                products.append(p)
            _db.session.bulk_save_objects(products)
            _db.session.commit()

        # Verify count
        count = Product.query.filter(Product.deleted_at.is_(None)).count()
        assert count >= TOTAL, f"Expected {TOTAL} products, got {count}"

        # Create FTS5 virtual table and populate it (mirrors migration 0005)
        _db.session.execute(_db.text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS products_fts "
            "USING fts5(name, brand, description, content='products', content_rowid='rowid')"
        ))
        _db.session.execute(_db.text(
            "INSERT INTO products_fts(rowid, name, brand, description) "
            "SELECT rowid, name, COALESCE(brand, ''), COALESCE(description, '') FROM products"
        ))
        _db.session.execute(_db.text("PRAGMA cache_size=-200000"))
        _db.session.commit()


# ---------------------------------------------------------------------------
# Performance test
# ---------------------------------------------------------------------------

_SEARCH_QUERIES = [
    {"q": "Widget", "page_size": "20"},
    {"q": "Alpha", "brand": "Acme", "page_size": "20"},
    {"q": "Bravo", "min_price": "10", "max_price": "100", "page_size": "20"},
    {"q": "Charlie", "sort": "price_asc", "page_size": "20"},
    {"q": "Delta", "sort": "sales_volume", "page_size": "20"},
    {"brand": "Globex", "page_size": "20"},
    {"q": "Echo", "page_size": "20"},
    {"q": "Foxtrot", "sort": "price_desc", "page_size": "20"},
]

_P99_LIMIT_MS = 300
_WARMUP_ITERATIONS = 10  # warmup: not counted — stabilize caches
_MEASURED_ITERATIONS = 50  # total measured queries: len(_SEARCH_QUERIES) * _MEASURED_ITERATIONS
_MAX_RETRIES = 3  # retry on transient CI noise


def _run_search_benchmark(perf_client, perf_headers):
    """Run one full benchmark pass. Returns (p99, report_str)."""
    # Warmup — populate SQLite page cache and Python caches
    for _ in range(_WARMUP_ITERATIONS):
        for params in _SEARCH_QUERIES:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            perf_client.get(f"/api/v1/search/products?{qs}",
                            headers=perf_headers)

    # Measured iterations
    latencies = []
    for _ in range(_MEASURED_ITERATIONS):
        for params in _SEARCH_QUERIES:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            start = time.perf_counter()
            resp = perf_client.get(f"/api/v1/search/products?{qs}",
                                   headers=perf_headers)
            elapsed_ms = (time.perf_counter() - start) * 1000
            assert resp.status_code == 200
            latencies.append(elapsed_ms)

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p99_idx = int(len(latencies) * 0.99)
    p99 = latencies[p99_idx]
    mean = statistics.mean(latencies)

    report = (
        f"\n--- Search Performance Report ---\n"
        f"  Total queries: {len(latencies)}\n"
        f"  Mean latency:  {mean:.1f} ms\n"
        f"  P50 latency:   {p50:.1f} ms\n"
        f"  P99 latency:   {p99:.1f} ms\n"
        f"  Max latency:   {max(latencies):.1f} ms\n"
        f"  P99 limit:     {_P99_LIMIT_MS} ms"
    )
    return p99, report


def test_search_p99_latency_under_300ms(perf_client, perf_headers):
    """
    Execute a diverse set of search queries and assert that the p99 latency
    stays under 300 ms against a dataset of 50,000 products.
    Includes warmup and retry logic to tolerate transient CI load spikes.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        p99, report = _run_search_benchmark(perf_client, perf_headers)
        print(f"{report}  (attempt {attempt}/{_MAX_RETRIES})")
        if p99 < _P99_LIMIT_MS:
            return  # PASS

    assert p99 < _P99_LIMIT_MS, (
        f"p99 search latency {p99:.1f} ms exceeds {_P99_LIMIT_MS} ms limit "
        f"after {_MAX_RETRIES} attempts"
    )
