from flask import Flask


def register_middleware(app: Flask) -> None:
    from .correlation import init_correlation_middleware
    from .logging import init_logging_middleware

    init_correlation_middleware(app)
    init_logging_middleware(app)
    # Auth and RBAC are applied per-route via decorators (see middleware/auth.py and middleware/rbac.py)
