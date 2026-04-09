# API Specification

**System:** Neighborhood Commerce & Content Operations Management System
**Base URL:** `/api/v1`
**Transport:** HTTP/1.1 (REST) + WebSocket (STOMP) for messaging
**Auth Scheme:** Session token via `Authorization: Bearer <token>` header

---

## Conventions

- All request/response bodies are JSON unless noted.
- Timestamps use ISO 8601 UTC: `"2026-03-31T14:00:00Z"`.
- Paginated endpoints accept `?page=1&page_size=20` (max `page_size=100`).
- Soft-deleted records are excluded from all responses unless `?include_deleted=true` is passed by an Administrator.
- `correlation_id` is returned in every response header as `X-Correlation-ID`.
- Error shape:
  ```json
  {
    "error": "short_code",
    "message": "Human-readable detail",
    "field": "optional_field_name"
  }
  ```

---

## 1. Authentication & Users

### `POST /auth/register`

Create a new user account.

**Roles:** Public (Administrator seeds first account; subsequent registrations may require admin invite token).

**Request:**

```json
{
  "username": "string (unique, max 64)",
  "password": "string (min 12 chars)",
  "role": "Member"
}
```

**Response `201`:**

```json
{
  "user_id": "uuid",
  "username": "string",
  "role": "Member",
  "created_at": "timestamp"
}
```

**Errors:** `400 password_too_short`, `409 username_taken`

---

### `POST /auth/login`

Authenticate and receive a session token.

**Request:**

```json
{ "username": "string", "password": "string" }
```

**Response `200`:**

```json
{
  "token": "string",
  "expires_at": "timestamp",
  "user_id": "uuid",
  "role": "string"
}
```

**Errors:** `401 invalid_credentials`, `423 account_locked` (includes `"retry_after": "timestamp"` after 5 failed attempts; lockout lasts 15 minutes)

---

### `POST /auth/logout`

Invalidate the current session token.

**Roles:** Authenticated

**Response `204`:** No content

---

### `GET /users`

List all users.

**Roles:** Administrator, Operations Manager

**Query params:** `?role=<role>&page=&page_size=`

**Response `200`:**

```json
{
  "total": 150,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "user_id": "uuid",
      "username": "string",
      "role": "string",
      "created_at": "timestamp",
      "deleted_at": "timestamp|null"
    }
  ]
}
```

---

### `GET /users/{user_id}`

Get a single user profile.

**Roles:** Administrator, Operations Manager, or self.

**Response `200`:**

```json
{
  "user_id": "uuid",
  "username": "string",
  "role": "string",
  "created_at": "timestamp"
}
```

---

### `PATCH /users/{user_id}`

Update role or username. Password and sensitive fields are updated via dedicated sub-resource.

**Roles:** Administrator (role changes); self (username changes).

**Request:**

```json
{ "role": "string (optional)", "username": "string (optional)" }
```

**Response `200`:** Updated user object.

---

### `PATCH /users/{user_id}/password`

Change password.

**Roles:** Self, Administrator

**Request:**

```json
{ "current_password": "string", "new_password": "string (min 12)" }
```

**Response `204`:** No content. All existing tokens invalidated.

---

### `DELETE /users/{user_id}`

Soft-delete a user.

**Roles:** Administrator

**Response `204`:** No content.

---

## 2. Communities & Service Areas

### `POST /communities`

Create a community.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{
  "name": "string",
  "address_line1": "string",
  "address_line2": "string (optional)",
  "city": "string",
  "state": "string (2-char US code)",
  "zip": "string (5 or 9 digit)",
  "service_hours": { "monday": "09:00-17:00", "...": "..." },
  "fulfillment_scope": "string (description)"
}
```

**Response `201`:**

```json
{ "community_id": "uuid", "name": "string", "created_at": "timestamp" }
```

---

### `GET /communities`

List communities.

**Roles:** All authenticated

**Query params:** `?city=&state=&page=&page_size=`

**Response `200`:** Paginated list of community objects.

---

### `GET /communities/{community_id}`

Get community detail including active group leader binding.

**Response `200`:**

```json
{
  "community_id": "uuid",
  "name": "string",
  "address": { "line1": "", "city": "", "state": "", "zip": "" },
  "service_hours": {},
  "fulfillment_scope": "string",
  "active_group_leader": { "user_id": "uuid", "username": "string" }
}
```

---

### `PATCH /communities/{community_id}`

Update community fields.

**Roles:** Administrator, Operations Manager

**Response `200`:** Updated community object.

---

### `DELETE /communities/{community_id}`

Soft-delete a community.

**Roles:** Administrator

**Response `204`**

---

### `POST /communities/{community_id}/service-areas`

Add a service area to a community.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{
  "name": "string",
  "address_line1": "string",
  "city": "string",
  "state": "string",
  "zip": "string",
  "notes": "string (optional)"
}
```

