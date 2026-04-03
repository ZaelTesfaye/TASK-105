from marshmallow import Schema, fields, validate, EXCLUDE

# Mirrors app.models.user.ROLES — kept here to avoid circular import
_VALID_ROLES = (
    "Administrator", "Operations Manager", "Moderator",
    "Group Leader", "Staff", "Member",
)


class RegisterSchema(Schema):
    class Meta:
        unknown = EXCLUDE  # silently ignore any extra unknown fields

    username = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=64, error="Username must be between 1 and 64 characters"),
    )
    # Password min-length business rule enforced in AuthService (returns password_too_short error code)
    password = fields.Str(required=True, load_only=True)
    # role is optional at the public endpoint (route hardcodes "Member"), but if provided
    # it must be a known role so callers get a clear error rather than silent rejection.
    role = fields.Str(
        load_default=None,
        validate=validate.OneOf(_VALID_ROLES, error=f"Role must be one of: {', '.join(_VALID_ROLES)}"),
    )


class LoginSchema(Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True, load_only=True)
