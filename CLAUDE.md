# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Run the desktop app (PySide6)
python -m app.main

# Run the API server (FastAPI, default port 8000)
uvicorn app.api_server:app --reload

# Run all tests
python -m pytest tests/

# Run a single test
python -m pytest tests/test_scenarios.py::ScenarioTests::test_full_flow_blind_lottery

# Build executables (see scripts/)
scripts/build.bat          # full build
scripts/build_client.bat   # client only
scripts/build_server.bat   # server only

# Run without building
scripts/run.bat
```

**Important**: On Windows, `QT_PLUGIN_PATH` must point to PySide6's `Qt/plugins` directory (handled by `start.bat`/`start.sh`).

## Architecture

This is a **PySide6 desktop application** for campus activity registration, volunteer scheduling, and check-in. It has a dual-mode architecture supporting local-only (SQLite) and remote (FastAPI server) data backends.

### Layered Design (DDD-inspired)

```
app/
  config.py       # APP_NAME, DATA_DIR, DB_PATH (env-overridable via CAMPUS_DB_PATH)
  domain/         # Frozen dataclass entities & pure domain logic (no I/O)
    models.py     # User, Activity, TimeSlot, Registration, ScheduleResult, CheckIn, Group, GroupMember + enums
    services.py   # schedule_registrations() — core allocation algorithm
    templates.py  # ActivityTemplate, RecurrencePattern, JSON persistence (4 built-in templates)
    exceptions.py # DomainError hierarchy: PermissionDenied, CapacityExceeded, ValidationError, ConflictError
  application/    # Business logic services (orchestration, validation)
    *_service.py  # ActivityService, RegistrationService, CheckInService, SchedulingService, UserService, GroupService, TemplateService
    remote_services.py  # Remote API-backed service implementations
  infrastructure/ # Data access & external integrations
    db.py         # SQLite connection, init_db with migrations, _ensure_column, transaction()
    repositories.py       # Local SQLite repositories (8: User, Activity, TimeSlot, Registration, Schedule, CheckIn, Group)
    remote_repositories.py # Remote API repositories (with MetricsCache)
    api_client.py         # HTTP client for remote API (Bearer auth)
    auth.py               # pbkdf2_sha256 password hashing via passlib
    runtime_config.py     # QSettings for data mode (local/remote) and API URL
    exporter.py           # Excel export via pandas
    notifications.py      # SMTP email (sync + async via threading/Qt Signal), notification preferences
  ui/             # PySide6 Qt widgets
    main.py       # App entry point: wires services/repos, launches LoginDialog → AdminWindow or ClientWindow
    shell.py      # NavigationWindow — collapsible sidebar, page stack, theme/density/avatar menu, Ctrl+1-5 shortcuts
    style.py      # QSS stylesheet builder + QSettings for theme/density/default-page/form-layout
    theme.py      # Palette dataclasses (LIGHT/DARK) → QSS generator (~800 lines of QSS)
    admin_window.py / client_window.py  # Role-based window shells with tab panels
    login_dialog.py / settings_dialog.py / account_settings.py
    *_widgets.py  # Concrete QWidget pages and utility widgets
    activity_guided.py  # Wizard-driven activity creation (template-driven, 5-step flow)
    activity_workflow.py # Activity status workflow management widget
    icon_loader.py       # SVG icon loader from resources/
  resources/      # SQLite DB (app.db), SVG icons, uploads/avatars/
