"""Marshmallow schemas for catalog/product endpoints."""
from marshmallow import Schema, fields, validate, EXCLUDE


class ProductAttributeSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    key = fields.Str(required=True, validate=validate.Length(min=1))
    value = fields.Str(required=True)


class CreateProductSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    sku = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    name = fields.Str(required=True, validate=validate.Length(min=1, max=256))
    brand = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    category = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    description = fields.Str(load_default="")
    price_usd = fields.Float(required=True, validate=validate.Range(min=0))
    attributes = fields.List(fields.Nested(ProductAttributeSchema), load_default=[])
    tags = fields.List(fields.Str(), load_default=[])


class UpdateProductSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(validate=validate.Length(min=1, max=256))
    brand = fields.Str(validate=validate.Length(min=1, max=128))
    category = fields.Str(validate=validate.Length(min=1, max=128))
    description = fields.Str()
    price_usd = fields.Float(validate=validate.Range(min=0))
    attributes = fields.List(fields.Nested(ProductAttributeSchema))
    tags = fields.List(fields.Str())
