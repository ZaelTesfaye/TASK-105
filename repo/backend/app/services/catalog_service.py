"""Product catalog service."""
from datetime import datetime, timezone

from app.extensions import db
from app.models.catalog import Product, ProductAttribute, ProductTag
from app.models.inventory import InventoryLot
from app.errors import NotFoundError, ConflictError


class CatalogService:

    @staticmethod
    def _get_or_404(product_id: str) -> Product:
        p = db.session.get(Product, product_id)
        if p is None or p.deleted_at is not None:
            raise NotFoundError("product")
        return p

    @staticmethod
    def create_product(data: dict) -> Product:
        if Product.query.filter_by(sku=data["sku"]).first():
            raise ConflictError("sku_taken", "SKU already in use", field="sku")
        product = Product(
            sku=data["sku"],
            name=data["name"],
            brand=data["brand"],
            category=data["category"],
            description=data.get("description", ""),
            price_usd=float(data["price_usd"]),
        )
        db.session.add(product)
        db.session.flush()  # get product_id before adding children

        for attr in data.get("attributes", []):
            db.session.add(ProductAttribute(product_id=product.product_id, key=attr["key"], value=attr["value"]))
        for tag in data.get("tags", []):
            db.session.add(ProductTag(product_id=product.product_id, tag=tag))

        db.session.commit()
        return product

    @staticmethod
    def get_product(product_id: str) -> Product:
        return CatalogService._get_or_404(product_id)

    @staticmethod
    def update_product(product_id: str, data: dict) -> Product:
        product = CatalogService._get_or_404(product_id)
        for field in ("name", "brand", "category", "description"):
            if field in data:
                setattr(product, field, data[field])
        if "price_usd" in data:
            product.price_usd = float(data["price_usd"])
        if "attributes" in data:
            ProductAttribute.query.filter_by(product_id=product.product_id).delete()
            for attr in data["attributes"]:
                db.session.add(ProductAttribute(product_id=product.product_id, key=attr["key"], value=attr["value"]))
        if "tags" in data:
            ProductTag.query.filter_by(product_id=product.product_id).delete()
            for tag in data["tags"]:
                db.session.add(ProductTag(product_id=product.product_id, tag=tag))
        db.session.commit()
        return product

    @staticmethod
    def delete_product(product_id: str) -> None:
        product = CatalogService._get_or_404(product_id)
        product.deleted_at = datetime.now(timezone.utc)
        db.session.commit()

    @staticmethod
    def set_safety_stock(product_id: str, threshold: int) -> dict:
        product = CatalogService._get_or_404(product_id)
        threshold = int(threshold)
        product.safety_stock_threshold = threshold
        # Propagate to all inventory lots for this product
        InventoryLot.query.filter_by(sku_id=product.product_id).update(
            {"safety_stock_threshold": threshold}
        )
        db.session.commit()
        return {"product_id": str(product.product_id), "safety_stock_threshold": threshold}
