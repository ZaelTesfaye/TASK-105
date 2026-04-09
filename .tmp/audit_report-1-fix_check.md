# Audit Report 1 - Fix Check

Date: 2026-04-09
Scope: Re-check findings `F-001` to `F-003` from `.tmp/audit_report-1.md` against the current code in `repo/backend`.

## Summary
- F-001: Fixed
- F-002: Fixed
- F-003: Fixed (with normal runtime-observability caveat)

## Finding-by-finding Verification

### F-001 - Service-area endpoints lack schema validation and can fail with malformed payloads
Status: Fixed

Evidence:
- Service-area routes now validate request payloads via Marshmallow before service calls:
  - `repo/backend/app/routes/communities.py` (`CreateServiceAreaSchema`, `UpdateServiceAreaSchema` in POST/PATCH handlers).
- Dedicated schemas exist with required fields and validators:
  - `repo/backend/app/schemas/community_schemas.py`
  - Required: `name`, `address_line1`, `city`, `state`, `zip`.
  - ZIP regex enforced via `^\d{5}(-\d{4})?$`.
  - State format enforced via `^[A-Z]{2}$`.
- Negative tests for malformed service-area payloads are present and passing:
  - `repo/backend/tests/api/test_api_communities.py`:
    - `test_create_service_area_missing_fields_400`
    - `test_create_service_area_invalid_state_400`
    - `test_create_service_area_invalid_zip_400`
    - `test_update_service_area_invalid_state_400`
    - `test_update_service_area_invalid_zip_400`

Validation run:
- `pytest -q backend/tests/api/test_api_communities.py` -> passed (`26 passed`).

### F-002 - Community update path does not enforce US ZIP format
Status: Fixed

Evidence:
- ZIP validation is enforced in update flow:
  - `repo/backend/app/services/community_service.py` checks `zip` in `update()` using `_ZIP_RE` and returns 400 on invalid format.
- Route-level schema also validates update ZIP format:
  - `repo/backend/app/routes/communities.py` uses `UpdateCommunitySchema`.
  - `repo/backend/app/schemas/community_schemas.py` has ZIP regex on `UpdateCommunitySchema.zip`.
- Test exists and passes:
  - `repo/backend/tests/api/test_api_communities.py::test_update_community_invalid_zip_400`.

Validation run:
- Included in `pytest -q backend/tests/api/test_api_communities.py` -> passed.

### F-003 - Observability structured for HTTP but not fully traceable across async/job flows
Status: Fixed (static + test evidence)

Evidence:
- Job wrapper injects correlation IDs for scheduled jobs:
  - `repo/backend/app/jobs/__init__.py` (`_with_context`, sets `g.correlation_id = "job-..."`).
- Async/job modules emit structured JSON logs with `correlation_id`:
  - `repo/backend/app/jobs/message_redelivery.py`
  - `repo/backend/app/jobs/safety_stock.py`
  - `repo/backend/app/jobs/slow_moving.py`
  - `repo/backend/app/jobs/trending_precompute.py`
  - `repo/backend/app/jobs/attachment_cleanup.py`
- WebSocket path also assigns correlation IDs:
  - `repo/backend/app/websocket.py` (`ws-connect`, `ws-direct`, `ws-group`, `ws-receipt`).
- Integration/API observability tests exist and pass:
  - `repo/backend/tests/integration/test_jobs.py::test_job_logs_include_correlation_id`
  - `repo/backend/tests/api/test_api_observability.py`

Validation run:
- `pytest -q backend/tests/integration/test_jobs.py::test_job_logs_include_correlation_id` -> passed.
- `pytest -q backend/tests/api/test_api_observability.py` -> passed (`15 passed`).

## Notes
- All targeted checks passed.
- Non-blocking environment warning observed during pytest runs:
  - `PytestCacheWarning` due to write access denied for `.pytest_cache`.
  - This did not affect test execution outcomes.
