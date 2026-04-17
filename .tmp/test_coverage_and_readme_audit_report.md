# Test Coverage Audit

## Scope and Method
- Mode: static inspection only (no test execution, no builds, no package install).
- Audited paths: repo/backend/app/routes, repo/backend/tests/{api,integration,unit}, repo/run_tests.sh, repo/run_tests.ps1, repo/README.md.
- Project type declaration: backend (explicit in repo/README.md:1).

## Backend Endpoint Inventory
Resolved from Flask blueprint decorators plus /api/v1 prefix in repo/backend/app/__init__.py.

- Total HTTP endpoints: 82
- Health endpoints outside version prefix: /health, /health/ready
- All other route blueprints mounted under: /api/v1

## API Test Mapping Table`n`n| Endpoint | Covered | Test Type | Test Files | Evidence |
|---|---|---|---|---|
| GET /api/v1/admin/reports/group-leader-performance | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py | repo/backend/tests/api/test_api_admin.py:132; repo/backend/tests/api/test_api_admin.py:146 |
| GET /api/v1/admin/tickets | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py, repo/backend/tests/integration/test_admin.py | repo/backend/tests/api/test_api_admin.py:46; repo/backend/tests/api/test_api_admin.py:55 |
| POST /api/v1/admin/tickets | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py, repo/backend/tests/integration/test_admin.py | repo/backend/tests/api/test_api_admin.py:21; repo/backend/tests/integration/test_admin.py:5 |
| PATCH /api/v1/admin/tickets/<ticket_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py, repo/backend/tests/integration/test_admin.py | repo/backend/tests/api/test_api_admin.py:68; repo/backend/tests/integration/test_admin.py:26 |
| GET /api/v1/audit-log | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py, repo/backend/tests/integration/test_admin.py | repo/backend/tests/api/test_api_admin.py:79; repo/backend/tests/api/test_api_admin.py:87 |
| POST /api/v1/auth/login | yes | true no-mock HTTP | repo/backend/tests/api/conftest.py, repo/backend/tests/api/test_api_admin.py, repo/backend/tests/api/test_api_auth.py, repo/backend/tests/api/test_api_commission.py, repo/backend/tests/api/test_api_communities.py, repo/backend/tests/api/test_api_content.py, repo/backend/tests/api/test_api_messaging.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/api/test_api_users.py, repo/backend/tests/integration/conftest.py, repo/backend/tests/integration/test_auth.py, repo/backend/tests/integration/test_commission.py, repo/backend/tests/integration/test_jobs.py, repo/backend/tests/integration/test_messaging.py, repo/backend/tests/integration/test_observability.py, repo/backend/tests/integration/test_search_performance.py, repo/backend/tests/integration/test_users.py | repo/backend/tests/api/conftest.py:31; repo/backend/tests/api/test_api_admin.py:192 |
| POST /api/v1/auth/logout | yes | true no-mock HTTP | repo/backend/tests/api/test_api_auth.py, repo/backend/tests/integration/test_auth.py | repo/backend/tests/api/test_api_auth.py:133; repo/backend/tests/api/test_api_auth.py:144 |
| POST /api/v1/auth/register | yes | true no-mock HTTP | repo/backend/tests/api/test_api_auth.py, repo/backend/tests/api/test_api_communities.py, repo/backend/tests/api/test_api_content.py, repo/backend/tests/api/test_api_messaging.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/api/test_api_users.py, repo/backend/tests/integration/test_auth.py, repo/backend/tests/integration/test_jobs.py, repo/backend/tests/integration/test_messaging.py, repo/backend/tests/integration/test_observability.py, repo/backend/tests/integration/test_users.py | repo/backend/tests/api/test_api_auth.py:20; repo/backend/tests/api/test_api_auth.py:75 |
| GET /api/v1/communities | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py, repo/backend/tests/integration/test_communities.py | repo/backend/tests/api/test_api_communities.py:92; repo/backend/tests/integration/test_communities.py:23 |
| POST /api/v1/communities | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py, repo/backend/tests/api/test_api_commission.py, repo/backend/tests/api/test_api_communities.py, repo/backend/tests/api/test_api_messaging.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/integration/test_commission.py, repo/backend/tests/integration/test_communities.py, repo/backend/tests/integration/test_messaging.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_admin.py:125; repo/backend/tests/api/test_api_commission.py:23 |
| DELETE /api/v1/communities/<community_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:120 |
| GET /api/v1/communities/<community_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py, repo/backend/tests/integration/test_communities.py | repo/backend/tests/api/test_api_communities.py:102; repo/backend/tests/api/test_api_communities.py:122 |
| PATCH /api/v1/communities/<community_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:112; repo/backend/tests/api/test_api_communities.py:278 |
| GET /api/v1/communities/<community_id>/commission-rules | yes | true no-mock HTTP | repo/backend/tests/integration/test_commission.py | repo/backend/tests/integration/test_commission.py:124 |
| POST /api/v1/communities/<community_id>/commission-rules | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/integration/test_commission.py | repo/backend/tests/api/test_api_commission.py:42; repo/backend/tests/integration/test_commission.py:33 |
| DELETE /api/v1/communities/<community_id>/commission-rules/<rule_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/integration/test_commission.py | repo/backend/tests/api/test_api_commission.py:125; repo/backend/tests/integration/test_commission.py:120 |
| PATCH /api/v1/communities/<community_id>/commission-rules/<rule_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/integration/test_commission.py | repo/backend/tests/api/test_api_commission.py:99; repo/backend/tests/api/test_api_commission.py:112 |
| DELETE /api/v1/communities/<community_id>/leader-binding | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:204 |
| POST /api/v1/communities/<community_id>/leader-binding | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py, repo/backend/tests/api/test_api_commission.py, repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_admin.py:199; repo/backend/tests/api/test_api_admin.py:231 |
| GET /api/v1/communities/<community_id>/leader-binding/history | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:388; repo/backend/tests/api/test_api_communities.py:397 |
| DELETE /api/v1/communities/<community_id>/members | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:223 |
| GET /api/v1/communities/<community_id>/members | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:240 |
| POST /api/v1/communities/<community_id>/members | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py, repo/backend/tests/api/test_api_messaging.py, repo/backend/tests/integration/test_messaging.py | repo/backend/tests/api/test_api_communities.py:215; repo/backend/tests/api/test_api_communities.py:222 |
| GET /api/v1/communities/<community_id>/service-areas | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:166; repo/backend/tests/api/test_api_communities.py:422 |
| POST /api/v1/communities/<community_id>/service-areas | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py, repo/backend/tests/integration/test_communities.py | repo/backend/tests/api/test_api_communities.py:133; repo/backend/tests/api/test_api_communities.py:146 |
| DELETE /api/v1/communities/<community_id>/service-areas/<area_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:418; repo/backend/tests/api/test_api_communities.py:432 |
| PATCH /api/v1/communities/<community_id>/service-areas/<area_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_communities.py | repo/backend/tests/api/test_api_communities.py:353; repo/backend/tests/api/test_api_communities.py:371 |
| POST /api/v1/content | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/integration/test_content.py, repo/backend/tests/integration/test_jobs.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_content.py:26; repo/backend/tests/api/test_api_content.py:59 |
| GET /api/v1/content/<content_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:102; repo/backend/tests/api/test_api_content.py:135 |
| PATCH /api/v1/content/<content_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:111; repo/backend/tests/api/test_api_content.py:131 |
| GET /api/v1/content/<content_id>/attachments | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:208; repo/backend/tests/api/test_api_content.py:222 |
| POST /api/v1/content/<content_id>/attachments | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py, repo/backend/tests/integration/test_jobs.py | repo/backend/tests/api/test_api_content.py:32; repo/backend/tests/integration/test_content.py:119 |
| DELETE /api/v1/content/<content_id>/attachments/<attachment_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py, repo/backend/tests/integration/test_jobs.py | repo/backend/tests/api/test_api_content.py:219; repo/backend/tests/integration/test_content.py:172 |
| POST /api/v1/content/<content_id>/publish | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:120; repo/backend/tests/api/test_api_content.py:329 |
| POST /api/v1/content/<content_id>/rollback | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:132; repo/backend/tests/integration/test_content.py:76 |
| GET /api/v1/content/<content_id>/versions | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:144; repo/backend/tests/integration/test_content.py:91 |
| POST /api/v1/inventory/adjustments | yes | true no-mock HTTP | repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py | repo/backend/tests/api/test_api_inventory.py:220; repo/backend/tests/api/test_api_inventory.py:235 |
| POST /api/v1/inventory/cycle-counts | yes | true no-mock HTTP | repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py | repo/backend/tests/api/test_api_inventory.py:254; repo/backend/tests/api/test_api_inventory.py:270 |
| POST /api/v1/inventory/issues | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py, repo/backend/tests/integration/test_jobs.py | repo/backend/tests/api/test_api_commission.py:355; repo/backend/tests/api/test_api_inventory.py:59 |
| POST /api/v1/inventory/receipts | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/integration/test_inventory.py, repo/backend/tests/integration/test_jobs.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_commission.py:346; repo/backend/tests/api/test_api_inventory.py:48 |
| GET /api/v1/inventory/stock | yes | true no-mock HTTP | repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py | repo/backend/tests/api/test_api_inventory.py:68; repo/backend/tests/api/test_api_inventory.py:307 |
| GET /api/v1/inventory/transactions | yes | true no-mock HTTP | repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py | repo/backend/tests/api/test_api_inventory.py:323; repo/backend/tests/api/test_api_inventory.py:336 |
| POST /api/v1/inventory/transfers | yes | true no-mock HTTP | repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py | repo/backend/tests/api/test_api_inventory.py:200; repo/backend/tests/integration/test_inventory.py:260 |
| GET /api/v1/messages | yes | true no-mock HTTP | repo/backend/tests/api/test_api_messaging.py, repo/backend/tests/integration/test_messaging.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_messaging.py:114; repo/backend/tests/api/test_api_messaging.py:125 |
| POST /api/v1/messages | yes | true no-mock HTTP | repo/backend/tests/api/test_api_messaging.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/integration/test_jobs.py, repo/backend/tests/integration/test_messaging.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_messaging.py:35; repo/backend/tests/api/test_api_messaging.py:73 |
| POST /api/v1/messages/<message_id>/receipt | yes | true no-mock HTTP | repo/backend/tests/api/test_api_messaging.py, repo/backend/tests/integration/test_messaging.py | repo/backend/tests/api/test_api_messaging.py:138; repo/backend/tests/api/test_api_messaging.py:147 |
| POST /api/v1/products | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py, repo/backend/tests/api/test_api_commission.py, repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/integration/test_catalog.py, repo/backend/tests/integration/test_inventory.py, repo/backend/tests/integration/test_jobs.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_catalog.py:30; repo/backend/tests/api/test_api_catalog.py:199 |
| DELETE /api/v1/products/<product_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py, repo/backend/tests/integration/test_catalog.py | repo/backend/tests/api/test_api_catalog.py:93; repo/backend/tests/integration/test_catalog.py:51 |
| GET /api/v1/products/<product_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py, repo/backend/tests/integration/test_catalog.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_catalog.py:69; repo/backend/tests/api/test_api_catalog.py:76 |
| PATCH /api/v1/products/<product_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py | repo/backend/tests/api/test_api_catalog.py:85; repo/backend/tests/api/test_api_catalog.py:224 |
| PATCH /api/v1/products/<product_id>/safety-stock | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py, repo/backend/tests/api/test_api_inventory.py | repo/backend/tests/api/test_api_catalog.py:187; repo/backend/tests/api/test_api_inventory.py:302 |
| GET /api/v1/search/autocomplete | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py | repo/backend/tests/api/test_api_catalog.py:140 |
| DELETE /api/v1/search/history | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py | repo/backend/tests/api/test_api_catalog.py:162 |
| GET /api/v1/search/history | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py, repo/backend/tests/integration/test_catalog.py | repo/backend/tests/api/test_api_catalog.py:151; repo/backend/tests/api/test_api_catalog.py:164 |
| GET /api/v1/search/products | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py, repo/backend/tests/integration/test_catalog.py, repo/backend/tests/integration/test_jobs.py, repo/backend/tests/integration/test_search_performance.py | repo/backend/tests/api/test_api_catalog.py:107; repo/backend/tests/api/test_api_catalog.py:116 |
| GET /api/v1/search/trending | yes | true no-mock HTTP | repo/backend/tests/api/test_api_catalog.py | repo/backend/tests/api/test_api_catalog.py:173 |
| POST /api/v1/settlements | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/integration/test_commission.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_commission.py:49; repo/backend/tests/api/test_api_commission.py:363 |
| GET /api/v1/settlements/<settlement_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py | repo/backend/tests/api/test_api_commission.py:393; repo/backend/tests/api/test_api_commission.py:407 |
| POST /api/v1/settlements/<settlement_id>/disputes | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/integration/test_commission.py | repo/backend/tests/api/test_api_commission.py:168; repo/backend/tests/api/test_api_commission.py:188 |
| PATCH /api/v1/settlements/<settlement_id>/disputes/<dispute_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/integration/test_commission.py | repo/backend/tests/api/test_api_commission.py:205; repo/backend/tests/api/test_api_commission.py:222 |
| POST /api/v1/settlements/<settlement_id>/finalize | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/integration/test_commission.py | repo/backend/tests/api/test_api_commission.py:242; repo/backend/tests/api/test_api_commission.py:260 |
| POST /api/v1/templates | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:48; repo/backend/tests/api/test_api_content.py:609 |
| GET /api/v1/templates/<template_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py | repo/backend/tests/api/test_api_content.py:358; repo/backend/tests/api/test_api_content.py:362 |
| PATCH /api/v1/templates/<template_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:252; repo/backend/tests/api/test_api_content.py:267 |
| GET /api/v1/templates/<template_id>/attachments | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py | repo/backend/tests/api/test_api_content.py:555; repo/backend/tests/api/test_api_content.py:569 |
| POST /api/v1/templates/<template_id>/attachments | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py | repo/backend/tests/api/test_api_content.py:528 |
| DELETE /api/v1/templates/<template_id>/attachments/<attachment_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py | repo/backend/tests/api/test_api_content.py:566 |
| POST /api/v1/templates/<template_id>/migrations | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:280; repo/backend/tests/integration/test_content.py:232 |
| POST /api/v1/templates/<template_id>/publish | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:242; repo/backend/tests/api/test_api_content.py:251 |
| POST /api/v1/templates/<template_id>/rollback | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:303; repo/backend/tests/integration/test_content.py:252 |
| GET /api/v1/templates/<template_id>/versions | yes | true no-mock HTTP | repo/backend/tests/api/test_api_content.py, repo/backend/tests/integration/test_content.py | repo/backend/tests/api/test_api_content.py:313; repo/backend/tests/api/test_api_content.py:446 |
| GET /api/v1/users | yes | true no-mock HTTP | repo/backend/tests/api/test_api_auth.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/api/test_api_users.py, repo/backend/tests/integration/test_users.py | repo/backend/tests/api/test_api_auth.py:156; repo/backend/tests/api/test_api_observability.py:133 |
| DELETE /api/v1/users/<user_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_users.py, repo/backend/tests/integration/test_users.py | repo/backend/tests/api/test_api_users.py:199; repo/backend/tests/api/test_api_users.py:207 |
| GET /api/v1/users/<user_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_auth.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/api/test_api_users.py, repo/backend/tests/integration/test_auth.py, repo/backend/tests/integration/test_users.py | repo/backend/tests/api/test_api_auth.py:146; repo/backend/tests/api/test_api_observability.py:156 |
| PATCH /api/v1/users/<user_id> | yes | true no-mock HTTP | repo/backend/tests/api/test_api_users.py, repo/backend/tests/integration/test_users.py | repo/backend/tests/api/test_api_users.py:128; repo/backend/tests/api/test_api_users.py:136 |
| PATCH /api/v1/users/<user_id>/password | yes | true no-mock HTTP | repo/backend/tests/api/test_api_users.py, repo/backend/tests/integration/test_users.py | repo/backend/tests/api/test_api_users.py:164; repo/backend/tests/api/test_api_users.py:174 |
| GET /api/v1/warehouses | yes | true no-mock HTTP | repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py | repo/backend/tests/api/test_api_inventory.py:97; repo/backend/tests/integration/test_inventory.py:52 |
| POST /api/v1/warehouses | yes | true no-mock HTTP | repo/backend/tests/api/test_api_commission.py, repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/integration/test_inventory.py, repo/backend/tests/integration/test_jobs.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_commission.py:320; repo/backend/tests/api/test_api_commission.py:325 |
| GET /api/v1/warehouses/<warehouse_id>/bins | yes | true no-mock HTTP | repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py | repo/backend/tests/api/test_api_inventory.py:121; repo/backend/tests/integration/test_inventory.py:69 |
| POST /api/v1/warehouses/<warehouse_id>/bins | yes | true no-mock HTTP | repo/backend/tests/api/test_api_inventory.py, repo/backend/tests/integration/test_inventory.py | repo/backend/tests/api/test_api_inventory.py:109; repo/backend/tests/api/test_api_inventory.py:120 |
| GET /health | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/integration/test_admin.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_admin.py:97; repo/backend/tests/api/test_api_observability.py:55 |
| GET /health/ready | yes | true no-mock HTTP | repo/backend/tests/api/test_api_admin.py, repo/backend/tests/api/test_api_observability.py, repo/backend/tests/integration/test_observability.py | repo/backend/tests/api/test_api_admin.py:108; repo/backend/tests/api/test_api_observability.py:94 |
## API Test Classification
1. True No-Mock HTTP
- repo/backend/tests/api/test_api_admin.py
- repo/backend/tests/api/test_api_auth.py
- repo/backend/tests/api/test_api_catalog.py
- repo/backend/tests/api/test_api_commission.py
- repo/backend/tests/api/test_api_communities.py
- repo/backend/tests/api/test_api_content.py
- repo/backend/tests/api/test_api_inventory.py
- repo/backend/tests/api/test_api_messaging.py
- repo/backend/tests/api/test_api_observability.py
- repo/backend/tests/api/test_api_users.py
- Plus HTTP integration coverage in repo/backend/tests/integration/*.py via Flask test_client().

2. HTTP with Mocking
- None detected for HTTP endpoint tests.

3. Non-HTTP (unit/integration without HTTP)
- repo/backend/tests/api/test_api_websocket.py (SocketIO namespace /ws/messaging; no HTTP method+path).
- repo/backend/tests/api/test_api_stomp.py (direct STOMP handler invocation).
- repo/backend/tests/unit/*.py service/middleware unit tests.

## Mock Detection
Detected transport stubbing/bypass (non-HTTP tests):
- _FakeWs stub WebSocket transport in repo/backend/tests/api/test_api_stomp.py.
- Direct handler execution _handle_stomp_connection(...) in repo/backend/tests/api/test_api_stomp.py bypasses HTTP route layer.
- No evidence found of jest.mock, vi.mock, sinon.stub, mock.patch, or DI override mocking in backend tests.

## Coverage Summary
- Total endpoints: 82
- Endpoints with HTTP tests: 82
- Endpoints with TRUE no-mock HTTP tests: 82
- HTTP coverage: 100%
- True API coverage: 100%

## Unit Test Summary
### Backend Unit Tests
Detected files:
- repo/backend/tests/unit/test_admin_unit.py
- repo/backend/tests/unit/test_audit_unit.py
- repo/backend/tests/unit/test_auth_unit.py
- repo/backend/tests/unit/test_commission_unit.py
- repo/backend/tests/unit/test_content_unit.py
- repo/backend/tests/unit/test_inventory_unit.py
- repo/backend/tests/unit/test_messaging_unit.py
- repo/backend/tests/unit/test_search_unit.py
- repo/backend/tests/unit/test_security_redaction_crypto.py
- repo/backend/tests/unit/test_user_unit.py

Modules covered:
- Services: auth, user, admin, audit, commission, content, template, inventory, messaging, search.
- Models/business entities: user/session, messaging receipts, commission, content/template, inventory layers.
- Middleware/security: logging redaction and credential leakage checks.

Important backend modules not unit-tested directly:
- Route/controller modules under repo/backend/app/routes/*.py (covered through HTTP tests instead).
- RBAC/auth middleware internals (repo/backend/app/middleware/auth.py, rbac.py) mostly validated indirectly via API tests.
- STOMP/WebSocket handler internals are API-style tested, not classic unit-tested.

### Frontend Unit Tests (Strict Check)
- Frontend test files: NONE
- Frameworks/tools detected: NONE
- Frontend components/modules covered: NONE
- Important frontend components/modules not tested: N/A (backend-only repository)
- Frontend unit tests verdict: N/A (project type is backend)

### Cross-Layer Observation
- Repository is backend-only by structure and README declaration.

## API Observability Check
- Endpoint/method, request payload/query, and response assertions are explicit across API tests.
- Weak spots: some shape-only assertions reduce strictness.

## Test Quality & Sufficiency
Strengths:
- Broad success/failure coverage across auth, RBAC, validation, and domain flows.
- Strong negative-path and permission checks.
- Integration coverage reinforces API scenarios.

Risks:
- STOMP tests use fake transport and direct handler execution (not full network realism).

run_tests.sh check:
- Docker-based: OK (repo/run_tests.sh).
- Local dependency path exists (repo/run_tests.ps1 requires host Python/pytest): FLAG.

## End-to-End Expectations
- Backend project: fullstack FE-BE E2E requirement is not applicable.

## Tests Check
- Static evidence indicates complete HTTP endpoint coverage.
- Realtime messaging covered, but STOMP transport realism is partially stubbed.

## Test Coverage Score (0-100)
- 92/100

## Score Rationale
- Complete HTTP endpoint coverage (82/82)
- Strong auth/validation/negative-path depth
- Broad unit+API+integration footprint
- Deduction for STOMP fake transport and some broad assertions

## Key Gaps
- STOMP tests partly bypass transport stack via _FakeWs and direct handler invocation.
- PowerShell test path conflicts with strict container-only testing policy.

## Confidence & Assumptions
- Confidence: High
- Endpoint universe inferred from route decorators in repo/backend/app/routes/*.py plus blueprint prefixing in repo/backend/app/__init__.py.

---

# README Audit

## README Location
- Found: repo/README.md

## Hard Gate Evaluation
### Formatting
- PASS

### Startup Instructions (Backend)
- PASS: docker-compose up --build present (repo/README.md:56-58).

### Access Method
- PASS: API/health URLs listed (repo/README.md:71-74).

### Verification Method
- PASS: curl verification flow provided (repo/README.md:88-100).

### Environment Rules (Docker-only, strict)
- FAIL:
  - Host-dependent Windows test command documented (repo/README.md:157).
  - Script requires host Python/pytest and references pip install (repo/run_tests.ps1:22-23).

### Demo Credentials (auth exists -> all roles required)
- FAIL:
  - Staff role has no credentials (repo/README.md:116).

## Engineering Quality
- Tech stack clarity: strong.
- Architecture explanation: moderate-good.
- Testing instructions: good, but policy inconsistency exists.
- Security/roles communication: clear but strict credentials completeness fails.

## High Priority Issues
- Docker-only policy contradiction via host-dependent test path/script.
- Missing Staff demo credentials while auth/roles are present.

## Medium Priority Issues
- Statement says all roles represented, but Staff has no seeded account.

## Low Priority Issues
- None material beyond hard-gate failures.

## Hard Gate Failures
- Environment rules (Docker-contained only): FAILED
- Demo credentials for all auth roles: FAILED

## README Verdict (PASS / PARTIAL PASS / FAIL)
- FAIL

---

## Final Verdicts
- Test Coverage Audit: PASS (with quality risks)
- README Audit: FAIL

