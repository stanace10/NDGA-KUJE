# NDGA Workflow Review

Updated: 2026-03-11

This document describes the actual workflow implemented in the current NDGA codebase, not the planned workflow.

## 1. Startup and First-Time Setup Flow

1. `IT Manager` signs in.
2. If setup is not finalized, the user is pushed into the setup wizard.
3. The setup wizard runs in this order:
   - Session
   - Term
   - Calendar
   - Classes
   - Subjects
   - Class-Subject Mapping
   - Grade Scale
   - Finalize
4. When session is created, all three terms are scaffolded automatically.
5. When setup is finalized, the system state becomes `IT_READY` and the normal IT portal becomes the default landing page.

Important alignment note:
- The setup flow is automated and sequential.
- AI does not drive setup completion.
- AI is used later for lesson support, tutoring, and CBT draft/import flows.

## 2. Identity, Registration, and Assignment Flow

### IT Manager responsibilities
- Create and edit staff accounts.
- Create and edit student accounts.
- Reset credentials.
- Capture images through mobile capture flow.
- Maintain classes, subjects, class-subject mappings, subject-teacher assignments, and form-teacher assignments.

### Staff registration flow
1. IT creates the staff account.
2. IT selects the role path.
3. IT can assign:
   - subject teaching loads
   - form class assignment
   - dual-role cases such as `DEAN + SUBJECT_TEACHER`
4. Staff profile becomes visible in IT directory and staff portal.

### Student registration flow
1. IT creates the student account.
2. Student biodata/profile is saved.
3. Student is enrolled into class and subject context.
4. Student becomes visible in IT directory and student portal.

### Assignment ownership
- Subject teaching assignments are owned by IT in `academics/it/assignments/subject/`.
- Form-teacher assignments are owned by IT in `academics/it/assignments/form-teacher/`.
- One active form teacher per class/session is enforced by the form-teacher assignment flow.

## 3. Portal and Role Flow

### Student
- Student portal shows profile, attendance, subjects, transcript/report access, settings, and finance visibility.
- Student can access CBT and election portals only when those modules are enabled and the user is eligible.

### Subject Teacher
- Works only inside assigned class-subject windows.
- Can enter result scores for assigned subjects.
- Can build CBT drafts, manual questions, upload-import CBT, and AI-assisted drafts.
- Cannot publish final results.
- Cannot activate high-stakes CBT.

### Dean
- Reviews subject result sheets submitted by teachers.
- Approves or rejects teacher result sheets.
- Reviews CBT drafts and simulation wrappers before IT activation.

### Form Teacher
- Owns attendance for assigned class.
- Compiles class results after subject sheets are approved by Dean.
- Submits class compilation to VP.

### VP
- Oversees published academic context.
- Approves or rejects compiled class results.
- Can publish results after class compilation is submitted.

### Principal
- Oversight role with portal-wide visibility.
- Has privileged 2FA.
- Can publish or reject result compilations as override path where allowed.
- Can manage signature/settings for official report output.

### Bursar
- Finance dashboard, charges, payments, debtors, receipts, messaging, assets, salary, reminders.
- Has privileged 2FA.

### IT Manager
- Global operations owner.
- Has privileged 2FA.
- Can manage sync dashboard, user provisioning, academic structure, CBT activation, election management, feature toggles, and setup state.

## 4. Result Workflow

Result sheet status chain:
- `DRAFT`
- `SUBMITTED_TO_DEAN`
- `REJECTED_BY_DEAN`
- `APPROVED_BY_DEAN`
- `COMPILED_BY_FORM_TEACHER`
- `SUBMITTED_TO_VP`
- `REJECTED_BY_VP`
- `PUBLISHED`

Actual flow:
1. Subject teacher opens assigned class-subject sheet.
2. Teacher enters CA and exam components.
3. System calculates:
   - total CA
   - total exam
   - grand total
   - grade
4. Teacher submits sheet to Dean.
5. Dean approves or rejects.
6. Form teacher compiles the class after Dean approval is complete.
7. Compilation is submitted to VP.
8. VP publishes or rejects.
9. Principal can act as oversight/override according to policy.

What is automatic:
- score validation
- totals
- grade band resolution
- attendance percentage on class result records
- result share messaging links
- result PDF payload generation

What is not AI:
- score math
- ranking math
- highest/lowest/average calculations

What is AI-assisted:
- result comments and insight text

## 5. CBT Workflow

Exam status chain:
- `DRAFT`
- `PENDING_DEAN`
- `PENDING_IT`
- `APPROVED`
- `ACTIVE`
- `CLOSED`

### Standard graded CBT flow
1. Subject teacher creates exam against a real teaching assignment.
2. Teacher builds questions manually, by upload-import, or AI draft assistance.
3. Teacher submits draft to Dean.
4. Dean approves or rejects.
5. IT schedules and activates.
6. Students start attempts only when exam is active/open.
7. Objective marking is automatic.
8. Theory marking goes into teacher marking queue.
9. Writeback can feed locked score components into results.

