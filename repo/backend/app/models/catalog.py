from datetime import datetime, timezone
from app.extensions import db
from .base import GUID, new_uuid


class Product(db.Model):
    __tablename__ = "products"

    product_id = db.Column(GUID, primary_key=True, default=new_uuid)
    sku = db.Column(db.String(128), unique=True, nullable=False)
    name = db.Column(db.String(256), nullable=False)
    brand = db.Column(db.String(128), nullable=False, index=True)
    category = db.Column(db.String(128), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False, default="")
    price_usd = db.Column(db.Float, nullable=False, index=True)
    sales_volume = db.Column(db.Integer, nullable=False, default=0, index=True)
    # Per-SKU global safety-stock default; operative value lives on InventoryLot
    safety_stock_threshold = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    attributes = db.relationship(
        "ProductAttribute",
        back_populates="product",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    tags = db.relationship(
        "ProductTag",
        back_populates="product",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        return {
            "product_id": str(self.product_id),
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "description": self.description,
            "price_usd": self.price_usd,
            "sales_volume": self.sales_volume,
            "safety_stock_threshold": self.safety_stock_threshold,
            "created_at": self.created_at.isoformat(),
            "attributes": [a.to_dict() for a in self.attributes],
            "tags": [t.tag for t in self.tags],
        }


class ProductAttribute(db.Model):
    __tablename__ = "product_attributes"

    attribute_id = db.Column(GUID, primary_key=True, default=new_uuid)
    product_id = db.Column(
        GUID, db.ForeignKey("products.product_id"), nullable=False, index=True
    )
    key = db.Column(db.String(128), nullable=False)
    value = db.Column(db.String(512), nullable=False)

    product = db.relationship("Product", back_populates="attributes")

    def to_dict(self) -> dict:
        return {"key": self.key, "value": self.value}


class ProductTag(db.Model):
    __tablename__ = "product_tags"

    tag_id = db.Column(GUID, primary_key=True, default=new_uuid)
    product_id = db.Column(
        GUID, db.ForeignKey("products.product_id"), nullable=False, index=True
    )
    tag = db.Column(db.String(128), nullable=False, index=True)

    product = db.relationship("Product", back_populates="tags")


class SearchLog(db.Model):
    __tablename__ = "search_logs"

    log_id = db.Column(GUID, primary_key=True, default=new_uuid)
    user_id = db.Column(GUID, db.ForeignKey("users.user_id"), nullable=False, index=True)
    query = db.Column(db.Text, nullable=False)
    searched_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    result_count = db.Column(db.Integer, nullable=False, default=0)


class TrendingCache(db.Model):
    """Precomputed trending scores — refreshed every 15 min by background job."""
    __tablename__ = "trending_cache"

    term = db.Column(db.Text, primary_key=True)
    score = db.Column(db.Float, nullable=False)
    computed_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
