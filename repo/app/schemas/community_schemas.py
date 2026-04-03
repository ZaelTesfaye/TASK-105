"""Marshmallow schemas for community endpoints."""
from marshmallow import Schema, fields, validate, EXCLUDE


class CreateCommunitySchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=256))
    address_line1 = fields.Str(required=True, validate=validate.Length(min=1, max=512))
    address_line2 = fields.Str(load_default=None)
    city = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    state = fields.Str(required=True, validate=validate.Length(min=2, max=2))
    zip = fields.Str(required=True, validate=validate.Length(min=5, max=10))
    service_hours = fields.Dict(load_default={})
    fulfillment_scope = fields.Str(load_default="")


class UpdateCommunitySchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(validate=validate.Length(min=1, max=256))
    address_line1 = fields.Str(validate=validate.Length(min=1, max=512))
    address_line2 = fields.Str(allow_none=True)
    city = fields.Str(validate=validate.Length(min=1, max=128))
    state = fields.Str(validate=validate.Length(min=2, max=2))
    zip = fields.Str(validate=validate.Length(min=5, max=10))
    service_hours = fields.Dict()
    fulfillment_scope = fields.Str()