**Response `201`:**

```json
{ "service_area_id": "uuid", "community_id": "uuid", "name": "string" }
```

---

### `GET /communities/{community_id}/service-areas`

List service areas for a community.

**Response `200`:** Array of service area objects.

---

### `PATCH /communities/{community_id}/service-areas/{area_id}`

Update a service area.

**Roles:** Administrator, Operations Manager

**Response `200`:** Updated service area object.

---

### `DELETE /communities/{community_id}/service-areas/{area_id}`

Soft-delete a service area.

**Roles:** Administrator

**Response `204`**

---

## 3. Group Leader Bindings

### `POST /communities/{community_id}/leader-binding`

Bind (or replace) the active group leader for a community. Atomically deactivates any existing binding.

**Roles:** Administrator

**Request:**

```json
{ "user_id": "uuid (must have role=Group Leader)" }
```

**Response `201`:**

```json
{
  "binding_id": "uuid",
  "community_id": "uuid",
  "user_id": "uuid",
  "active": true,
  "bound_at": "timestamp"
}
```

**Errors:** `404 user_not_found`, `422 user_not_group_leader`

---

### `DELETE /communities/{community_id}/leader-binding`

Deactivate the current group leader binding.

**Roles:** Administrator

**Response `204`**

---

### `GET /communities/{community_id}/leader-binding/history`

View all past bindings (audit).

**Roles:** Administrator, Operations Manager

**Response `200`:** Array of binding records including `active`, `bound_at`, `unbound_at`.

---

## 4. Commission Rules & Settlement

### `POST /communities/{community_id}/commission-rules`

Create a commission rule for a product category within a community.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{
  "product_category": "string (optional; omit for community default)",
  "rate": 6.0,
  "floor": 0.0,
  "ceiling": 15.0,
  "settlement_cycle": "weekly | biweekly"
}
```

**Validation:** `0 ≤ floor ≤ rate ≤ ceiling ≤ 15.0`

**Response `201`:**

```json
{
  "rule_id": "uuid",
  "community_id": "uuid",
  "product_category": "string|null",
  "rate": 6.0,
  "floor": 0.0,
  "ceiling": 15.0,
  "settlement_cycle": "weekly"
}
```

---

### `GET /communities/{community_id}/commission-rules`

List all commission rules for a community. Category-level rules are shown alongside the community default.

**Roles:** Administrator, Operations Manager, Group Leader (own community only)

**Response `200`:** Array of rule objects.

**Resolution precedence (used by settlements):**

- `category_rule` for matching product category
- else community default rule (`product_category = null`)
- else system default `6.0%`

---

### `PATCH /communities/{community_id}/commission-rules/{rule_id}`

Update a commission rule (rate, floor, ceiling, cycle). Does not affect already-run settlements.

**Roles:** Administrator, Operations Manager

**Response `200`:** Updated rule.

---

### `DELETE /communities/{community_id}/commission-rules/{rule_id}`

Remove a commission rule. Community default cannot be deleted if settlements are pending.

**Roles:** Administrator

**Response `204`**

---

### `POST /settlements`

Initiate a settlement run.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{
  "community_id": "uuid",
  "period_start": "date (YYYY-MM-DD)",
  "period_end": "date",
  "idempotency_key": "string (required, unique)"
}
```

**Response `201`:**

```json
{
  "settlement_id": "uuid",
  "idempotency_key": "string",
  "status": "pending | processing | completed | disputed | cancelled",
  "community_id": "uuid",
  "period_start": "date",
  "period_end": "date",
  "created_at": "timestamp"
}
```

**Errors:** `409 duplicate_idempotency_key` (returns existing settlement object)

---

### `GET /settlements/{settlement_id}`

Get settlement detail.

**Roles:** Administrator, Operations Manager, Group Leader (own community)

**Response `200`:** Full settlement object with line items.

---

### `POST /settlements/{settlement_id}/disputes`

File a dispute against a settlement (within 2-day dispute window).