### Free test flow
- `FREE_TEST` can move `Teacher -> IT` directly.
- This bypass is only for non-graded practice mode.

### Integrity and evidence
- Activation creates an immutable snapshot and activation hash.
- Attempts record integrity bundle data including start, submit, heartbeat, violations, unlocks, and finalization trail.
- Calculator/graph tooling is supported on runner pages for configured exams.
- Lockdown middleware tracks focus, visibility, copy/paste, fullscreen and related violations.

### Simulation flow
1. IT registers wrapper/tool.
2. Dean reviews wrapper.
3. Teacher attaches approved simulation to exam.
4. Score mode can be:
   - `AUTO`
   - `VERIFY`
   - `RUBRIC`
5. Simulation results can write back into exam/CA targets.

## 6. Election Workflow

Election status chain:
- `DRAFT`
- `OPEN`
- `CLOSED`
- `ARCHIVED`

Actual flow:
1. IT creates election.
2. IT creates positions.
3. IT adds candidates.
4. IT defines voter groups using:
   - all students
   - all staff
   - selected roles
   - selected classes
   - selected users
5. Eligible users enter election portal.
6. User votes once per position.
7. Vote uniqueness is enforced at DB level.
8. Vote audit stores IP, device, user-agent, and metadata.
9. Analytics and result PDF can be generated for oversight users.

## 7. Sync, Cloud, and LAN Flow

Implemented sync model:
- LAN and cloud use separate databases.
- LAN does not write directly into cloud Postgres.
- Cloud does not write directly into LAN Postgres.
- Sync happens through NDGA sync APIs and queue processing.

Outbound and inbound paths:
- Generic model changes listed in `apps/sync/model_sync.py` go to outbox automatically.
- Teacher-authored CBT content also goes through incremental content feed.
- LAN pulls remote CBT content and remote generic changes.
- LAN pushes exam attempts, vote events, and synced model records.
- Conflict policy blocks unsafe overwrites during high-stakes live sessions.

What this means operationally:
- Teachers can prepare CBT online.
- LAN node can pull those CBT changes.
- Students can sit the live CBT on LAN.
- Attempts and related score/writeback records can sync back to cloud.
- Election voting follows the same app-layer sync pattern.

## 8. Security and Control Layer

Implemented:
- privileged-role 2FA for `IT_MANAGER`, `BURSAR`, `VP`, `PRINCIPAL`
- scope-based permission layer beyond raw role checks
- portal guards and audience-aware login separation
- tamper-evident audit chain using previous-event hash + event hash
- sync management scope for sync dashboard and API operations
- immutable CBT activation snapshot and attempt integrity records

## 9. Live Verification Run (2026-03-11)

### Passed live
- Brevo email send: passed
  - actual provider send returned `201`
  - one live test email was sent to the configured NDGA sender mailbox
- AWS S3 media bucket: passed
  - bucket head/list check succeeded for `ndgakuje-media`
- OpenAI API key auth: passed
  - direct `GET /v1/models` returned `200`
- Cloud settings verification: passed locally
  - `manage.py verify_stage20`
  - `manage.py check`

### Failed live or still blocked
- Paystack live API check: failed
  - authenticated call to `/transaction/totals` returned `403` with `error code: 1010`
  - this is currently a live payment blocker until the key/account restriction is resolved
- Public sync endpoint: failed
  - `https://ndgakuje.org/sync/api/` returned `502`
  - current cloud node is not healthy/reachable right now
- Cloud database: not directly live-tested from this laptop
  - current cloud DB design is the Postgres container inside the AWS compose stack
  - it can only be tested properly after the new AWS node is up

### Repo issue found during audit
- The code was using OpenAI helpers without declaring `openai` in `requirements.txt`.
- This has been fixed in the repo.
- Before that fix, AI features fell back to deterministic output even with a valid key.

### Runtime note on OpenAI
- After installing the package, the direct key check passed.
- In-app AI helper calls still hit `429 Too Many Requests` during this audit window, so the app correctly fell back to deterministic output.
- This means the key is valid, but the account/model request budget or rate limit needs review.

## 10. Readiness Review

### Architecture rating
- `8.8/10`

### Live go-live rating today
- `7.9/10`

Why it is not fully green today:
1. Paystack did not pass a live authenticated check.
2. The public sync endpoint currently returns `502`.
3. The cloud DB path is architecturally correct, but the actual new AWS node has not been stood up and tested yet.
4. OpenAI auth is valid, but live generation hit `429` during this audit.
5. I did not run a true two-node sync drill or a 150-device LAN load test in this pass.

## 11. Bottom Line

The repo aligns well with the original governance-first goal.

What is already strong:
- setup wizard and academic structure ownership
- IT-owned registration and assignment control
- results workflow chain
- CBT governance chain
- election integrity chain
- sync architecture model
- role separation and privileged access hardening

What must be fixed or proven before calling it fully ready:
- restore a healthy public cloud deployment
- make Paystack pass a live authenticated check
- bring up the AWS node and verify container Postgres end-to-end
- run an actual LAN-to-cloud sync drill
- run a short real CBT dry run with school users before the live window