```

### Key Concepts

- **Dual data mode**: Switched at login. `local` mode uses SQLite directly; `remote` mode connects to `app/api_server.py` via REST. `main()` chooses between local/remote implementations based on `runtime_config.get_data_mode()`. In remote mode, group features are unavailable (`group_repo = None`).
- **Role-based UI**: `Role.SUPER_ADMIN` / `Role.ORGANIZER` → `AdminWindow` (tabs: 概览, 活动管理, 排班管理, 签到管理, 用户管理, 小组管理). `Role.USER` → `ClientWindow` (tabs: 概览, 报名, 我的结果, 签到, 小组, 日程表). The Group tab is conditionally appended only when `group_service` is available.
- **Activity lifecycle**: `DRAFT → PENDING_REVIEW → OPEN → CLOSED → ARCHIVED`. Organizers submit drafts for review; super admins (or other organizers as reviewers) publish. Only super admins can publish directly from DRAFT. Rejected activities return to DRAFT. Closed activities auto-trigger scheduling; if scheduling fails, the activity is reopened.
- **Activity types**: Two core modes: `TIME_SLOT` (时段排班, with time-based slots) and `NON_TIME_SLOT` (选题/选课/自定义, with non-time options). Old 5-type schema (`scheduling`, `topic_selection`, `course_selection`, `seat_reservation`, `custom`) was migrated to these two via `_migrate_activity_type()`.
- **Slot types**: `TIME_SLOT`, `TOPIC`, `COURSE`, `SEAT`, `CUSTOM_OPTION` — each slot has a `slot_type`. Non-time-slot activity types cannot have time-based slots. Slots support a parent-child hierarchy via `parent_slot_id` for positions/sub-roles within a time slot (e.g., "接待员", "引导员" under a parent time slot).
- **Signup modes**: `REALTIME` (先到先得, instant slot locking in a transaction with `lock_slot`) vs `BLIND` (盲报, allocated later via scheduling).
- **Allocation algorithms**: `GREEDY` (priority-then-time, default), `FIRST_COME` (by creation time), `LOTTERY` (random shuffle), `POINTS` (意愿点: users distribute 99 points across preferences; sorted by -points with random tiebreaking).
- **Role permissions**: `SUPER_ADMIN` has full access; `ORGANIZER` can create/publish/manage activities but needs `SUPER_ADMIN` for user approval/role changes. Organizers cannot review their own activities (must go through another organizer or super admin).
- **User self-registration**: Users self-register with `PENDING_REVIEW` status; only super admins can approve/reject. Rejected users' tokens are invalidated.
- **DB migrations**: Schema evolves via `_ensure_column()` in `db.py` — columns are added with ALTER TABLE when missing. Complex migrations (nullable constraints, unique index changes, activity type values) use dedicated `_migrate_*()` functions. The `registrations` unique index was migrated from `(user_id, activity_id)` to `(user_id, slot_id)` to support multi-slot registration.
- **allow_multiple_slots**: When enabled on an activity, users can register for multiple slots within the same activity (兼报). The scheduling algorithm skips user deduplication in this mode and also skips the second-round reallocation.

### Scheduling Algorithm (`domain/services.py`)

The `schedule_registrations()` function implements a two-round allocation:

1. **First round**: Registrations are sorted by mode (priority ascending, creation time, random, or points descending), then each user is assigned to their chosen slot if capacity remains. In multi-slot mode, deduplication is per `(user_id, slot_id)`; in single-slot mode, once a user is assigned they are excluded from further rounds.
2. **Second round (reallocation)**: Only in single-slot mode. Unassigned users are offered any remaining capacity in other slots of the same activity, preferring their original slot first. This handles overflow/load balancing.

Returns `list[(registration_id, ScheduleResult)]` so callers can correctly mark registrations as ASSIGNED/NOT_ASSIGNED even when a user is reallocated to a different slot than they registered for.

### Group System

Groups restrict activity registration to members only. Key rules:
- Only SUPER_ADMIN/ORGANIZER can create groups; the creator becomes the group admin.
- Users apply to join (with optional reason); group admin or super admin approves/rejects.
- Group creator cannot be removed; deleting a group clears `group_id` on referencing activities.
- `GroupService.can_access_activity()` / `list_accessible_activities()` filter activities by group membership.

### Activity Templates (`domain/templates.py`)

Templates save activity configuration (without specific dates) for reuse. Four built-in templates cover common scenarios (weekly volunteering, monthly duty, semester course selection, one-time events). Templates support recurrence patterns: `ONCE`, `WEEKLY`, `MONTHLY`, `SEMESTER`. `generate_recurring_activities()` in `template_service.py` batch-creates activities from a template with computed time windows.

### Check-in System

Five check-in modes: `MANUAL` (admin marks attendance), `QRCODE` (admin displays code, users scan), `SELF_CODE` (users enter code), `LOCATION` (GPS coordinate validation), `PHOTO` (photo upload). Key behaviors:
- `NON_TIME_SLOT` activities cannot use `LOCATION` check-in.
- Location check-in requires coordinate-format location (`lat,lng`) validated to ±90/±180 ranges.
- Admin can close check-in early (`checkin_closed` flag, reversible) or mark users absent.
- `CheckInRepository` enforces `UNIQUE(user_id, slot_id)` — one check-in per user per slot.

### Notification System (`infrastructure/notifications.py`)

Users configure notification preference: `IN_APP` (console/system tray), `EMAIL` (SMTP), or `NONE`. SMTP settings persist via QSettings. `send_email_async()` uses a background thread with Qt Signals for thread-safe UI callbacks. `notify_by_preference()` routes notifications based on user preference.

### Theme System

`Palette` dataclass (42 color tokens) holds all colors; `build_stylesheet(palette)` generates ~800 lines of QSS. Light/dark themes and compact/comfortable density modes persist via QSettings. Widgets use standard QSS selectors and custom `get_palette()` for programmatic styling. The `NavigationWindow` top-bar includes an avatar button with a dropdown menu for theme/density switching, account settings, and logout.

### API Server (`api_server.py`)

FastAPI server with CORS enabled, in-memory Bearer token authentication (24h TTL), and comprehensive REST endpoints mirroring all application services. Key patterns:
- `_get_current_user()` dependency validates tokens and checks user approval status.
- `_handle_domain_error()` maps domain exceptions to HTTP status codes (400/403/409).
- Self-registration, avatar upload (2MB limit, allowed extensions), and notification preferences are REST endpoints.
- Activity close triggers auto-scheduling; rollback to OPEN on failure.
- `checkin_closed` / `reopen` endpoints for early check-in control.

### Testing

Tests use `unittest` with temporary SQLite databases (path set via `CAMPUS_DB_PATH` env var in `setUp`). Run from repo root so `app` package is importable. Test files: `test_db.py` (repository/slot-locking), `test_domain.py` (domain logic), `test_scenarios.py` (end-to-end flows), `test_batch2_features.py`, `test_time_diagnosis.py`, `test_pyautogui_e2e.py`.