**Roles:** Administrator, Operations Manager, Group Leader (own community only)

**Request:**

```json
{ "reason": "string", "disputed_amount": 0.0 }
```

**Response `201`:**

```json
{
  "dispute_id": "uuid",
  "settlement_id": "uuid",
  "status": "open",
  "created_at": "timestamp"
}
```

**Errors:** `422 dispute_window_expired`

---

### `PATCH /settlements/{settlement_id}/disputes/{dispute_id}`

Resolve or reject a dispute.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{ "resolution": "resolved | rejected", "notes": "string" }
```

**Response `200`:** Updated dispute object.

---

### `POST /settlements/{settlement_id}/finalize`

Finalize a settlement after processing.

**Roles:** Administrator, Operations Manager

**Response `200`:** Settlement object with `status: "completed"` and `finalized_at`.

**Rules enforced server-side:**

- Finalization is blocked while any linked dispute is `open`.
- If any dispute is open, response is `422 settlement_blocked_by_open_dispute`.

---

## 5. Catalog & Search

### `POST /products`

Create a product.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{
  "sku": "string (unique)",
  "name": "string",
  "brand": "string",
  "category": "string",
  "description": "string (Markdown)",
  "price_usd": 0.0,
  "attributes": [{ "key": "string", "value": "string" }],
  "tags": ["string"]
}
```

**Response `201`:** Full product object.

---

### `GET /products/{product_id}`

Get a product.

**Roles:** All authenticated

**Response `200`:** Full product object with attributes and tags.

---

### `PATCH /products/{product_id}`

Update product fields.

**Roles:** Administrator, Operations Manager

**Response `200`:** Updated product.

---

### `DELETE /products/{product_id}`

Soft-delete a product.

**Roles:** Administrator

**Response `204`**

---

### `GET /search/products`

Full-text product search with filters.

**Roles:** All authenticated

**Query params:**
| Param | Type | Notes |
|-------|------|-------|
| `q` | string | Keyword query (triggers autocomplete suggestions) |
| `brand` | string | Filter by brand |
| `tags` | comma-list | Filter by attribute tags |
| `min_price` | decimal | USD |
| `max_price` | decimal | USD |
| `sort` | string | `sales_volume \| price_asc \| price_desc \| new_arrivals` |
| `page` | int | Default 1 |
| `page_size` | int | Default 20, max 100 |

**Response `200`:**

```json
{
  "total": 320,
  "page": 1,
  "page_size": 20,
  "items": [
    /* product objects */
  ],
  "zero_result_guidance": null
}
```

**Zero-result response** (when `total=0`):

```json
{
  "total": 0,
  "items": [],
  "zero_result_guidance": {
    "closest_brands": ["Brand A", "Brand B"],
    "closest_tags": ["tag1", "tag2"]
  }
}
```

Search queries are logged to `SearchLogs` for the authenticated user (capped at 50 entries per user; oldest is evicted).

---

### `GET /search/autocomplete`

Autocomplete suggestions for a partial query.

**Roles:** All authenticated

**Query params:** `?q=par`

**Response `200`:**

```json
{ "suggestions": ["partial match 1", "partial match 2"] }
```

---

### `GET /search/trending`

Top trending search terms in the last 7 days (frequency × recency-weighted score).

**Roles:** All authenticated

**Response `200`:**

```json
{ "trending": [{ "term": "string", "score": 1.23 }] }
```

---

### `GET /search/history`

Authenticated user's personal search history (max 50 entries, most recent first).

**Roles:** Authenticated (own history only)

**Response `200`:**

```json
{ "history": [{ "query": "string", "searched_at": "timestamp" }] }
```

---

### `DELETE /search/history`

Clear the authenticated user's search history.

**Response `204`**

---

## 6. Inventory & Warehouse

### `POST /warehouses`

