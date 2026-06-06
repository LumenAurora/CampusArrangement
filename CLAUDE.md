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
  domain/         # Frozen dataclass entities & pure domain logic (no I/O)
    models.py     # User, Activity, TimeSlot, Registration, ScheduleResult, CheckIn + enums
    services.py   # schedule_registrations() — core allocation algorithm
    exceptions.py # DomainError hierarchy
  application/    # Business logic services (orchestration, validation)
    *_service.py  # ActivityService, RegistrationService, CheckInService, SchedulingService, UserService
    remote_services.py  # Remote API-backed service implementations
  infrastructure/ # Data access & external integrations
    db.py         # SQLite connection, transactions, init_db with migrations
    repositories.py       # Local SQLite repositories
    remote_repositories.py # Remote API repositories (with MetricsCache)
    api_client.py         # HTTP client for remote API (Bearer auth)
    auth.py               # pbkdf2_sha256 password hashing via passlib
    runtime_config.py     # QSettings for data mode (local/remote) and API URL
  ui/             # PySide6 Qt widgets
    main.py       # App entry point: wires services/repos, launches LoginDialog then AdminWindow or ClientWindow
    shell.py      # NavigationWindow — sidebar nav, page stack, theme/density toggling
    style.py      # QSS stylesheet builder + QSettings for theme/density/default-page
    theme.py      # Palette dataclasses (LIGHT/DARK) → QSS generator
    admin_window.py / client_window.py  # Role-based window shells with 5 tab panels each
    login_dialog.py / settings_dialog.py
    *_widgets.py  # Concrete QWidget pages and utility widgets
  resources/      # SQLite DB (app.db), SVG icons
```

### Key Concepts

- **Dual data mode**: Switched at login. `local` mode uses SQLite directly; `remote` mode connects to `app/api_server.py` (a FastAPI server) via REST. The `main()` function in `main.py` chooses between local and remote repository/service implementations based on `runtime_config.get_data_mode()`.
- **Role-based UI**: `Role.SUPER_ADMIN` / `Role.ORGANIZER` → `AdminWindow` (5 tabs: 概览, 活动管理, 排班管理, 签到管理, 用户管理). `Role.USER` → `ClientWindow` (5 tabs: 概览, 报名, 我的结果, 签到, 日程表).
- **Activity lifecycle**: `DRAFT → PENDING_REVIEW → OPEN → CLOSED → ARCHIVED`
- **Activity types**: `TIME_SLOT` (时段排班) and `NON_TIME_SLOT` (选题/选课/自定义), with slot subtypes (TIME_SLOT, TOPIC, COURSE, SEAT, CUSTOM_OPTION)
- **Signup modes**: `REALTIME` (先到先得, instant slot locking) vs `BLIND` (盲报, allocated later)
- **Allocation algorithms**: `GREEDY` (priority-then-time), `FIRST_COME` (creation-time), `LOTTERY` (random shuffle) — implemented in `domain/services.py`
- **Role permissions**: `SUPER_ADMIN` has full access; `ORGANIZER` can create/publish/manage activities but needs `SUPER_ADMIN` for user approval/role changes
- **DB migrations**: Schema evolves via `_ensure_column()` in `db.py` — columns are added with ALTER TABLE when missing. Old activity_type values are migrated via `_migrate_activity_type()`.

### Theme System

Palette dataclass holds all colors; `build_stylesheet(palette)` generates QSS. Light/dark themes and compact/comfortable density modes persist via QSettings. Widgets use standard QSS selectors and custom `get_palette()` for programmatic styling.

### Testing

Tests use `unittest` with temporary SQLite databases (path set via `CAMPUS_DB_PATH` env var in `setUp`). Run from repo root so `app` package is importable. Test files: `test_db.py` (repository/slot-locking), `test_domain.py` (domain logic), `test_scenarios.py` (end-to-end flows).
