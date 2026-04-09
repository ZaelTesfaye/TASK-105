"""
Injects / propagates X-Correlation-ID on every request.
The value is stored in Flask's g context so service/job code can access it.
"""
import uuid
from flask import Flask, g, request, Response


def init_correlation_middleware(app: Flask) -> None:
    @app.before_request
    def set_correlation_id():
        g.correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

    @app.after_request
    def add_correlation_header(response: Response) -> Response:
        response.headers["X-Correlation-ID"] = getattr(g, "correlation_id", "")
        return response