Create a warehouse.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{ "name": "string", "location": "string", "notes": "string (optional)" }
```

**Response `201`:** Warehouse object with `warehouse_id`.

---

### `GET /warehouses`

List warehouses.

**Roles:** Administrator, Operations Manager, Staff

**Response `200`:** Array of warehouse objects.

---

### `POST /warehouses/{warehouse_id}/bins`

Create a bin location within a warehouse.

**Request:**

```json
{
  "bin_code": "string (unique within warehouse)",
  "description": "string (optional)"
}
```

**Response `201`:** Bin object.

---

### `GET /warehouses/{warehouse_id}/bins`

List bins in a warehouse.

**Response `200`:** Array of bin objects.

---

### `POST /inventory/receipts`

Record a stock receipt (inbound movement).

**Roles:** Administrator, Operations Manager, Staff

**Request:**

```json
{
  "warehouse_id": "uuid",
  "bin_id": "uuid (optional)",
  "sku_id": "uuid",
  "quantity": 100,
  "lot_number": "string (optional)",
  "serial_numbers": ["string"],
  "barcode": "string (format-validated, optional)",
  "rfid": "string (format-validated, optional)",
  "costing_method": "fifo | moving_average (only on first transaction for SKU)",
  "unit_cost_usd": 0.0,
  "occurred_at": "timestamp",
  "notes": "string (optional)"
}
```

**Response `201`:** Transaction object with `transaction_id`, `type: receipt"`.

---

### `POST /inventory/issues`

Record a stock issue (outbound movement). Resets slow-moving timer for SKU.

**Roles:** Administrator, Operations Manager, Staff

**Request:**

```json
{
  "warehouse_id": "uuid",
  "bin_id": "uuid (optional)",
  "sku_id": "uuid",
  "quantity": 10,
  "lot_number": "string (optional)",
  "serial_numbers": ["string"],
  "reference": "string (order or reason reference)",
  "occurred_at": "timestamp"
}
```

**Response `201`:** Transaction object with `type: "issue"`.

---

### `POST /inventory/transfers`

Transfer stock between warehouses or bins.

**Roles:** Administrator, Operations Manager, Staff

**Request:**

```json
{
  "from_warehouse_id": "uuid",
  "from_bin_id": "uuid (optional)",
  "to_warehouse_id": "uuid",
  "to_bin_id": "uuid (optional)",
  "sku_id": "uuid",
  "quantity": 5,
  "occurred_at": "timestamp"
}
```

**Response `201`:** Two linked transaction objects (issue + receipt).

---

### `POST /inventory/adjustments`

Manual quantity adjustment. Always writes an audit log entry.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{
  "warehouse_id": "uuid",
  "bin_id": "uuid (optional)",
  "sku_id": "uuid",
  "quantity_delta": -3,
  "reason": "string (required)",
  "occurred_at": "timestamp"
}
```

**Response `201`:** Transaction + audit log entry.

---

### `POST /inventory/cycle-counts`

Submit a cycle count.

**Roles:** Administrator, Operations Manager, Staff

**Request:**

```json
{
  "warehouse_id": "uuid",
  "counted_at": "timestamp",
  "lines": [
    {
      "sku_id": "uuid",
      "bin_id": "uuid (optional)",
      "counted_qty": 50,
      "variance_reason": "string (required if variance != 0)"
    }
  ]
}
```

**Response `201`:**

```json
{
  "cycle_count_id": "uuid",
  "lines": [
    {
      "sku_id": "uuid",
      "system_qty": 53,
      "counted_qty": 50,
      "variance": -3,
      "variance_reason": "string"
    }
  ]
}
```

---

### `GET /inventory/stock`

Query current on-hand stock.

**Roles:** Administrator, Operations Manager, Staff

**Query params:** `?sku_id=&warehouse_id=&bin_id=&below_safety_stock=true&slow_moving=true`

**Response `200`:**

```json
{
  "items": [
    {
      "sku_id": "uuid",
      "warehouse_id": "uuid",
      "bin_id": "uuid|null",
      "on_hand_qty": 47,
      "safety_stock_threshold": 10,
      "below_safety_stock": false,
      "slow_moving": false,
      "last_issue_at": "timestamp|null",
      "costing_method": "fifo | moving_average",
      "current_cost_usd": 9.99
    }
  ]
}
```

---

### `PATCH /products/{product_id}/safety-stock`

Set safety-stock threshold for a SKU.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{ "threshold": 10 }
```

**Response `200`:** Updated threshold.

---

### `GET /inventory/transactions`

Query inventory transaction history.

**Roles:** Administrator, Operations Manager, Staff

**Query params:** `?sku_id=&warehouse_id=&type=receipt|issue|transfer|adjustment&from=&to=&page=&page_size=`

**Response `200`:** Paginated list of transaction objects.

---

## 7. Messaging

### WebSocket Endpoint

`ws://<host>/ws/messaging`

Connect with `Authorization: Bearer <token>` in the STOMP `CONNECT` frame headers.

