from flask import Blueprint, request, jsonify
from app.middleware.auth import require_auth
from app.middleware.rbac import require_roles
from app.services.catalog_service import CatalogService
from app.schemas.catalog_schemas import CreateProductSchema, UpdateProductSchema

catalog_bp = Blueprint("catalog", __name__)


@catalog_bp.post("/products")
@require_auth
@require_roles("Administrator", "Operations Manager")
def create_product():
    data = CreateProductSchema().load(request.get_json(force=True) or {})
    product = CatalogService.create_product(data)
    return jsonify(product.to_dict()), 201


@catalog_bp.get("/products/<product_id>")
@require_auth
def get_product(product_id):
    product = CatalogService.get_product(product_id)
    return jsonify(product.to_dict())


@catalog_bp.patch("/products/<product_id>")
@require_auth
@require_roles("Administrator", "Operations Manager")
def update_product(product_id):
    data = UpdateProductSchema().load(request.get_json(force=True) or {})
    product = CatalogService.update_product(product_id, data)
    return jsonify(product.to_dict())


@catalog_bp.delete("/products/<product_id>")
@require_auth
@require_roles("Administrator")
def delete_product(product_id):
    CatalogService.delete_product(product_id)
    return "", 204


@catalog_bp.patch("/products/<product_id>/safety-stock")
@require_auth
@require_roles("Administrator", "Operations Manager")
def set_safety_stock(product_id):
    data = request.get_json(force=True) or {}
    result = CatalogService.set_safety_stock(product_id, data["threshold"])
    return jsonify(result)
