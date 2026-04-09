Project Implementation & Delivery Guide

This guide is the "Developer's Blueprint" to passing a professional Architecture & Delivery Audit. Follow these phases to ensure a 0-to-1 deliverable that is robust, runnable, and high-quality.

Phase 0: Requirement Alignment (The Foundation)

Goal: Ensure 100% compliance with the business intent before writing code.

Placeholder Prompt Placement:

[INSERT ORIGINAL BUSINESS PROMPT HERE]: Always paste the specific task requirements here to serve as the North Star for the implementation.

Strict Requirement Adherence:

Zero Overscoping: Do not add "gold-plated" features not requested in the prompt.

100% Coverage: Every explicit requirement in the prompt must be mapped to a functional component or logic path.

User Flow Definition:

Before coding, define the "Path to Success" for every user persona mentioned (e.g., Guest, Registered User, Admin).

Map out the step-by-step interactions required for a user to complete the core business objective.

Phase 1: Initialization & Runnability (The Hard Gates)

Goal: Ensure the project can be started by any stakeholder without pain. Failure here results in a "One-Vote Veto".

Standardized Entry Point:

One-Click Startup: Create a README.md containing only Docker commands. The project must strictly support docker-compose up --build.

Environment Management: All environment variables must be defined in the root docker-compose.yml.

Configuration Flow: Every variable must pass through a dedicated "Main Config" module. Application logic must never access process.env or os.getenv directly.

TLS Toggle: The Config module must include a ENABLE_TLS toggle (Boolean). Default: false.

Zero Intervention: No manual file creation (e.g., copying .env.example), folder creation, or interactive command-line inputs are allowed.

Strict Environment Isolation:

No Host Dependence: Services must not attempt to connect to host-level databases/Redis not declared in docker-compose.yml.

No Path Dependence: Absolute paths (e.g., C:/Users/...) are strictly forbidden. Use relative paths within the container.

Documentation Consistency: Port mapping in README.md must match docker-compose.yml exactly.

Phase 2: Architecture & Module Design

Goal: High maintainability and clear separation of concerns using the mandated repository structure.

Mandatory Repository Structure:

/repo
├── backend/
│ ├── config/ # "Clean" Config module (Single source of truth)
│ ├── logging/ # Centralized Logger definition
│ ├── tests/  
│ │ ├── unit/ # Isolated Unit tests
│ │ └── api/ # Isolated API/Integration tests
│ └── [src_logic]
├── frontend/
│ ├── tests/
│ │ ├── unit/ # Unit test sub-folder
│ │ └── e2e/ # End-to-End test sub-folder
│ └── [src_logic]
├── docker-compose.yml # Main orchestration (defines all env vars)
├── run_tests.sh # Global test execution script
└── README.md

Clean Config Pattern:

Provide type safety and default values. Centralize all external resource URLs and security toggles here.

Anonymization: Ensure no personal keys (AK/SK) or intranet IPs are hardcoded in config files.

Phase 3: Security & Data Integrity

Goal: Zero high-risk vulnerabilities and logical "Business Closed Loops".

Non-Negotiable Security:

RBAC (Role-Based Access Control): Every project must implement RBAC by default. Define roles (e.g., Admin, User) and enforce permissions at the route and controller levels.

Authentication & Authorization: Implement Route Guards (Frontend) and Middleware (Backend).

Object-Level Authorization: Users can only see/edit their own data (BOLA/IDOR protection).

Requirement Fidelity:

Prohibit Unauthorized Simplification: Do not replace core requirements (e.g., swapping WebSocket for HTTP polling) to reduce difficulty.

Identify Implicit Constraints: Implementation must make business sense (e.g., inventory cannot be negative; reservations cannot overlap).

Phase 4: Engineering Professionalism & Logging

External Service Mocking (Mandatory Rule):

Allowed Mocks: You are never allowed to integrate real 3rd party external services (e.g., Stripe, AWS SES, Twilio, SendGrid).

Implementation: These must be mocked using internal stubs. The application must function as if the service responded successfully.

Documentation: Provide clear comments in the code explaining the stub logic (e.g., // Mocking Payment Gateway response for audit stability).

Centralized Logging (Backend):

Structured Format: Use [stub][sub-stub] message.

Mandatory Interception: Log every route request/outcome, every exception, and every promise rejection.

Redaction: Automatically redact sensitive data (passwords, tokens, SSNs).

Robust Error Handling:

Elegant Degradation: Return standard HTTP status codes and clear JSON prompts. Do NOT throw raw Stack Traces.

Front-end Fault Tolerance: Use Toasts or default pages for failures; no "White Screens."

Clean Code:

Remove all node_modules/, .venv/, and cache files before submission.

Remove deprecated/commented-out code and console.log statements.

API Beautification: Ensure JSON returns are paginated and structured for readability.

Phase 5: Testing & Verification

Goal: Pass the mandatory 3.3.4 Testing Standards.

The run_tests.sh Script:

Must automatically call all tests in backend/tests/ and frontend/tests/.

Must output a clear summary: Total tests, Passes, Failures, and error logs for failures.

Coverage & Quality Targets:

API Test Coverage: Backend API tests must achieve >= 90% code coverage.

Unit Tests: Must cover main functional modules, state transitions, and exception handling logic.

API Tests: Must cover normal requests, abnormal scenarios, and permission (RBAC) checks.

Phase 6: Final Quality Acceptance (Self-Test Report)

Before submitting, you MUST generate a self-test report against these dimensions.

3.1 Hard Thresholds (One-Vote Veto)

[ ] One-click startup: Does docker-compose up work without any manual file edits or errors?

[ ] Environment Isolation: Are there zero absolute paths or host-specific dependencies?

[ ] Core Goal Consistency (Expanded):

[ ] Have the user flows for all personas been fully implemented?

[ ] Is the implementation a 100% match for the original prompt requirements?

[ ] Does the project solve the actual business problem rather than just providing a technical demo?

3.2 Delivery Integrity

[ ] 0-1 Completeness: Is this a complete project (src, config, tests) rather than code snippets?

[ ] Reject Mock Spoofing: Is core business logic (login, RBAC, DB processing) real?

[ ] External Mocks: Are 3rd party services properly stubbed/commented and NOT integrated with real APIs?

3.3 Engineering Quality

[ ] Architecture Layering: Are database operations, business logic, and API definitions separated?

[ ] RBAC Enforcement: Is security non-negotiable and applied across all sensitive routes?

[ ] Test Execution: Does ./run_tests.sh execute unit and API tests with clear results?

3.6 Aesthetics (Frontend/Full-Stack)

[ ] Visual Specification: Is the layout neat, aligned, and using a modern framework (Tailwind, AntD, etc.)?

[ ] Interaction Experience: Do buttons show Loading/Disabled states? Is the flow smooth?