**STOMP destinations:**
| Destination | Direction | Description |
|-------------|-----------|-------------|
| `/user/queue/messages` | Subscribe | Receive direct messages |
| `/topic/community.<id>` | Subscribe | Receive group messages for a community |
| `/app/direct` | Send | Send a direct message |
| `/app/group` | Send | Send a group message |
| `/app/receipt` | Send | Acknowledge delivery or read |

---

### Message Payload (all types)

```json
{
  "message_id": "uuid",
  "type": "text | image_meta | file_meta | emoji | system",
  "sender_id": "uuid",
  "recipient_id": "uuid (direct) | null",
  "group_id": "uuid (community) | null",
  "body": "string (text/emoji; null for file/image types)",
  "file_metadata": {
    "filename": "string",
    "mime_type": "string",
    "size_bytes": 0
  },
  "sent_at": "timestamp",
  "delivery_status": "sent | delivered | read"
}
```

Note: No file bytes are stored or transmitted through messaging. Only metadata fields are accepted.

---

### REST Fallback (Offline Queue)

### `GET /messages`

Retrieve queued (undelivered) messages for the authenticated user.

**Roles:** Authenticated (own messages)

**Response `200`:** Array of message objects with `delivery_status: "sent"`.

Messages in the offline queue are retried with exponential backoff for up to 7 days, then purged.

---

### `POST /messages/{message_id}/receipt`

Confirm delivery or read status (REST fallback for STOMP receipt).

**Request:**

```json
{ "status": "delivered | read" }
```

**Response `200`:** Updated message with new `delivery_status`.

---

## 8. Content & Templates

### `POST /content`

Create a new content item (article, book, or chapter).

**Roles:** Administrator, Operations Manager, Moderator

**Request:**

```json
{
  "type": "article | book | chapter",
  "title": "string",
  "body": "string (Markdown or rich-text; sanitized server-side)",
  "parent_id": "uuid (chapter → book; optional)",
  "tags": ["string"],
  "categories": ["string"],
  "status": "draft"
}
```

**Response `201`:** Content item with `content_id`, `version: 1`, `status: "draft"`.

---

### `GET /content/{content_id}`

Get a content item (latest published version by default).

**Query params:** `?version=3` to retrieve a specific version.

**Roles:** All authenticated

**Response `200`:**

```json
{
  "content_id": "uuid",
  "type": "article",
  "title": "string",
  "body": "string",
  "version": 3,
  "status": "draft | published",
  "tags": [],
  "categories": [],
  "published_at": "timestamp|null",
  "created_at": "timestamp"
}
```

---

### `PATCH /content/{content_id}`

Update a content item (creates a new draft version; does not auto-publish).

**Roles:** Administrator, Operations Manager, Moderator

**Request:**

```json
{
  "title": "string (optional)",
  "body": "string (optional)",
  "tags": [],
  "categories": []
}
```

**Response `200`:** New draft version object.

---

### `POST /content/{content_id}/publish`

Publish the latest draft version.

**Roles:** Administrator, Operations Manager

**Response `200`:** Published content object with updated `status` and `published_at`.

---

### `POST /content/{content_id}/rollback`

Roll back to a prior published version.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{ "target_version": 2 }
```

**Response `200`:** Content object at rolled-back version, now active.

---

### `GET /content/{content_id}/versions`

List all versions of a content item.

**Roles:** Administrator, Operations Manager, Moderator

**Response `200`:** Array of version objects with `version`, `status`, `created_at`.

---

### `POST /content/{content_id}/attachments`

Upload an attachment (local storage; max 25 MB; allowed: png, jpg, pdf, txt, md).

**Roles:** Administrator, Operations Manager, Moderator

**Request:** `multipart/form-data` with field `file`.

**Response `201`:**

```json
{
  "attachment_id": "uuid",
  "content_id": "uuid",
  "filename": "string",
  "mime_type": "string",
  "size_bytes": 0,
  "sha256": "string",
  "created_at": "timestamp"
}
```

**Errors:** `413 file_too_large`, `415 unsupported_media_type`

---

### `GET /content/{content_id}/attachments`

List attachments for a content item.

**Response `200`:** Array of attachment objects.

---

### `DELETE /content/{content_id}/attachments/{attachment_id}`

Remove an attachment.

**Roles:** Administrator, Operations Manager

**Response `204`**

---

### `POST /templates`

Create a capture template.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{
  "name": "string",
  "fields": [
    {
      "name": "string",
      "type": "text | number | enum | bool | date",
      "enum_values": ["opt1"],
      "required": true
    }
  ]
}
```

