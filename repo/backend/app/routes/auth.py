from flask import Blueprint, request, jsonify
from app.middleware.auth import require_auth
from app.services.auth_service import AuthService
from app.schemas.auth_schemas import RegisterSchema, LoginSchema

auth_bp = Blueprint("auth", __name__)
_register_schema = RegisterSchema()
_login_schema = LoginSchema()


@auth_bp.post("/auth/register")
def register():
    data = _register_schema.load(request.get_json(force=True))
    user = AuthService.register(
        username=data["username"],
        password=data["password"],
        role="Member",
    )
    return jsonify(user.to_dict()), 201


@auth_bp.post("/auth/login")
def login():
    data = _login_schema.load(request.get_json(force=True))
    result = AuthService.login(data["username"], data["password"])
    return jsonify(result), 200


@auth_bp.post("/auth/logout")
@require_auth
def logout():
    token = request.headers["Authorization"][7:]
    AuthService.logout(token)
    return "", 204
