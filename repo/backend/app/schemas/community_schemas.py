"""Marshmallow schemas for community endpoints."""
from marshmallow import Schema, fields, validate, EXCLUDE

_STATE_RE = r"^[A-Z]{2}$"
_ZIP_RE = r"^\d{5}(-\d{4})?$"


class CreateCommunitySchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=256))
    address_line1 = fields.Str(required=True, validate=validate.Length(min=1, max=512))
    address_line2 = fields.Str(load_default=None)
    city = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    state = fields.Str(required=True, validate=validate.Regexp(_STATE_RE, error="state must be exactly 2 uppercase letters"))
    zip = fields.Str(required=True, validate=validate.Regexp(_ZIP_RE, error="zip must be a 5 or 9-digit US ZIP"))
    service_hours = fields.Dict(load_default={})
    fulfillment_scope = fields.Str(load_default="")


class UpdateCommunitySchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(validate=validate.Length(min=1, max=256))
    address_line1 = fields.Str(validate=validate.Length(min=1, max=512))
    address_line2 = fields.Str(allow_none=True)
    city = fields.Str(validate=validate.Length(min=1, max=128))
    state = fields.Str(validate=validate.Regexp(_STATE_RE, error="state must be exactly 2 uppercase letters"))
    zip = fields.Str(validate=validate.Regexp(_ZIP_RE, error="zip must be a 5 or 9-digit US ZIP"))
    service_hours = fields.Dict()
    fulfillment_scope = fields.Str()


class CreateServiceAreaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=256))
    address_line1 = fields.Str(required=True, validate=validate.Length(min=1, max=512))
    city = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    state = fields.Str(required=True, validate=validate.Regexp(_STATE_RE, error="state must be exactly 2 uppercase letters"))
    zip = fields.Str(required=True, validate=validate.Regexp(_ZIP_RE, error="zip must be a 5 or 9-digit US ZIP"))
    notes = fields.Str(load_default=None)


class UpdateServiceAreaSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(validate=validate.Length(min=1, max=256))
    address_line1 = fields.Str(validate=validate.Length(min=1, max=512))
    city = fields.Str(validate=validate.Length(min=1, max=128))
    state = fields.Str(validate=validate.Regexp(_STATE_RE, error="state must be exactly 2 uppercase letters"))
    zip = fields.Str(validate=validate.Regexp(_ZIP_RE, error="zip must be a 5 or 9-digit US ZIP"))
    notes = fields.Str(allow_none=True)