**Response `201`:** Template with `template_id`, `version: 1`, `status: "draft"`.

---

### `GET /templates/{template_id}`

Get a template (latest published version by default).

**Query params:** `?version=2`

**Roles:** All authenticated

**Response `200`:** Template object with fields and version.

---

### `PATCH /templates/{template_id}`

Update a template (creates a new draft version; additive updates are always allowed).

**Roles:** Administrator, Operations Manager

**Rules enforced server-side:**

- Adding new optional fields: allowed.
- Removing or renaming fields: allowed in draft only when a migration is defined before publish.
- Changing an existing field type: allowed in draft only when a migration is defined before publish.
- Narrowing enum values: allowed in draft only when a migration is defined before publish.
- Publish is blocked with `422 migration_required` until required mappings exist.

**Response `200`:** New draft version.

---

### `POST /templates/{template_id}/publish`

Publish a template draft.

**Roles:** Administrator, Operations Manager

**Response `200`:** Published template.

---

### `POST /templates/{template_id}/rollback`

Roll back to a prior published template version.

**Request:**

```json
{ "target_version": 1 }
```

**Response `200`:** Rolled-back template; previous captures remain parseable.

---

### `GET /templates/{template_id}/versions`

List all template versions.

**Response `200`:** Array of version metadata objects.

---

### `POST /templates/{template_id}/migrations`

Define a field migration mapping between two versions (required for non-additive transitions before publish).

**Roles:** Administrator

**Request:**

```json
{
  "from_version": 2,
  "to_version": 3,
  "field_mappings": [
    {
      "from_field": "old_name",
      "to_field": "new_name",
      "transform": "identity | concat | default:<value>"
    }
  ]
}
```

**Response `201`:** Migration record.

---

## 9. Admin, Audit & Reports

### `GET /audit-log`

Query the immutable audit log.

**Roles:** Administrator

**Query params:** `?action_type=settlement|moderation|inventory&user_id=&from=&to=&page=&page_size=`

**Response `200`:**

```json
{
  "items": [
    {
      "log_id": "uuid",
      "action_type": "string",
      "actor_id": "uuid",
      "target_type": "string",
      "target_id": "uuid",
      "before": {},
      "after": {},
      "occurred_at": "timestamp",
      "correlation_id": "string"
    }
  ]
}
```

---

### `POST /admin/tickets`

Create an administrative ticket (moderation action or report).

**Roles:** Administrator, Operations Manager, Moderator

**Request:**

```json
{
  "type": "moderation | report | other",
  "subject": "string",
  "body": "string",
  "target_type": "user | content | product | community (optional)",
  "target_id": "uuid (optional)"
}
```

**Response `201`:** Ticket with `ticket_id`, `status: "open"`.

---

### `GET /admin/tickets`

List tickets.

**Roles:** Administrator, Operations Manager, Moderator (own tickets)

**Query params:** `?status=open|closed&type=&page=&page_size=`

**Response `200`:** Paginated ticket list.

---

### `PATCH /admin/tickets/{ticket_id}`

Update ticket status or add resolution notes.

**Roles:** Administrator, Operations Manager

**Request:**

```json
{ "status": "closed | in_progress", "resolution_notes": "string" }
```

**Response `200`:** Updated ticket. All state changes are appended to the audit log.

---

### `GET /admin/reports/group-leader-performance`

Group leader performance metrics scoped to their communities.

**Roles:** Administrator, Operations Manager; Group Leader (own community only).

**Query params:** `?community_id=&from=&to=`

**Response `200`:**

```json
{
  "community_id": "uuid",
  "period": { "from": "date", "to": "date" },
  "total_orders": 150,
  "total_order_value_usd": 12345.67,
  "commission_earned_usd": 740.74,
  "top_products": [{ "sku_id": "uuid", "name": "string", "units_sold": 30 }]
}
```

---

## 10. Observability

### `GET /health`

Liveness probe.

**Roles:** Public

**Response `200`:**

```json
{ "status": "ok", "version": "string", "db": "ok | degraded" }
```

---

### `GET /health/ready`

Readiness probe (checks DB connectivity and background job queue).

**Response `200`:** `{ "status": "ready" }` or `503` with detail.
