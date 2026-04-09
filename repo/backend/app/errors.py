from flask import Flask, jsonify
from marshmallow.exceptions import ValidationError as MarshmallowValidationError


class AppError(Exception):
    """Base application error — raised in service layer, caught here."""
    status_code = 400

    def __init__(self, error: str, message: str, field: str | None = None, status_code: int | None = None):
        self.error = error
        self.message = message
        self.field = field
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)

    def to_dict(self) -> dict:
        d = {"error": self.error, "message": self.message}
        if self.field:
            d["field"] = self.field
        return d


class NotFoundError(AppError):
    status_code = 404

    def __init__(self, resource: str = "resource"):
        super().__init__("not_found", f"{resource} not found", status_code=404)


class ConflictError(AppError):
    status_code = 409


class UnauthorizedError(AppError):
    status_code = 401


class ForbiddenError(AppError):
    status_code = 403


class UnprocessableError(AppError):
    status_code = 422


class LockedError(AppError):
    status_code = 423

    def __init__(self, retry_after: str):
        super().__init__("account_locked", "Account temporarily locked", status_code=423)
        self.retry_after = retry_after

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["retry_after"] = self.retry_after
        return d


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(MarshmallowValidationError)
    def handle_marshmallow_error(err: MarshmallowValidationError):
        return jsonify({
            "error": "validation_error",
            "message": "Invalid request data",
            "fields": err.messages,
        }), 400

    @app.errorhandler(404)
    def handle_404(_err):
        return jsonify({"error": "not_found", "message": "Endpoint not found"}), 404

    @app.errorhandler(405)
    def handle_405(_err):
        return jsonify({"error": "method_not_allowed", "message": "Method not allowed"}), 405

    @app.errorhandler(500)
    def handle_500(_err):
        return jsonify({"error": "internal_error", "message": "An unexpected error occurred"}), 500
