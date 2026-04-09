"""Marshmallow schemas for inventory endpoints."""
from marshmallow import Schema, fields, validate, EXCLUDE


class CreateWarehouseSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=256))
    location = fields.Str(required=True, validate=validate.Length(min=1, max=512))
    notes = fields.Str(load_default=None)
    community_id = fields.Str(load_default=None)


class CreateBinSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    bin_code = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    description = fields.Str(load_default=None)


class ReceiptSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    sku_id = fields.Str(required=True)
    warehouse_id = fields.Str(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))
    bin_id = fields.Str(load_default=None)
    lot_number = fields.Str(load_default=None)
    costing_method = fields.Str(
        load_default="fifo",
        validate=validate.OneOf(["fifo", "moving_average"]),
    )
    unit_cost_usd = fields.Float(load_default=0)
    barcode = fields.Str(load_default=None)
    rfid = fields.Str(load_default=None)
    serial_numbers = fields.Raw(load_default=None)
    occurred_at = fields.Str(load_default=None)
    notes = fields.Str(load_default=None)


class IssueSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    sku_id = fields.Str(required=True)
    warehouse_id = fields.Str(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))
    bin_id = fields.Str(load_default=None)
    lot_number = fields.Str(load_default=None)
    barcode = fields.Str(load_default=None)
    rfid = fields.Str(load_default=None)
    serial_numbers = fields.Raw(load_default=None)
    reference = fields.Str(load_default=None)
    occurred_at = fields.Str(load_default=None)


class TransferSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    sku_id = fields.Str(required=True)
    from_warehouse_id = fields.Str(required=True)
    to_warehouse_id = fields.Str(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))
    from_bin_id = fields.Str(load_default=None)
    to_bin_id = fields.Str(load_default=None)
    lot_number = fields.Str(load_default=None)
    barcode = fields.Str(load_default=None)
    rfid = fields.Str(load_default=None)
    reference = fields.Str(load_default=None)
    notes = fields.Str(load_default=None)
    occurred_at = fields.Str(load_default=None)


class AdjustmentSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    sku_id = fields.Str(required=True)
    warehouse_id = fields.Str(required=True)
    quantity_delta = fields.Int(required=True)
    bin_id = fields.Str(load_default=None)
    reason = fields.Str(load_default=None)  # validated in service for custom error code
    occurred_at = fields.Str(load_default=None)


class CycleCountLineSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    sku_id = fields.Str(required=True)
    bin_id = fields.Str(load_default=None)
    counted_qty = fields.Int(required=True)
    variance_reason = fields.Str(load_default=None)


class CycleCountSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    warehouse_id = fields.Str(required=True)
    counted_at = fields.Str(required=True)
    lines = fields.List(fields.Nested(CycleCountLineSchema), required=True)
