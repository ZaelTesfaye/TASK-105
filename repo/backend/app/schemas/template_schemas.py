"""Marshmallow schemas for template endpoints."""
from marshmallow import Schema, fields, validate, validates, validates_schema, ValidationError, EXCLUDE

_ALLOWED_FIELD_TYPES = ("text", "number", "textarea", "date", "boolean", "enum", "select")


class TemplateFieldSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=256))
    type = fields.Str(required=True, validate=validate.OneOf(_ALLOWED_FIELD_TYPES))
    required = fields.Bool(load_default=False)
    enum = fields.List(fields.Str(), load_default=None)

    @validates_schema
    def validate_enum_field(self, data, **kwargs):
        if data.get("type") == "enum" and not data.get("enum"):
            raise ValidationError("enum list is required when type is 'enum'", field_name="enum")
        if data.get("type") != "enum" and data.get("enum"):
            raise ValidationError("enum list is only allowed when type is 'enum'", field_name="enum")


class CreateTemplateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=256))
    fields_ = fields.List(fields.Nested(TemplateFieldSchema), data_key="fields", load_default=[])


class UpdateTemplateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(validate=validate.Length(min=1, max=256))
    fields_ = fields.List(fields.Nested(TemplateFieldSchema), data_key="fields")
