from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import sqlite3

from goalmate.auth import (
    SESSION_COOKIE_NAME,
    build_session_cookie,
    generate_session_token,
    hash_password,
    hash_session_token,
    session_expiry_iso,
    verify_password,
)
from goalmate.config import load_config
from goalmate.context import RequestContext, get_request_context
from goalmate.db import (
    build_database_settings,
    connect_database,
    ensure_sqlite_data_dir,
    reset_database,
    sync_identity_sequences,
)


ROOT_DIR = Path(__file__).resolve().parent
CONFIG = load_config(ROOT_DIR)
STATIC_DIR = CONFIG.static_dir
DATA_DIR = CONFIG.data_dir
DB_SETTINGS = build_database_settings(CONFIG)
DB_PATH = DB_SETTINGS.sqlite_path if DB_SETTINGS.sqlite_path is not None else CONFIG.db_path

DEMO_AUTH_USERS = [
    {
        "id": 1,
        "email": "demo@goalmate.local",
        "password": "goalmate-demo",
        "full_name": "GoalMate Demo Admin",
        "user_type": "mixed",
        "role": "mixed",
        "is_default": 1,
    },
    {
        "id": 2,
        "email": "participant@goalmate.local",
        "password": "goalmate-participant",
        "full_name": "GoalMate Demo Participant",
        "user_type": "participant",
        "role": "participant",
        "is_default": 0,
    },
    {
        "id": 3,
        "email": "organizer@goalmate.local",
        "password": "goalmate-organizer",
        "full_name": "GoalMate Demo Organizer",
        "user_type": "organizer",
        "role": "organizer",
        "is_default": 0,
    },
]

ROLE_CAPABILITIES = {
    "mixed": {"participant", "organizer"},
    "participant": {"participant"},
    "organizer": {"organizer"},
    "demo": {"participant", "organizer"},
}

ORGANIZER_MEMBERSHIP_ROLES = {"owner", "admin", "curator"}
PROGRAM_ORGANIZER_MEMBERSHIP_ROLES = {"organizer", "curator"}
PROGRAM_PARTICIPANT_MEMBERSHIP_ROLES = {"participant"}


class AuthorizationError(Exception):
    """Raised when the current context is not allowed to perform an action."""


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS organizers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    brand_name TEXT NOT NULL,
    primary_color TEXT NOT NULL,
    accent_color TEXT NOT NULL,
    support_email TEXT NOT NULL,
    tagline TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS programs (
    id INTEGER PRIMARY KEY,
    organizer_id INTEGER NOT NULL,
    source_program_id INTEGER,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    audience TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (organizer_id) REFERENCES organizers(id),
    FOREIGN KEY (source_program_id) REFERENCES programs(id)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    user_type TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL,
    bio TEXT NOT NULL,
    avatar_bg TEXT NOT NULL,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_active_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_contexts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    organizer_id INTEGER NOT NULL,
    program_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (organizer_id) REFERENCES organizers(id) ON DELETE CASCADE,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    UNIQUE (user_id, organizer_id, program_id, participant_id, role)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    user_context_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    user_agent TEXT,
    ip_address TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (user_context_id) REFERENCES user_contexts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_scopes (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL UNIQUE,
    organizer_id INTEGER NOT NULL,
    program_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (organizer_id) REFERENCES organizers(id) ON DELETE CASCADE,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS organization_memberships (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    organizer_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (organizer_id) REFERENCES organizers(id) ON DELETE CASCADE,
    UNIQUE (user_id, organizer_id, role)
);

CREATE TABLE IF NOT EXISTS modules (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    week_label TEXT NOT NULL,
    position INTEGER NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    module_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    task_type TEXT NOT NULL,
    submission_mode TEXT NOT NULL,
    points INTEGER NOT NULL,
    estimated_minutes INTEGER NOT NULL,
    scheduled_for TEXT NOT NULL,
    position INTEGER NOT NULL,
    soft_return_copy TEXT NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS program_memberships (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    program_id INTEGER NOT NULL,
    participant_id INTEGER,
    role TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE SET NULL,
    UNIQUE (user_id, program_id, participant_id, role)
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'participant',
    progress_percent REAL NOT NULL DEFAULT 0,
    xp INTEGER NOT NULL DEFAULT 0,
    completed_tasks INTEGER NOT NULL DEFAULT 0,
    total_tasks INTEGER NOT NULL DEFAULT 0,
    soft_return_count INTEGER NOT NULL DEFAULT 0,
    at_risk INTEGER NOT NULL DEFAULT 0,
    joined_at TEXT NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    UNIQUE (program_id, participant_id)
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    goal_text TEXT NOT NULL,
    progress_percent REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    is_captain INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    UNIQUE (team_id, participant_id)
);

CREATE TABLE IF NOT EXISTS participant_tasks (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    progress_percent REAL NOT NULL DEFAULT 0,
    report_required INTEGER NOT NULL DEFAULT 0,
    soft_return_available INTEGER NOT NULL DEFAULT 0,
    planned_for TEXT NOT NULL,
    completed_at TEXT,
    last_interaction_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    UNIQUE (task_id, participant_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    participant_task_id INTEGER NOT NULL UNIQUE,
    participant_id INTEGER NOT NULL,
    task_id INTEGER NOT NULL,
    report_type TEXT NOT NULL,
    content TEXT NOT NULL,
    attachment_name TEXT,
    status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    FOREIGN KEY (participant_task_id) REFERENCES participant_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    participant_id INTEGER NOT NULL,
    program_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    notification_type TEXT NOT NULL,
    trigger_reason TEXT NOT NULL,
    cta_label TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    metric_date TEXT NOT NULL,
    active_participants INTEGER NOT NULL,
    reports_submitted INTEGER NOT NULL,
    missed_tasks INTEGER NOT NULL,
    completion_rate REAL NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS private_challenges (
    id INTEGER PRIMARY KEY,
    creator_participant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    goal_text TEXT NOT NULL,
    target_per_week INTEGER NOT NULL,
    target_team_size INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    visibility TEXT NOT NULL,
    FOREIGN KEY (creator_participant_id) REFERENCES participants(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS private_challenge_members (
    id INTEGER PRIMARY KEY,
    challenge_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    FOREIGN KEY (challenge_id) REFERENCES private_challenges(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
    UNIQUE (challenge_id, participant_id)
);
"""


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def current_request_context(handler: BaseHTTPRequestHandler | None = None) -> RequestContext:
    session_context = resolve_session_context(handler)
    if session_context is not None:
        return session_context
    return get_request_context(CONFIG, handler)


def connect_db() -> sqlite3.Connection:
    return connect_database(DB_SETTINGS)


def parse_cookies(handler: BaseHTTPRequestHandler | None) -> dict[str, str]:
    if handler is None:
        return {}

    raw_cookie = handler.headers.get("Cookie", "")
    if not raw_cookie:
        return {}

    cookie = SimpleCookie()
    cookie.load(raw_cookie)
    return {key: morsel.value for key, morsel in cookie.items()}


def ordered_available_roles(roles: set[str] | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    unique_roles = {role for role in roles if role in {"participant", "organizer"}}
    return tuple(candidate for candidate in ("participant", "organizer") if candidate in unique_roles)


def primary_role_from_available_roles(available_roles: tuple[str, ...] | list[str]) -> str:
    normalized = ordered_available_roles(tuple(available_roles))
    if len(normalized) == 2:
        return "mixed"
    if normalized:
        return normalized[0]
    return "demo"


def list_user_memberships(conn: sqlite3.Connection, user_id: int) -> dict[str, list[dict]]:
    organization_rows = conn.execute(
        """
        SELECT
            om.id,
            om.organizer_id,
            om.role,
            om.is_default,
            om.created_at,
            o.name AS organizer_name,
            o.brand_name
        FROM organization_memberships om
        JOIN organizers o ON o.id = om.organizer_id
        WHERE om.user_id = ?
        ORDER BY om.is_default DESC, om.id ASC
        """,
        (user_id,),
    ).fetchall()
    program_rows = conn.execute(
        """
        SELECT
            pm.id,
            p.organizer_id,
            pm.program_id,
            pm.participant_id,
            pm.role,
            pm.is_default,
            pm.created_at,
            p.name AS program_name,
            p.status AS program_status,
            pt.full_name AS participant_name
        FROM program_memberships pm
        JOIN programs p ON p.id = pm.program_id
        LEFT JOIN participants pt ON pt.id = pm.participant_id
        WHERE pm.user_id = ?
        ORDER BY pm.is_default DESC, pm.id ASC
        """,
        (user_id,),
    ).fetchall()
    return {
        "organizations": [{key: row[key] for key in row.keys()} for row in organization_rows],
        "programs": [{key: row[key] for key in row.keys()} for row in program_rows],
    }


def default_program_row_for_organizer(conn: sqlite3.Connection, organizer_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, organizer_id, status
        FROM programs
        WHERE organizer_id = ?
        ORDER BY
            CASE status
                WHEN 'active' THEN 1
                WHEN 'draft' THEN 2
                WHEN 'archived' THEN 3
                ELSE 4
            END,
            id ASC
        LIMIT 1
        """,
        (organizer_id,),
    ).fetchone()


def default_preview_participant_id(conn: sqlite3.Connection, program_id: int) -> int | None:
    preferred = conn.execute(
        """
        SELECT participant_id
        FROM enrollments
        WHERE program_id = ? AND participant_id = ?
        """,
        (program_id, CONFIG.dev_participant_id),
    ).fetchone()
    if preferred is not None:
        return int(preferred["participant_id"])

    row = conn.execute(
        """
        SELECT participant_id
        FROM enrollments
        WHERE program_id = ?
        ORDER BY participant_id ASC
        LIMIT 1
        """,
        (program_id,),
    ).fetchone()
    if row is None:
        return None
    return int(row["participant_id"])


def available_roles_from_memberships(
    memberships: dict[str, list[dict]],
    organizer_id: int,
    program_id: int,
    participant_id: int,
) -> tuple[str, ...]:
    available_roles: set[str] = set()
    organization_memberships = memberships.get("organizations", [])
    program_memberships = memberships.get("programs", [])

    if any(
        membership["organizer_id"] == organizer_id and membership["role"] in ORGANIZER_MEMBERSHIP_ROLES
        for membership in organization_memberships
    ):
        available_roles.add("organizer")

    if any(
        membership["program_id"] == program_id and membership["role"] in PROGRAM_ORGANIZER_MEMBERSHIP_ROLES
        for membership in program_memberships
    ):
        available_roles.add("organizer")

    if any(
        membership["program_id"] == program_id
        and membership["role"] in PROGRAM_PARTICIPANT_MEMBERSHIP_ROLES
        and membership["participant_id"] == participant_id
        for membership in program_memberships
    ):
        available_roles.add("participant")

    return ordered_available_roles(available_roles)


def default_scope_from_memberships(
    conn: sqlite3.Connection,
    user_id: int,
    memberships: dict[str, list[dict]] | None = None,
) -> dict | None:
    memberships = memberships or list_user_memberships(conn, user_id)
    program_memberships = memberships.get("programs", [])
    organization_memberships = memberships.get("organizations", [])

    scoped_program_memberships = [
        membership
        for membership in program_memberships
        if membership["role"] in PROGRAM_PARTICIPANT_MEMBERSHIP_ROLES | PROGRAM_ORGANIZER_MEMBERSHIP_ROLES
    ]
    selected_program_membership = scoped_program_memberships[0] if scoped_program_memberships else None

    if selected_program_membership is not None:
        organizer_id = int(selected_program_membership["organizer_id"])
        program_id = int(selected_program_membership["program_id"])
        participant_id = selected_program_membership["participant_id"]
    else:
        selected_organization_membership = organization_memberships[0] if organization_memberships else None
        if selected_organization_membership is None:
            return None
        organizer_id = int(selected_organization_membership["organizer_id"])
        program_row = default_program_row_for_organizer(conn, organizer_id)
        if program_row is None:
            return None
        program_id = int(program_row["id"])
        participant_id = None

    if participant_id is None:
        participant_membership = next(
            (
                membership
                for membership in program_memberships
                if membership["program_id"] == program_id
                and membership["role"] in PROGRAM_PARTICIPANT_MEMBERSHIP_ROLES
                and membership["participant_id"] is not None
            ),
            None,
        )
        participant_id = participant_membership["participant_id"] if participant_membership is not None else None

    if participant_id is None:
        participant_id = default_preview_participant_id(conn, program_id)

    if participant_id is None:
        return None

    available_roles = available_roles_from_memberships(
        memberships,
        organizer_id,
        program_id,
        int(participant_id),
    )
    if not available_roles:
        return None

    return {
        "organizer_id": organizer_id,
        "program_id": program_id,
        "participant_id": int(participant_id),
        "available_roles": available_roles,
        "primary_role": primary_role_from_available_roles(available_roles),
    }


def scope_options_from_memberships(
    conn: sqlite3.Connection,
    user_id: int,
    memberships: dict[str, list[dict]] | None = None,
    current_scope: tuple[int, int, int] | None = None,
) -> list[dict]:
    memberships = memberships or list_user_memberships(conn, user_id)
    options: list[dict] = []
    seen_programs: set[int] = set()

    for membership in memberships.get("programs", []):
        program_id = int(membership["program_id"])
        if program_id in seen_programs:
            continue

        participant_membership = next(
            (
                item
                for item in memberships.get("programs", [])
                if item["program_id"] == program_id
                and item["role"] in PROGRAM_PARTICIPANT_MEMBERSHIP_ROLES
                and item["participant_id"] is not None
            ),
            None,
        )
        participant_id = (
            int(participant_membership["participant_id"])
            if participant_membership is not None
            else default_preview_participant_id(conn, program_id)
        )
        if participant_id is None:
            continue

        organizer_id = int(membership["organizer_id"])
        available_roles = available_roles_from_memberships(
            memberships,
            organizer_id,
            program_id,
            participant_id,
        )
        if not available_roles:
            continue

        option_scope = (organizer_id, program_id, participant_id)
        options.append(
            {
                "organizerId": organizer_id,
                "programId": program_id,
                "participantId": participant_id,
                "programName": membership["program_name"],
                "programStatus": membership["program_status"],
                "participantName": participant_membership["participant_name"] if participant_membership is not None else None,
                "availableRoles": list(available_roles),
                "primaryRole": primary_role_from_available_roles(available_roles),
                "isCurrent": option_scope == current_scope if current_scope is not None else False,
            }
        )
        seen_programs.add(program_id)

    if not options:
        fallback_scope = default_scope_from_memberships(conn, user_id, memberships)
        if fallback_scope is not None:
            options.append(
                {
                    "organizerId": fallback_scope["organizer_id"],
                    "programId": fallback_scope["program_id"],
                    "participantId": fallback_scope["participant_id"],
                    "programName": f"Program #{fallback_scope['program_id']}",
                    "programStatus": "active",
                    "participantName": None,
                    "availableRoles": list(fallback_scope["available_roles"]),
                    "primaryRole": fallback_scope["primary_role"],
                    "isCurrent": True,
                }
            )

    return options


def scope_membership_state(
    memberships: dict[str, list[dict]],
    organizer_id: int,
    program_id: int,
    participant_id: int,
    available_scopes: list[dict] | None = None,
) -> dict:
    current_organization_memberships = [
        membership
        for membership in memberships.get("organizations", [])
        if membership["organizer_id"] == organizer_id
    ]
    current_program_memberships = [
        membership
        for membership in memberships.get("programs", [])
        if membership["program_id"] == program_id and (membership["participant_id"] in {participant_id, None})
    ]
    return {
        "organizations": memberships.get("organizations", []),
        "programs": memberships.get("programs", []),
        "currentScope": {
            "organizerId": organizer_id,
            "programId": program_id,
            "participantId": participant_id,
            "organizerMemberships": current_organization_memberships,
            "programMemberships": current_program_memberships,
            "availableRoles": list(
                available_roles_from_memberships(
                    memberships,
                    organizer_id,
                    program_id,
                    participant_id,
                )
            ),
        },
        "availableScopes": available_scopes or [],
    }


def legacy_scope_from_context_row(legacy_context_row: sqlite3.Row | None) -> dict | None:
    if legacy_context_row is None:
        return None

    organizer_id = legacy_context_row["legacy_organizer_id"] if "legacy_organizer_id" in legacy_context_row.keys() else legacy_context_row["organizer_id"]
    program_id = legacy_context_row["legacy_program_id"] if "legacy_program_id" in legacy_context_row.keys() else legacy_context_row["program_id"]
    participant_id = legacy_context_row["legacy_participant_id"] if "legacy_participant_id" in legacy_context_row.keys() else legacy_context_row["participant_id"]
    role = legacy_context_row["legacy_role"] if "legacy_role" in legacy_context_row.keys() else legacy_context_row["role"]

    available_roles = ordered_available_roles(ROLE_CAPABILITIES.get(role, set()))
    return {
        "organizer_id": int(organizer_id),
        "program_id": int(program_id),
        "participant_id": int(participant_id),
        "available_roles": available_roles,
        "primary_role": role if role else primary_role_from_available_roles(available_roles),
    }


def session_scope_row(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM session_scopes
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()


def upsert_session_scope(
    conn: sqlite3.Connection,
    session_id: int,
    organizer_id: int,
    program_id: int,
    participant_id: int,
) -> sqlite3.Row:
    timestamp = now_iso()
    existing = session_scope_row(conn, session_id)
    if existing is None:
        conn.execute(
            """
            INSERT INTO session_scopes (
                session_id, organizer_id, program_id, participant_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, organizer_id, program_id, participant_id, timestamp, timestamp),
        )
    else:
        conn.execute(
            """
            UPDATE session_scopes
            SET organizer_id = ?, program_id = ?, participant_id = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (organizer_id, program_id, participant_id, timestamp, session_id),
        )
    return session_scope_row(conn, session_id)


def ensure_session_scope(
    conn: sqlite3.Connection,
    session_id: int,
    user_id: int,
    legacy_context_row: sqlite3.Row | None = None,
) -> tuple[sqlite3.Row | None, tuple[str, ...], str]:
    existing_scope = session_scope_row(conn, session_id)
    memberships = list_user_memberships(conn, user_id)

    if existing_scope is not None:
        available_roles = available_roles_from_memberships(
            memberships,
            existing_scope["organizer_id"],
            existing_scope["program_id"],
            existing_scope["participant_id"],
        )
        if available_roles:
            return existing_scope, available_roles, primary_role_from_available_roles(available_roles)

    derived_scope = default_scope_from_memberships(conn, user_id, memberships)
    if derived_scope is None:
        derived_scope = legacy_scope_from_context_row(legacy_context_row)
    if derived_scope is None:
        return None, tuple(), "demo"

    persisted_scope = upsert_session_scope(
        conn,
        session_id,
        derived_scope["organizer_id"],
        derived_scope["program_id"],
        derived_scope["participant_id"],
    )
    available_roles = available_roles_from_memberships(
        memberships,
        derived_scope["organizer_id"],
        derived_scope["program_id"],
        derived_scope["participant_id"],
    )
    if not available_roles:
        available_roles = tuple(derived_scope["available_roles"])
    primary_role = primary_role_from_available_roles(available_roles) if available_roles else derived_scope["primary_role"]
    return persisted_scope, available_roles, primary_role


def available_roles_for_context(context: RequestContext | None) -> list[str]:
    if context is None:
        return ["participant", "organizer"]

    if context.available_roles:
        ordered = ordered_available_roles(context.available_roles)
        if ordered:
            return list(ordered)

    role = context.role
    capabilities = ROLE_CAPABILITIES.get(role, set())
    ordered = ordered_available_roles(capabilities)
    return list(ordered or ("participant",))


def require_capability(context: RequestContext, capability: str) -> None:
    capabilities = set(available_roles_for_context(context))
    if capability not in capabilities:
        raise AuthorizationError(f"Роль '{context.role}' не может выполнять действие типа '{capability}'")


def resolve_session_context(handler: BaseHTTPRequestHandler | None) -> RequestContext | None:
    cookies = parse_cookies(handler)
    session_token = cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None

    session_token_hash = hash_session_token(session_token, CONFIG.session_secret)
    with connect_db() as conn:
        session_row = conn.execute(
            """
            SELECT
                s.id AS session_id,
                s.user_id,
                s.user_context_id,
                s.expires_at,
                uc.organizer_id AS legacy_organizer_id,
                uc.program_id AS legacy_program_id,
                uc.participant_id AS legacy_participant_id,
                uc.role AS legacy_role,
                u.email,
                u.full_name
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN user_contexts uc ON uc.id = s.user_context_id
            WHERE s.token_hash = ?
              AND s.expires_at > ?
              AND u.is_active = 1
            """,
            (session_token_hash, now_iso()),
        ).fetchone()
        if session_row is None:
            return None

        scope_row, available_roles, primary_role = ensure_session_scope(
            conn,
            session_row["session_id"],
            session_row["user_id"],
            session_row,
        )
        if scope_row is None:
            return None

        conn.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
            (now_iso(), session_row["session_id"]),
        )
        conn.commit()

    return RequestContext(
        organizer_id=scope_row["organizer_id"],
        program_id=scope_row["program_id"],
        participant_id=scope_row["participant_id"],
        source="session",
        user_id=session_row["user_id"],
        session_id=session_row["session_id"],
        session_expires_at=session_row["expires_at"],
        role=primary_role,
        available_roles=available_roles,
        is_authenticated=True,
    )


def default_user_context_row(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM user_contexts
        WHERE user_id = ?
        ORDER BY is_default DESC, id ASC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def ensure_legacy_user_context(
    conn: sqlite3.Connection,
    user_id: int,
    scope: dict,
) -> sqlite3.Row:
    existing = conn.execute(
        """
        SELECT *
        FROM user_contexts
        WHERE user_id = ? AND organizer_id = ? AND program_id = ? AND participant_id = ? AND role = ?
        LIMIT 1
        """,
        (
            user_id,
            scope["organizer_id"],
            scope["program_id"],
            scope["participant_id"],
            scope["primary_role"],
        ),
    ).fetchone()
    if existing is not None:
        return existing

    conn.execute(
        """
        INSERT INTO user_contexts (
            user_id, organizer_id, program_id, participant_id, role, is_default
        ) VALUES (?, ?, ?, ?, ?, 1)
        """,
        (
            user_id,
            scope["organizer_id"],
            scope["program_id"],
            scope["participant_id"],
            scope["primary_role"],
        ),
    )
    return default_user_context_row(conn, user_id)


def get_me_state(context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    available_roles = available_roles_for_context(context)
    membership_state = {
        "organizations": [],
        "programs": [],
        "currentScope": {
            "organizerId": context.organizer_id,
            "programId": context.program_id,
            "participantId": context.participant_id,
            "organizerMemberships": [],
            "programMemberships": [],
            "availableRoles": available_roles,
        },
        "availableScopes": [],
    }
    me_state = {
        "authenticated": context.is_authenticated,
        "source": context.source,
        "role": context.role,
        "availableRoles": available_roles,
        "primaryRole": available_roles[0] if available_roles else "participant",
        "user": None,
        "session": {
            "id": context.session_id,
            "expiresAt": context.session_expires_at,
        }
        if context.is_authenticated
        else None,
        "demoCredentials": [
            {
                "email": demo_user["email"],
                "password": demo_user["password"],
                "role": demo_user["role"],
            }
            for demo_user in DEMO_AUTH_USERS
        ]
        if CONFIG.is_development
        else [],
        "memberships": membership_state,
    }

    if context.user_id is not None:
        with connect_db() as conn:
            user = conn.execute(
                "SELECT id, email, full_name, user_type, last_login_at FROM users WHERE id = ?",
                (context.user_id,),
            ).fetchone()
            memberships = list_user_memberships(conn, context.user_id)
            available_scopes = scope_options_from_memberships(
                conn,
                context.user_id,
                memberships,
                (context.organizer_id, context.program_id, context.participant_id),
            )
        if user is not None:
            me_state["user"] = {
                "id": user["id"],
                "email": user["email"],
                "fullName": user["full_name"],
                "userType": user["user_type"],
                "lastLoginAt": user["last_login_at"],
            }
            me_state["memberships"] = scope_membership_state(
                memberships,
                context.organizer_id,
                context.program_id,
                context.participant_id,
                available_scopes=available_scopes,
            )

    return me_state


def login_user(payload: dict, handler: BaseHTTPRequestHandler | None = None) -> tuple[dict, str]:
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", "")).strip()
    if not email or not password:
        raise ValueError("Нужны email и пароль")

    user_agent = handler.headers.get("User-Agent", "") if handler is not None else ""
    ip_address = handler.client_address[0] if handler is not None and handler.client_address else ""

    with connect_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE lower(email) = ? AND is_active = 1",
            (email,),
        ).fetchone()
        if user is None or not verify_password(password, user["password_hash"]):
            raise ValueError("Неверный email или пароль")

        memberships = list_user_memberships(conn, user["id"])
        scope = default_scope_from_memberships(conn, user["id"], memberships)
        if scope is None:
            raise ValueError("Для этого пользователя не найден доступ к GoalMate")
        user_context = ensure_legacy_user_context(conn, user["id"], scope)

        token = generate_session_token()
        token_hash = hash_session_token(token, CONFIG.session_secret)
        expires_at = session_expiry_iso()
        session_cursor = conn.execute(
            """
            INSERT INTO sessions (
                user_id, user_context_id, token_hash, created_at, expires_at, last_seen_at, user_agent, ip_address
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                user_context["id"],
                token_hash,
                now_iso(),
                expires_at,
                now_iso(),
                user_agent,
                ip_address,
            ),
        )
        upsert_session_scope(
            conn,
            session_cursor.lastrowid,
            scope["organizer_id"],
            scope["program_id"],
            scope["participant_id"],
        )
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (now_iso(), user["id"]),
        )
        conn.commit()

    if handler is not None:
        context = resolve_session_context_from_token(token)
    else:
        context = current_request_context()

    return {"me": get_me_state(context), "bootstrap": get_bootstrap_state(context)}, build_session_cookie(token)


def resolve_session_context_from_token(session_token: str) -> RequestContext | None:
    session_token_hash = hash_session_token(session_token, CONFIG.session_secret)
    with connect_db() as conn:
        session_row = conn.execute(
            """
            SELECT
                s.id AS session_id,
                s.user_id,
                s.user_context_id,
                s.expires_at,
                uc.organizer_id AS legacy_organizer_id,
                uc.program_id AS legacy_program_id,
                uc.participant_id AS legacy_participant_id,
                uc.role AS legacy_role
            FROM sessions s
            LEFT JOIN user_contexts uc ON uc.id = s.user_context_id
            WHERE s.token_hash = ?
              AND s.expires_at > ?
            """,
            (session_token_hash, now_iso()),
        ).fetchone()
        if session_row is None:
            return None
        scope_row, available_roles, primary_role = ensure_session_scope(
            conn,
            session_row["session_id"],
            session_row["user_id"],
            session_row,
        )
        if scope_row is None:
            return None
        conn.commit()
    return RequestContext(
        organizer_id=scope_row["organizer_id"],
        program_id=scope_row["program_id"],
        participant_id=scope_row["participant_id"],
        source="session",
        user_id=session_row["user_id"],
        session_id=session_row["session_id"],
        session_expires_at=session_row["expires_at"],
        role=primary_role,
        available_roles=available_roles,
        is_authenticated=True,
    )


def logout_user(context: RequestContext | None = None) -> tuple[dict, str]:
    context = context or current_request_context()
    if context.session_id is not None:
        with connect_db() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (context.session_id,))
            conn.commit()

    fallback_context = get_request_context(CONFIG)
    return {"me": get_me_state(fallback_context), "bootstrap": get_bootstrap_state(fallback_context)}, build_session_cookie("", clear=True)


def resolve_session_context_from_session_id(session_id: int) -> RequestContext | None:
    with connect_db() as conn:
        session_row = conn.execute(
            """
            SELECT
                s.id AS session_id,
                s.user_id,
                s.user_context_id,
                s.expires_at,
                uc.organizer_id AS legacy_organizer_id,
                uc.program_id AS legacy_program_id,
                uc.participant_id AS legacy_participant_id,
                uc.role AS legacy_role
            FROM sessions s
            LEFT JOIN user_contexts uc ON uc.id = s.user_context_id
            WHERE s.id = ?
              AND s.expires_at > ?
            """,
            (session_id, now_iso()),
        ).fetchone()
        if session_row is None:
            return None
        scope_row, available_roles, primary_role = ensure_session_scope(
            conn,
            session_row["session_id"],
            session_row["user_id"],
            session_row,
        )
        if scope_row is None:
            return None
        conn.commit()
    return RequestContext(
        organizer_id=scope_row["organizer_id"],
        program_id=scope_row["program_id"],
        participant_id=scope_row["participant_id"],
        source="session",
        user_id=session_row["user_id"],
        session_id=session_row["session_id"],
        session_expires_at=session_row["expires_at"],
        role=primary_role,
        available_roles=available_roles,
        is_authenticated=True,
    )


def switch_session_scope(payload: dict, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    if not context.is_authenticated or context.session_id is None or context.user_id is None:
        raise AuthorizationError("Нужно войти в GoalMate, чтобы менять активный scope")

    program_id = int(payload.get("programId", 0))
    if not program_id:
        raise ValueError("Нужен programId")

    with connect_db() as conn:
        memberships = list_user_memberships(conn, context.user_id)
        available_scopes = scope_options_from_memberships(conn, context.user_id, memberships)
        selected_scope = next((scope for scope in available_scopes if scope["programId"] == program_id), None)
        if selected_scope is None:
            raise AuthorizationError("Нет доступа к выбранной программе")

        upsert_session_scope(
            conn,
            context.session_id,
            selected_scope["organizerId"],
            selected_scope["programId"],
            selected_scope["participantId"],
        )
        legacy_context = ensure_legacy_user_context(
            conn,
            context.user_id,
            {
                "organizer_id": selected_scope["organizerId"],
                "program_id": selected_scope["programId"],
                "participant_id": selected_scope["participantId"],
                "primary_role": selected_scope["primaryRole"],
            },
        )
        conn.execute(
            "UPDATE sessions SET user_context_id = ?, last_seen_at = ? WHERE id = ?",
            (legacy_context["id"], now_iso(), context.session_id),
        )
        conn.commit()

    resolved_context = resolve_session_context_from_session_id(context.session_id)
    if resolved_context is None:
        raise ValueError("Не удалось обновить активный scope")
    return {"me": get_me_state(resolved_context), "bootstrap": get_bootstrap_state(resolved_context)}


def init_db(force_reset: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_sqlite_data_dir(DB_SETTINGS)
    if force_reset and DB_SETTINGS.is_sqlite and DB_PATH.exists():
        DB_PATH.unlink()

    with connect_db() as conn:
        if force_reset and not DB_SETTINGS.is_sqlite:
            reset_database(DB_SETTINGS, conn)
        conn.executescript(SCHEMA_SQL)
        has_data = conn.execute("SELECT COUNT(*) AS count FROM organizers").fetchone()["count"]
        if not has_data:
            seed_demo(conn)
        ensure_demo_auth_seed(conn)
        sync_identity_sequences(DB_SETTINGS, conn)
        conn.commit()


def ensure_demo_auth_seed(conn: sqlite3.Connection, created_at: str | None = None) -> None:
    created_at = created_at or now_iso()
    users = [
        (
            demo_user["id"],
            demo_user["email"],
            hash_password(demo_user["password"]),
            demo_user["full_name"],
            demo_user["user_type"],
            1,
            created_at,
            None,
        )
        for demo_user in DEMO_AUTH_USERS
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO users (id, email, password_hash, full_name, user_type, is_active, created_at, last_login_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        users,
    )

    user_contexts = [
        (
            index,
            demo_user["id"],
            CONFIG.dev_organizer_id,
            CONFIG.dev_program_id,
            CONFIG.dev_participant_id,
            demo_user["role"],
            demo_user["is_default"],
        )
        for index, demo_user in enumerate(DEMO_AUTH_USERS, start=1)
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO user_contexts (
            id, user_id, organizer_id, program_id, participant_id, role, is_default
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        user_contexts,
    )

    organization_memberships = [
        (1, 1, CONFIG.dev_organizer_id, "owner", 1, created_at),
        (2, 3, CONFIG.dev_organizer_id, "admin", 1, created_at),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO organization_memberships (
            id, user_id, organizer_id, role, is_default, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        organization_memberships,
    )

    program_memberships = [
        (1, 1, CONFIG.dev_program_id, CONFIG.dev_participant_id, "participant", 1, created_at),
        (2, 1, CONFIG.dev_program_id, None, "organizer", 0, created_at),
        (3, 2, CONFIG.dev_program_id, CONFIG.dev_participant_id, "participant", 1, created_at),
        (4, 3, CONFIG.dev_program_id, None, "organizer", 1, created_at),
        (5, 1, 2, CONFIG.dev_participant_id, "participant", 0, created_at),
        (6, 1, 2, None, "organizer", 0, created_at),
        (7, 3, 2, None, "organizer", 0, created_at),
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO program_memberships (
            id, user_id, program_id, participant_id, role, is_default, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        program_memberships,
    )


def seed_demo(conn: sqlite3.Connection) -> None:
    today = date.today()
    joined_at = f"{today - timedelta(days=10)} 09:00:00"
    current_time = now_iso()

    conn.execute(
        """
        INSERT INTO organizers (id, name, email, brand_name, primary_color, accent_color, support_email, tagline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            CONFIG.dev_organizer_id,
            "Мария Волкова",
            "maria@goalmate.local",
            "Habit Power",
            "#10A37F",
            "#FF8A3D",
            "support@goalmate.local",
            "Платформа-конструктор для марафонов, интенсивов и челленджей",
        ),
    )

    programs = [
        (
            1,
            CONFIG.dev_organizer_id,
            None,
            "Весенний wellness-марафон Habit Power",
            "spring-wellness",
            "Поток для участников, которым нужен красивый трекер, поддержка команды и мягкий возврат после пропуска.",
            "B2B cohort",
            str(today - timedelta(days=10)),
            str(today + timedelta(days=21)),
            "active",
        ),
        (
            2,
            CONFIG.dev_organizer_id,
            None,
            "Зимний перезапуск привычек",
            "winter-reset",
            "Архивный поток, который можно быстро клонировать и адаптировать под новый запуск.",
            "Reusable template",
            str(today - timedelta(days=80)),
            str(today - timedelta(days=40)),
            "archived",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO programs (id, organizer_id, source_program_id, name, slug, description, audience, start_date, end_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        programs,
    )

    modules = [
        (1, 1, "Запуск ритма", "Лёгкий старт без чувства перегруза и с быстрыми победами.", "Неделя 1", 1),
        (2, 1, "Фокус и энергия", "Точки опоры на середину марафона и защита от слива.", "Неделя 2", 2),
        (3, 1, "Команда и рефлексия", "Сообщество, обратная связь и закрепление результатов.", "Неделя 3", 3),
        (4, 2, "Перезагрузка", "Блок старта архивного шаблона.", "Неделя 1", 1),
        (5, 2, "Стабилизация", "Блок удержания темпа.", "Неделя 2", 2),
    ]
    conn.executemany(
        """
        INSERT INTO modules (id, program_id, title, description, week_label, position)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        modules,
    )

    tasks = [
        (
            1,
            1,
            1,
            "ДЗ №5: Запишите утреннюю разминку",
            "Короткое видео или фото с вашей утренней активацией. Цель — войти в ритм без перегруза.",
            "video",
            "photo",
            100,
            12,
            str(today - timedelta(days=1)),
            1,
            "Пропуск не обнуляет прогресс. Вернись с укороченной версией на 5 минут.",
        ),
        (
            2,
            1,
            2,
            "ДЗ №6: Прочитать 1 главу книги",
            "Подчеркните одну мысль, которая реально влияет на ваш текущий фокус.",
            "reading",
            "checklist",
            150,
            25,
            str(today),
            2,
            "Вернись в задачу через одну ключевую мысль вместо идеального конспекта.",
        ),
        (
            3,
            1,
            2,
            "ДЗ №7: Вечерний дневник благодарности",
            "Три наблюдения за день и одна вещь, которую хочется повторить завтра.",
            "journal",
            "text",
            80,
            10,
            str(today + timedelta(days=1)),
            3,
            "Если день выпал, заполни дневник одним абзацем без чувства провала.",
        ),
        (
            4,
            1,
            2,
            "ДЗ №4: Вечерняя медитация",
            "10 минут на выдох, сброс шума и закрытие дня.",
            "meditation",
            "voice",
            120,
            10,
            str(today - timedelta(days=1)),
            4,
            "Ничего страшного: вернись через короткую двухминутную версию и продолжай марафон.",
        ),
        (
            5,
            1,
            3,
            "ДЗ №8: Напишите другу о цели недели",
            "Сформулируйте цель так, чтобы друг мог проверить факт её достижения.",
            "accountability",
            "text",
            90,
            7,
            str(today + timedelta(days=2)),
            5,
            "Если не получилось вовремя, отправь одно сообщение с самой важной целью.",
        ),
        (
            6,
            1,
            3,
            "ДЗ №9: План на завтра",
            "Определи один обязательный шаг, который точно будет сделан утром.",
            "planning",
            "text",
            60,
            5,
            str(today + timedelta(days=2)),
            6,
            "Вернись с микропланом из одного шага, а не идеальным расписанием.",
        ),
        (
            7,
            2,
            4,
            "Разгрузить календарь",
            "Освободить один слот и вернуть себе внимание.",
            "planning",
            "text",
            60,
            10,
            str(today - timedelta(days=70)),
            1,
            "Сделай один шаг вместо полной ревизии.",
        ),
        (
            8,
            2,
            4,
            "5 минут движения",
            "Короткая физическая активация на старте дня.",
            "movement",
            "photo",
            70,
            5,
            str(today - timedelta(days=69)),
            2,
            "Подойдёт даже прогулка вокруг дома.",
        ),
        (
            9,
            2,
            5,
            "Антишум-чек",
            "Поймать главный отвлекающий триггер недели.",
            "reflection",
            "text",
            90,
            8,
            str(today - timedelta(days=65)),
            3,
            "Достаточно одной честной заметки.",
        ),
        (
            10,
            2,
            5,
            "Фокус-обещание",
            "Отправить напарнику одну цель до пятницы.",
            "accountability",
            "text",
            90,
            6,
            str(today - timedelta(days=63)),
            4,
            "Даже короткое сообщение уже работает.",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO tasks (
            id, program_id, module_id, title, description, task_type, submission_mode,
            points, estimated_minutes, scheduled_for, position, soft_return_copy
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tasks,
    )

    participants = [
        (1, "Анна Петрова", "anna@demo.local", "Москва", "Строю систему привычек без жёсткого давления.", "#FFD9C5", 6, f"{today} 08:15:00"),
        (2, "Александр К.", "alex@demo.local", "Сочи", "Хочу держать фокус даже в плотном графике.", "#B7E7E0", 12, f"{today} 07:40:00"),
        (3, "Ольга Р.", "olga@demo.local", "Казань", "Ищу ритм, который можно не сорвать через неделю.", "#F7E8AE", 10, f"{today - timedelta(days=1)} 19:00:00"),
        (4, "Иван С.", "ivan@demo.local", "Минск", "Мне нужна поддержка команды и понятный прогресс.", "#F6C4D0", 8, f"{today - timedelta(days=1)} 14:30:00"),
        (5, "Марина З.", "marina@demo.local", "Екатеринбург", "Прокачиваю дисциплину через мягкие ритуалы.", "#D7D4FF", 7, f"{today - timedelta(days=2)} 10:10:00"),
        (6, "Кирилл В.", "kirill@demo.local", "Санкт-Петербург", "Люблю короткие челленджи с друзьями.", "#D0F0C0", 5, f"{today} 06:55:00"),
        (7, "Илона П.", "ilona@demo.local", "Тбилиси", "Собираю устойчивую утреннюю рутину.", "#FFE6A7", 9, f"{today - timedelta(days=3)} 12:20:00"),
        (8, "Лев Н.", "lev@demo.local", "Новосибирск", "Тестирую привычки как продуктовые гипотезы.", "#C5E1FF", 11, f"{today} 08:35:00"),
    ]
    conn.executemany(
        """
        INSERT INTO participants (id, full_name, email, city, bio, avatar_bg, streak_days, last_active_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        participants,
    )
    ensure_demo_auth_seed(conn, current_time)

    enrollments = [
        (1, 1, 1, "participant", 75.0, 1250, 3, 4, 1, 0, joined_at),
        (2, 1, 2, "participant", 92.0, 2150, 7, 8, 0, 0, joined_at),
        (3, 1, 3, "participant", 89.0, 1980, 7, 8, 0, 0, joined_at),
        (4, 1, 4, "participant", 87.0, 1850, 6, 7, 0, 0, joined_at),
        (5, 1, 5, "participant", 76.0, 1380, 5, 7, 1, 1, joined_at),
        (6, 1, 6, "participant", 74.0, 1320, 5, 7, 0, 0, joined_at),
        (7, 1, 7, "participant", 61.0, 980, 4, 7, 2, 1, joined_at),
        (8, 1, 8, "participant", 70.0, 1200, 5, 8, 0, 0, joined_at),
        (9, 2, 1, "participant", 50.0, 420, 2, 4, 0, 0, joined_at),
    ]
    conn.executemany(
        """
        INSERT INTO enrollments (
            id, program_id, participant_id, role, progress_percent, xp, completed_tasks,
            total_tasks, soft_return_count, at_risk, joined_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        enrollments,
    )

    teams = [
        (1, 1, "Искры", "Держим ежедневный ритм без срывов больше двух дней подряд.", 65.0),
        (2, 1, "Фокус", "Собираем неделю без пропусков.", 72.0),
        (3, 1, "Импульс", "Больше отчётов, меньше шума.", 58.0),
        (4, 2, "Архив", "Смотрим, как шаблон выглядит после завершения потока.", 54.0),
    ]
    conn.executemany(
        """
        INSERT INTO teams (id, program_id, name, goal_text, progress_percent)
        VALUES (?, ?, ?, ?, ?)
        """,
        teams,
    )

    team_members = [
        (1, 1, 1, 0),
        (2, 1, 2, 1),
        (3, 1, 3, 0),
        (4, 1, 4, 0),
        (5, 2, 5, 1),
        (6, 2, 6, 0),
        (7, 3, 7, 1),
        (8, 3, 8, 0),
        (9, 4, 1, 1),
    ]
    conn.executemany(
        """
        INSERT INTO team_members (id, team_id, participant_id, is_captain)
        VALUES (?, ?, ?, ?)
        """,
        team_members,
    )

    participant_tasks = [
        (1, 1, 1, "completed", 100.0, 1, 0, str(today - timedelta(days=1)), f"{today - timedelta(days=1)} 09:05:00", f"{today - timedelta(days=1)} 09:05:00"),
        (2, 2, 1, "in_progress", 50.0, 0, 0, str(today), None, f"{today} 08:30:00"),
        (3, 3, 1, "planned", 0.0, 1, 1, str(today + timedelta(days=1)), None, current_time),
        (4, 4, 1, "missed", 0.0, 1, 1, str(today - timedelta(days=1)), None, f"{today - timedelta(days=1)} 22:00:00"),
        (5, 1, 2, "completed", 100.0, 1, 0, str(today - timedelta(days=1)), f"{today - timedelta(days=1)} 07:55:00", f"{today - timedelta(days=1)} 07:55:00"),
        (6, 2, 2, "completed", 100.0, 0, 0, str(today), f"{today} 07:30:00", f"{today} 07:30:00"),
        (7, 1, 3, "completed", 100.0, 1, 0, str(today - timedelta(days=1)), f"{today - timedelta(days=1)} 08:10:00", f"{today - timedelta(days=1)} 08:10:00"),
        (8, 2, 3, "completed", 100.0, 0, 0, str(today), f"{today} 06:40:00", f"{today} 06:40:00"),
        (9, 1, 4, "completed", 100.0, 1, 0, str(today - timedelta(days=1)), f"{today - timedelta(days=1)} 10:00:00", f"{today - timedelta(days=1)} 10:00:00"),
        (10, 2, 4, "in_progress", 60.0, 0, 0, str(today), None, f"{today} 07:10:00"),
        (11, 1, 5, "missed", 0.0, 1, 1, str(today - timedelta(days=2)), None, f"{today - timedelta(days=2)} 11:40:00"),
        (12, 1, 7, "missed", 0.0, 1, 1, str(today - timedelta(days=3)), None, f"{today - timedelta(days=3)} 11:00:00"),
        (13, 7, 1, "completed", 100.0, 1, 0, str(today - timedelta(days=70)), f"{today - timedelta(days=70)} 09:20:00", f"{today - timedelta(days=70)} 09:20:00"),
        (14, 8, 1, "completed", 100.0, 1, 0, str(today - timedelta(days=69)), f"{today - timedelta(days=69)} 08:45:00", f"{today - timedelta(days=69)} 08:45:00"),
        (15, 9, 1, "planned", 0.0, 1, 1, str(today - timedelta(days=65)), None, f"{today - timedelta(days=65)} 08:10:00"),
        (16, 10, 1, "planned", 0.0, 1, 1, str(today - timedelta(days=63)), None, f"{today - timedelta(days=63)} 08:10:00"),
    ]
    conn.executemany(
        """
        INSERT INTO participant_tasks (
            id, task_id, participant_id, status, progress_percent, report_required,
            soft_return_available, planned_for, completed_at, last_interaction_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        participant_tasks,
    )

    reports = [
        (1, 1, 1, 1, "photo", "Отличный старт! Видео принято. Ритм зашёл с первого дня.", "warmup.mp4", "accepted", f"{today - timedelta(days=1)} 09:08:00"),
        (2, 5, 2, 1, "photo", "Сделал короткую разминку прямо перед первым созвоном.", "alex-stretch.jpg", "accepted", f"{today - timedelta(days=1)} 08:00:00"),
        (3, 7, 3, 1, "photo", "Сработало лучше, чем ожидала. Захотелось продолжить.", "olga-start.jpg", "accepted", f"{today - timedelta(days=1)} 08:12:00"),
        (4, 9, 4, 1, "photo", "Команда подстёгивает. Отчёт сдан вовремя.", "ivan-move.jpg", "accepted", f"{today - timedelta(days=1)} 10:03:00"),
        (5, 13, 1, 7, "text", "Архивный поток остался как хороший шаблон для перезапуска.", None, "accepted", f"{today - timedelta(days=70)} 09:25:00"),
    ]
    conn.executemany(
        """
        INSERT INTO reports (
            id, participant_task_id, participant_id, task_id, report_type, content,
            attachment_name, status, submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        reports,
    )

    notifications = [
        (1, 1, 1, "Команда почти закрыла день", "В мини-команде 'Искры' уже 3 из 4 человек сдали отчёт. Можно добить день без лишнего напряжения.", "team", "accountability", "Открыть команду", 0, f"{today} 08:00:00"),
        (2, 1, 1, "Мягкий возврат доступен", "Ты пропустила вечернюю медитацию. Нажми один раз и вернись через короткую версию, без чувства провала.", "soft_return", "missed_task", "Вернуться мягко", 0, f"{today} 07:30:00"),
        (3, 1, 1, "Организатор открыл новую неделю", "В конструкторе потока появился новый блок про фокус и энергию. Можно заглянуть в задания заранее.", "program", "new_module", "Посмотреть блок", 1, f"{today - timedelta(days=1)} 18:10:00"),
        (4, 1, 2, "Архивный поток доступен", "Можно переключиться в зимний шаблон и быстро клонировать его под новый запуск.", "program", "scope_switch", "Открыть архив", 1, f"{today - timedelta(days=5)} 12:00:00"),
    ]
    conn.executemany(
        """
        INSERT INTO notifications (
            id, participant_id, program_id, title, message, notification_type,
            trigger_reason, cta_label, is_read, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        notifications,
    )

    daily_metrics = []
    for offset, active, reports_count, missed, completion in [
        (6, 68, 34, 11, 58.0),
        (5, 72, 39, 9, 61.0),
        (4, 76, 42, 8, 64.0),
        (3, 74, 37, 12, 62.0),
        (2, 79, 45, 7, 69.0),
        (1, 81, 48, 6, 72.0),
        (0, 84, 51, 5, 75.0),
    ]:
        daily_metrics.append((None, 1, str(today - timedelta(days=offset)), active, reports_count, missed, completion))
    for offset, active, reports_count, missed, completion in [
        (70, 18, 8, 3, 42.0),
        (69, 19, 9, 2, 47.0),
        (68, 21, 10, 2, 50.0),
    ]:
        daily_metrics.append((None, 2, str(today - timedelta(days=offset)), active, reports_count, missed, completion))
    conn.executemany(
        """
        INSERT INTO daily_metrics (
            id, program_id, metric_date, active_participants, reports_submitted, missed_tasks, completion_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        daily_metrics,
    )

    private_challenges = [
        (1, 1, "Английский по утрам", "Личный B2C-челлендж для мини-команды друзей без организатора.", "5 коротких сессий английского в неделю", 5, 4, str(today), str(today + timedelta(days=21)), "active", "friends"),
    ]
    conn.executemany(
        """
        INSERT INTO private_challenges (
            id, creator_participant_id, name, description, goal_text, target_per_week,
            target_team_size, start_date, end_date, status, visibility
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        private_challenges,
    )

    challenge_members = [
        (1, 1, 1, "creator", current_time),
        (2, 1, 6, "member", current_time),
        (3, 1, 8, "member", current_time),
    ]
    conn.executemany(
        """
        INSERT INTO private_challenge_members (id, challenge_id, participant_id, role, joined_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        challenge_members,
    )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def progress_badge(status: str) -> dict[str, str]:
    mapping = {
        "completed": {"label": "Выполнено", "tone": "success"},
        "in_progress": {"label": "В процессе", "tone": "info"},
        "planned": {"label": "Запланировано", "tone": "neutral"},
        "missed": {"label": "Пропущено", "tone": "warning"},
    }
    return mapping.get(status, {"label": status, "tone": "neutral"})


def get_modules_with_tasks(conn: sqlite3.Connection, program_id: int) -> list[dict]:
    modules = [row_to_dict(row) for row in conn.execute(
        "SELECT * FROM modules WHERE program_id = ? ORDER BY position",
        (program_id,),
    ).fetchall()]

    tasks = [row_to_dict(row) for row in conn.execute(
        """
        SELECT t.*, m.title AS module_title
        FROM tasks t
        JOIN modules m ON m.id = t.module_id
        WHERE t.program_id = ?
        ORDER BY m.position, t.position
        """,
        (program_id,),
    ).fetchall()]

    grouped: dict[int, list[dict]] = {}
    for task in tasks:
        grouped.setdefault(task["module_id"], []).append(task)

    for module in modules:
        module["tasks"] = grouped.get(module["id"], [])
    return modules


def get_bootstrap_state(context: RequestContext | None = None) -> dict:
    context = context or current_request_context()

    with connect_db() as conn:
        program = row_to_dict(conn.execute(
            """
            SELECT p.*, o.brand_name, o.primary_color, o.accent_color, o.tagline
            FROM programs p
            JOIN organizers o ON o.id = p.organizer_id
            WHERE p.id = ?
            """,
            (context.program_id,),
        ).fetchone())

        organizer = row_to_dict(conn.execute(
            "SELECT * FROM organizers WHERE id = ?",
            (context.organizer_id,),
        ).fetchone())

        participant = row_to_dict(conn.execute(
            "SELECT * FROM participants WHERE id = ?",
            (context.participant_id,),
        ).fetchone())

        enrollment = row_to_dict(conn.execute(
            """
            SELECT * FROM enrollments
            WHERE program_id = ? AND participant_id = ?
            """,
            (context.program_id, context.participant_id),
        ).fetchone())

        task_rows = conn.execute(
            """
            SELECT
                pt.id AS participant_task_id,
                pt.status,
                pt.progress_percent AS participant_progress,
                pt.report_required,
                pt.soft_return_available,
                pt.planned_for,
                pt.completed_at,
                t.id AS task_id,
                t.title,
                t.description,
                t.task_type,
                t.submission_mode,
                t.points,
                t.estimated_minutes,
                t.scheduled_for,
                t.soft_return_copy,
                m.title AS module_title,
                r.report_type,
                r.content AS report_content,
                r.attachment_name,
                r.status AS report_status,
                r.submitted_at
            FROM participant_tasks pt
            JOIN tasks t ON t.id = pt.task_id
            JOIN modules m ON m.id = t.module_id
            LEFT JOIN reports r ON r.participant_task_id = pt.id
            WHERE pt.participant_id = ? AND t.program_id = ?
            ORDER BY
                CASE pt.status
                    WHEN 'in_progress' THEN 1
                    WHEN 'missed' THEN 2
                    WHEN 'planned' THEN 3
                    WHEN 'completed' THEN 4
                    ELSE 5
                END,
                t.position
            """,
            (context.participant_id, context.program_id),
        ).fetchall()

        participant_tasks = []
        for row in task_rows:
            card = row_to_dict(row)
            card["badge"] = progress_badge(card["status"])
            participant_tasks.append(card)

        notifications = [row_to_dict(row) for row in conn.execute(
            """
            SELECT *
            FROM notifications
            WHERE participant_id = ? AND program_id = ?
            ORDER BY is_read ASC, created_at DESC
            """,
            (context.participant_id, context.program_id),
        ).fetchall()]

        leaderboard_rows = [row_to_dict(row) for row in conn.execute(
            """
            SELECT
                e.participant_id,
                p.full_name,
                p.avatar_bg,
                e.progress_percent,
                e.xp,
                e.completed_tasks,
                e.total_tasks,
                e.at_risk,
                p.last_active_at
            FROM enrollments e
            JOIN participants p ON p.id = e.participant_id
            WHERE e.program_id = ?
            ORDER BY e.xp DESC, e.progress_percent DESC, p.full_name ASC
            """,
            (context.program_id,),
        ).fetchall()]
        for index, row in enumerate(leaderboard_rows, start=1):
            row["rank"] = index

        top_three = leaderboard_rows[:3]
        current_rank = next((row["rank"] for row in leaderboard_rows if row["participant_id"] == context.participant_id), None)

        current_team = row_to_dict(conn.execute(
            """
            SELECT t.*
            FROM teams t
            JOIN team_members tm ON tm.team_id = t.id
            WHERE tm.participant_id = ? AND t.program_id = ?
            """,
            (context.participant_id, context.program_id),
        ).fetchone())

        team_members = [row_to_dict(row) for row in conn.execute(
            """
            SELECT
                p.id,
                p.full_name,
                p.avatar_bg,
                p.streak_days,
                e.progress_percent,
                e.xp,
                tm.is_captain
            FROM team_members tm
            JOIN participants p ON p.id = tm.participant_id
            JOIN enrollments e ON e.participant_id = p.id AND e.program_id = ?
            WHERE tm.team_id = ?
            ORDER BY e.xp DESC
            """,
            (context.program_id, current_team["id"]),
        ).fetchall()]

        team_xp = sum(member["xp"] for member in team_members)
        team_done_today = sum(1 for member in team_members if member["progress_percent"] >= 75)

        recent_reports = [row_to_dict(row) for row in conn.execute(
            """
            SELECT
                r.id,
                p.full_name,
                p.avatar_bg,
                t.title,
                r.report_type,
                r.content,
                r.status,
                r.submitted_at
            FROM reports r
            JOIN participants p ON p.id = r.participant_id
            JOIN tasks t ON t.id = r.task_id
            JOIN participant_tasks pt ON pt.id = r.participant_task_id
            JOIN tasks rt ON rt.id = pt.task_id
            WHERE rt.program_id = ?
            ORDER BY r.submitted_at DESC
            LIMIT 6
            """,
            (context.program_id,),
        ).fetchall()]

        at_risk = [row_to_dict(row) for row in conn.execute(
            """
            SELECT
                p.id,
                p.full_name,
                p.avatar_bg,
                e.progress_percent,
                e.xp,
                e.soft_return_count,
                p.last_active_at
            FROM enrollments e
            JOIN participants p ON p.id = e.participant_id
            WHERE e.program_id = ? AND e.at_risk = 1
            ORDER BY p.last_active_at ASC
            """,
            (context.program_id,),
        ).fetchall()]

        metrics = [row_to_dict(row) for row in conn.execute(
            """
            SELECT *
            FROM daily_metrics
            WHERE program_id = ?
            ORDER BY metric_date ASC
            """,
            (context.program_id,),
        ).fetchall()]

        private_challenges = [row_to_dict(row) for row in conn.execute(
            """
            SELECT
                pc.*,
                COUNT(pcm.participant_id) AS member_count
            FROM private_challenges pc
            LEFT JOIN private_challenge_members pcm ON pcm.challenge_id = pc.id
            GROUP BY pc.id
            ORDER BY pc.id DESC
            """,
        ).fetchall()]
        for challenge in private_challenges:
            members = [row_to_dict(row) for row in conn.execute(
                """
                SELECT p.id, p.full_name, p.avatar_bg
                FROM private_challenge_members pcm
                JOIN participants p ON p.id = pcm.participant_id
                WHERE pcm.challenge_id = ?
                ORDER BY pcm.role DESC, p.full_name ASC
                """,
                (challenge["id"],),
            ).fetchall()]
            challenge["members"] = members

        reusable_programs = [row_to_dict(row) for row in conn.execute(
            """
            SELECT
                p.id,
                p.name,
                p.status,
                p.start_date,
                p.end_date,
                COUNT(DISTINCT m.id) AS module_count,
                COUNT(DISTINCT t.id) AS task_count
            FROM programs p
            LEFT JOIN modules m ON m.program_id = p.id
            LEFT JOIN tasks t ON t.program_id = p.id
            WHERE p.organizer_id = ?
            GROUP BY p.id
            ORDER BY p.id DESC
            """,
            (context.organizer_id,),
        ).fetchall()]

        unread_notifications = sum(1 for item in notifications if item["is_read"] == 0)
        reports_today = sum(1 for item in recent_reports if item["submitted_at"].startswith(str(date.today())))
        completion_rate = round(sum(row["progress_percent"] for row in leaderboard_rows) / max(len(leaderboard_rows), 1), 1)
        today_focus = sum(1 for task in participant_tasks if task["status"] in {"completed", "in_progress"})
        total_focus = len(participant_tasks)

        return {
            "meta": {
                "projectName": "GoalMate",
                "currentDate": str(date.today()),
                "host": f"http://{CONFIG.host}:{CONFIG.port}",
                "appEnv": CONFIG.app_env,
                "contextSource": context.source,
                "databaseBackend": DB_SETTINGS.backend,
                "databaseTarget": DB_SETTINGS.label,
            },
            "program": program,
            "organizer": organizer,
            "participant": {
                **participant,
                **enrollment,
                "rank": current_rank,
                "shareCard": {
                    "title": "Карточка результата",
                    "subtitle": "Её можно использовать для вирального шеринга после прохождения потока.",
                    "progress_percent": enrollment["progress_percent"],
                    "xp": enrollment["xp"],
                    "rank": current_rank,
                    "streak_days": participant["streak_days"],
                    "team_name": current_team["name"],
                },
            },
            "participantBoard": {
                "tasks": participant_tasks,
                "todayFocus": today_focus,
                "totalFocus": total_focus,
                "missedCount": sum(1 for task in participant_tasks if task["status"] == "missed"),
                "softReturnCount": enrollment["soft_return_count"],
                "unreadNotifications": unread_notifications,
            },
            "leaderboard": {
                "topThree": top_three,
                "rows": leaderboard_rows,
            },
            "team": {
                **current_team,
                "xp_total": team_xp,
                "done_today": team_done_today,
                "member_count": len(team_members),
                "members": team_members,
            },
            "notifications": notifications,
            "organizerDashboard": {
                "totalParticipants": len(leaderboard_rows),
                "completionRate": completion_rate,
                "atRiskCount": len(at_risk),
                "reportsToday": reports_today,
                "recentReports": recent_reports,
                "atRiskParticipants": at_risk,
                "hoursSavedPerWeek": 5.6,
                "smartTriggers": [
                    {
                        "title": "Автоматический мягкий возврат",
                        "description": "Срабатывает, если участник пропустил день и не открыл платформу до вечера.",
                    },
                    {
                        "title": "Пинг мини-команды",
                        "description": "Напоминает о командной ответственности, когда 75% группы уже закрыли шаг.",
                    },
                    {
                        "title": "Риск выгорания",
                        "description": "Подсвечивает участников, которые замедляются после 2-х пропусков подряд.",
                    },
                ],
            },
            "builder": {
                "modules": get_modules_with_tasks(conn, context.program_id),
                "reusablePrograms": reusable_programs,
            },
            "analytics": {
                "dailyMetrics": metrics,
                "cohorts": [
                    {"label": "Сильный ритм", "count": sum(1 for row in leaderboard_rows if row["progress_percent"] >= 85), "tone": "success"},
                    {"label": "Нужен nudging", "count": sum(1 for row in leaderboard_rows if 70 <= row["progress_percent"] < 85), "tone": "info"},
                    {"label": "Высокий риск оттока", "count": len(at_risk), "tone": "warning"},
                ],
            },
            "privateChallenges": private_challenges,
        }


def add_notification(
    conn: sqlite3.Connection,
    context: RequestContext,
    title: str,
    message: str,
    notification_type: str,
    reason: str,
    cta_label: str,
) -> None:
    conn.execute(
        """
        INSERT INTO notifications (
            participant_id, program_id, title, message, notification_type,
            trigger_reason, cta_label, is_read, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            context.participant_id,
            context.program_id,
            title,
            message,
            notification_type,
            reason,
            cta_label,
            now_iso(),
        ),
    )


def refresh_progress(conn: sqlite3.Connection, context: RequestContext, participant_id: int) -> None:
    enrollment = conn.execute(
        """
        SELECT completed_tasks, total_tasks
        FROM enrollments
        WHERE program_id = ? AND participant_id = ?
        """,
        (context.program_id, participant_id),
    ).fetchone()
    if enrollment is None:
        return

    total_tasks = max(enrollment["total_tasks"], 1)
    progress = round((enrollment["completed_tasks"] / total_tasks) * 100, 1)
    conn.execute(
        """
        UPDATE enrollments
        SET progress_percent = ?
        WHERE program_id = ? AND participant_id = ?
        """,
        (progress, context.program_id, participant_id),
    )


def touch_participant(conn: sqlite3.Connection, participant_id: int) -> None:
    conn.execute(
        "UPDATE participants SET last_active_at = ? WHERE id = ?",
        (now_iso(), participant_id),
    )


def complete_task(participant_task_id: int, context: RequestContext | None = None, via_report: bool = False) -> dict:
    context = context or current_request_context()
    require_capability(context, "participant")

    with connect_db() as conn:
        record = conn.execute(
            """
            SELECT pt.*, t.points, t.title
            FROM participant_tasks pt
            JOIN tasks t ON t.id = pt.task_id
            WHERE pt.id = ? AND pt.participant_id = ?
            """,
            (participant_task_id, context.participant_id),
        ).fetchone()
        if record is None:
            raise ValueError("Задача не найдена")

        if record["status"] != "completed":
            conn.execute(
                """
                UPDATE participant_tasks
                SET status = 'completed',
                    progress_percent = 100,
                    soft_return_available = 0,
                    completed_at = ?,
                    last_interaction_at = ?
                WHERE id = ?
                """,
                (now_iso(), now_iso(), participant_task_id),
            )
            conn.execute(
                """
                UPDATE enrollments
                SET completed_tasks = completed_tasks + 1,
                    xp = xp + ?,
                    at_risk = 0
                WHERE program_id = ? AND participant_id = ?
                """,
                (record["points"], context.program_id, context.participant_id),
            )
            conn.execute(
                """
                UPDATE participants
                SET streak_days = streak_days + 1,
                    last_active_at = ?
                WHERE id = ?
                """,
                (now_iso(), context.participant_id),
            )
            refresh_progress(conn, context, context.participant_id)
            if via_report:
                add_notification(
                    conn,
                    context,
                    "Отчёт принят",
                    f"Задача '{record['title']}' засчитана. Прогресс обновлён автоматически.",
                    "report",
                    "report_accepted",
                    "Открыть прогресс",
                )
            else:
                add_notification(
                    conn,
                    context,
                    "Шаг закрыт",
                    f"Задача '{record['title']}' завершена. Темп удержан без лишнего давления.",
                    "progress",
                    "task_completed",
                    "Посмотреть задачи",
                )
        touch_participant(conn, context.participant_id)
        conn.commit()

    return get_bootstrap_state(context)


def soft_return_task(participant_task_id: int, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    require_capability(context, "participant")

    with connect_db() as conn:
        record = conn.execute(
            """
            SELECT pt.id, t.title
            FROM participant_tasks pt
            JOIN tasks t ON t.id = pt.task_id
            WHERE pt.id = ? AND pt.participant_id = ?
            """,
            (participant_task_id, context.participant_id),
        ).fetchone()
        if record is None:
            raise ValueError("Задача не найдена")

        conn.execute(
            """
            UPDATE participant_tasks
            SET status = 'in_progress',
                progress_percent = CASE
                    WHEN progress_percent < 25 THEN 25
                    ELSE progress_percent
                END,
                soft_return_available = 0,
                last_interaction_at = ?
            WHERE id = ?
            """,
            (now_iso(), participant_task_id),
        )
        conn.execute(
            """
            UPDATE enrollments
            SET soft_return_count = soft_return_count + 1,
                at_risk = 0
            WHERE program_id = ? AND participant_id = ?
            """,
            (context.program_id, context.participant_id),
        )
        touch_participant(conn, context.participant_id)
        add_notification(
            conn,
            context,
            "Мягкий возврат активирован",
            f"Задача '{record['title']}' снова в работе. Прогресс не обнулился.",
            "soft_return",
            "soft_return_used",
            "Продолжить",
        )
        conn.commit()

    return get_bootstrap_state(context)


def submit_report(payload: dict, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    require_capability(context, "participant")

    participant_task_id = int(payload.get("participantTaskId", 0))
    report_type = str(payload.get("reportType", "text")).strip() or "text"
    content = str(payload.get("content", "")).strip()
    attachment_name = str(payload.get("attachmentName", "")).strip() or None

    if not participant_task_id:
        raise ValueError("Нужен participantTaskId")
    if not content:
        raise ValueError("Добавь короткий текст отчёта")

    with connect_db() as conn:
        task = conn.execute(
            """
            SELECT pt.id, pt.task_id, t.title
            FROM participant_tasks pt
            JOIN tasks t ON t.id = pt.task_id
            WHERE pt.id = ? AND pt.participant_id = ?
            """,
            (participant_task_id, context.participant_id),
        ).fetchone()
        if task is None:
            raise ValueError("Задача для отчёта не найдена")

        existing = conn.execute(
            "SELECT id FROM reports WHERE participant_task_id = ?",
            (participant_task_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE reports
                SET report_type = ?, content = ?, attachment_name = ?, status = 'accepted', submitted_at = ?
                WHERE participant_task_id = ?
                """,
                (report_type, content, attachment_name, now_iso(), participant_task_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO reports (
                    participant_task_id, participant_id, task_id, report_type,
                    content, attachment_name, status, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'accepted', ?)
                """,
                (
                    participant_task_id,
                    context.participant_id,
                    task["task_id"],
                    report_type,
                    content,
                    attachment_name,
                    now_iso(),
                ),
            )
        touch_participant(conn, context.participant_id)
        conn.commit()

    return complete_task(participant_task_id, context=context, via_report=True)


def mark_notification_read(notification_id: int, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    require_capability(context, "participant")

    with connect_db() as conn:
        conn.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE id = ? AND participant_id = ?
            """,
            (notification_id, context.participant_id),
        )
        conn.commit()
    return get_bootstrap_state(context)


def create_module(payload: dict, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    require_capability(context, "organizer")

    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    week_label = str(payload.get("weekLabel", "")).strip() or "Новая неделя"
    if not title:
        raise ValueError("Название модуля обязательно")

    with connect_db() as conn:
        position = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM modules WHERE program_id = ?",
            (context.program_id,),
        ).fetchone()["next_position"]
        conn.execute(
            """
            INSERT INTO modules (program_id, title, description, week_label, position)
            VALUES (?, ?, ?, ?, ?)
            """,
            (context.program_id, title, description or "Новый блок в конструкторе GoalMate.", week_label, position),
        )
        conn.commit()
    return get_bootstrap_state(context)


def create_task(payload: dict, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    require_capability(context, "organizer")

    module_id = int(payload.get("moduleId", 0))
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    task_type = str(payload.get("taskType", "custom")).strip() or "custom"
    submission_mode = str(payload.get("submissionMode", "text")).strip() or "text"
    points = int(payload.get("points", 100))
    estimated_minutes = int(payload.get("estimatedMinutes", 15))
    scheduled_for = str(payload.get("scheduledFor", str(date.today() + timedelta(days=1))))
    soft_return_copy = str(payload.get("softReturnCopy", "")).strip() or "Можно вернуться укороченной версией шага."
    if not module_id or not title:
        raise ValueError("Нужны модуль и название задания")

    with connect_db() as conn:
        position = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM tasks WHERE module_id = ?",
            (module_id,),
        ).fetchone()["next_position"]
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                program_id, module_id, title, description, task_type, submission_mode,
                points, estimated_minutes, scheduled_for, position, soft_return_copy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context.program_id,
                module_id,
                title,
                description or "Новое задание из конструктора GoalMate.",
                task_type,
                submission_mode,
                points,
                estimated_minutes,
                scheduled_for,
                position,
                soft_return_copy,
            ),
        )
        new_task_id = cursor.lastrowid

        participants = [row["participant_id"] for row in conn.execute(
            "SELECT participant_id FROM enrollments WHERE program_id = ?",
            (context.program_id,),
        ).fetchall()]
        for participant_id in participants:
            conn.execute(
                """
                INSERT INTO participant_tasks (
                    task_id, participant_id, status, progress_percent, report_required,
                    soft_return_available, planned_for, completed_at, last_interaction_at
                ) VALUES (?, ?, 'planned', 0, ?, 1, ?, NULL, ?)
                """,
                (
                    new_task_id,
                    participant_id,
                    1 if submission_mode in {"text", "photo", "voice"} else 0,
                    scheduled_for,
                    now_iso(),
                ),
            )
            conn.execute(
                """
                UPDATE enrollments
                SET total_tasks = total_tasks + 1
                WHERE program_id = ? AND participant_id = ?
                """,
                (context.program_id, participant_id),
            )
            refresh_progress(conn, context, participant_id)
        conn.commit()
    return get_bootstrap_state(context)


def duplicate_program(program_id: int, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    require_capability(context, "organizer")

    with connect_db() as conn:
        source_program = conn.execute(
            "SELECT * FROM programs WHERE id = ? AND organizer_id = ?",
            (program_id, context.organizer_id),
        ).fetchone()
        if source_program is None:
            raise ValueError("Программа для копирования не найдена")

        new_name = f"{source_program['name']} (копия)"
        new_slug = f"{source_program['slug']}-copy-{int(datetime.now().timestamp())}"
        cursor = conn.execute(
            """
            INSERT INTO programs (
                organizer_id, source_program_id, name, slug, description, audience,
                start_date, end_date, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')
            """,
            (
                context.organizer_id,
                source_program["id"],
                new_name,
                new_slug,
                source_program["description"],
                source_program["audience"],
                str(date.today()),
                str(date.today() + timedelta(days=30)),
            ),
        )
        new_program_id = cursor.lastrowid

        module_map: dict[int, int] = {}
        for module in conn.execute(
            "SELECT * FROM modules WHERE program_id = ? ORDER BY position",
            (program_id,),
        ).fetchall():
            module_cursor = conn.execute(
                """
                INSERT INTO modules (program_id, title, description, week_label, position)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_program_id, module["title"], module["description"], module["week_label"], module["position"]),
            )
            module_map[module["id"]] = module_cursor.lastrowid

        for task in conn.execute(
            "SELECT * FROM tasks WHERE program_id = ? ORDER BY position",
            (program_id,),
        ).fetchall():
            conn.execute(
                """
                INSERT INTO tasks (
                    program_id, module_id, title, description, task_type, submission_mode,
                    points, estimated_minutes, scheduled_for, position, soft_return_copy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_program_id,
                    module_map[task["module_id"]],
                    task["title"],
                    task["description"],
                    task["task_type"],
                    task["submission_mode"],
                    task["points"],
                    task["estimated_minutes"],
                    task["scheduled_for"],
                    task["position"],
                    task["soft_return_copy"],
                ),
            )
        conn.commit()
    return get_bootstrap_state(context)


def update_branding(payload: dict, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    require_capability(context, "organizer")

    brand_name = str(payload.get("brandName", "")).strip()
    primary_color = str(payload.get("primaryColor", "")).strip()
    accent_color = str(payload.get("accentColor", "")).strip()
    support_email = str(payload.get("supportEmail", "")).strip()

    if not all([brand_name, primary_color, accent_color, support_email]):
        raise ValueError("Заполни все поля брендинга")

    with connect_db() as conn:
        conn.execute(
            """
            UPDATE organizers
            SET brand_name = ?, primary_color = ?, accent_color = ?, support_email = ?
            WHERE id = ?
            """,
            (brand_name, primary_color, accent_color, support_email, context.organizer_id),
        )
        conn.commit()
    return get_bootstrap_state(context)


def create_private_challenge(payload: dict, context: RequestContext | None = None) -> dict:
    context = context or current_request_context()
    require_capability(context, "participant")

    name = str(payload.get("name", "")).strip()
    goal_text = str(payload.get("goalText", "")).strip()
    description = str(payload.get("description", "")).strip()
    target_per_week = int(payload.get("targetPerWeek", 3))
    target_team_size = int(payload.get("targetTeamSize", 4))
    duration_weeks = int(payload.get("durationWeeks", 3))

    if not name or not goal_text:
        raise ValueError("Нужны название и цель челленджа")

    start_date = date.today()
    end_date = start_date + timedelta(days=duration_weeks * 7)
    with connect_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO private_challenges (
                creator_participant_id, name, description, goal_text, target_per_week,
                target_team_size, start_date, end_date, status, visibility
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', 'friends')
            """,
            (
                context.participant_id,
                name,
                description or "Новый приватный челлендж на базе GoalMate.",
                goal_text,
                target_per_week,
                target_team_size,
                str(start_date),
                str(end_date),
            ),
        )
        challenge_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO private_challenge_members (challenge_id, participant_id, role, joined_at)
            VALUES (?, ?, 'creator', ?)
            """,
            (challenge_id, context.participant_id, now_iso()),
        )
        conn.commit()
    return get_bootstrap_state(context)


def reset_demo(context: RequestContext | None = None) -> dict:
    if not CONFIG.is_development:
        raise AuthorizationError("Сброс демо доступен только в development-режиме")
    context = context or current_request_context()
    init_db(force_reset=True)
    return get_bootstrap_state(context)


class GoalMateHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def request_context(self) -> RequestContext:
        return current_request_context(self)

    def head_response(self, status: int, content_type: str = "application/json; charset=utf-8", content_length: int = 0) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.end_headers()

    def send_json(self, payload: dict, status: int = 200, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for header_name, header_value in extra_headers or []:
            self.send_header(header_name, header_value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}
        raw_body = self.rfile.read(content_length)
        return json.loads(raw_body.decode("utf-8"))

    def serve_static(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        mime_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
        }
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_types.get(file_path.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/bootstrap":
            self.send_json({"ok": True, "data": get_bootstrap_state(self.request_context())})
            return
        if path == "/api/me":
            self.send_json({"ok": True, "data": get_me_state(self.request_context())})
            return

        if path == "/":
            self.serve_static(STATIC_DIR / "index.html")
            return

        if path in {"/styles.css", "/app.js"}:
            self.serve_static(STATIC_DIR / path.lstrip("/"))
            return

        if path.startswith("/static/"):
            self.serve_static(ROOT_DIR / path.lstrip("/"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Route not found")

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/bootstrap":
            body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
            self.head_response(HTTPStatus.OK, "application/json; charset=utf-8", len(body))
            return
        if path == "/api/me":
            body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
            self.head_response(HTTPStatus.OK, "application/json; charset=utf-8", len(body))
            return

        if path == "/":
            file_path = STATIC_DIR / "index.html"
            if file_path.exists():
                self.head_response(HTTPStatus.OK, "text/html; charset=utf-8", file_path.stat().st_size)
                return

        if path in {"/styles.css", "/app.js"}:
            file_path = STATIC_DIR / path.lstrip("/")
            if file_path.exists():
                content_type = "text/css; charset=utf-8" if path.endswith(".css") else "application/javascript; charset=utf-8"
                self.head_response(HTTPStatus.OK, content_type, file_path.stat().st_size)
                return

        self.send_error(HTTPStatus.NOT_FOUND, "Route not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            context = self.request_context()
            payload = self.read_json_body()
            if path == "/api/auth/login":
                auth_payload, session_cookie = login_user(payload, self)
                self.send_json({"ok": True, "data": auth_payload}, extra_headers=[("Set-Cookie", session_cookie)])
                return
            if path == "/api/auth/logout":
                auth_payload, session_cookie = logout_user(context)
                self.send_json({"ok": True, "data": auth_payload}, extra_headers=[("Set-Cookie", session_cookie)])
                return
            if path == "/api/me/scope":
                self.send_json({"ok": True, "data": switch_session_scope(payload, context)})
                return
            if path == "/api/reports":
                self.send_json({"ok": True, "data": submit_report(payload, context)})
                return
            if path == "/api/builder/modules":
                self.send_json({"ok": True, "data": create_module(payload, context)})
                return
            if path == "/api/builder/tasks":
                self.send_json({"ok": True, "data": create_task(payload, context)})
                return
            if path == "/api/settings/branding":
                self.send_json({"ok": True, "data": update_branding(payload, context)})
                return
            if path == "/api/private-challenges":
                self.send_json({"ok": True, "data": create_private_challenge(payload, context)})
                return
            if path == "/api/reset-demo":
                self.send_json({"ok": True, "data": reset_demo(context)})
                return

            if path.startswith("/api/participant-tasks/") and path.endswith("/complete"):
                participant_task_id = int(path.split("/")[3])
                self.send_json({"ok": True, "data": complete_task(participant_task_id, context=context)})
                return
            if path.startswith("/api/participant-tasks/") and path.endswith("/soft-return"):
                participant_task_id = int(path.split("/")[3])
                self.send_json({"ok": True, "data": soft_return_task(participant_task_id, context)})
                return
            if path.startswith("/api/notifications/") and path.endswith("/read"):
                notification_id = int(path.split("/")[3])
                self.send_json({"ok": True, "data": mark_notification_read(notification_id, context)})
                return
            if path.startswith("/api/programs/") and path.endswith("/duplicate"):
                program_id = int(path.split("/")[3])
                self.send_json({"ok": True, "data": duplicate_program(program_id, context)})
                return
        except ValueError as error:
            self.send_json({"ok": False, "error": str(error)}, status=400)
            return
        except AuthorizationError as error:
            self.send_json({"ok": False, "error": str(error)}, status=403)
            return
        except sqlite3.IntegrityError as error:
            self.send_json({"ok": False, "error": f"Ошибка данных: {error}"}, status=400)
            return
        except Exception as error:
            self.send_json({"ok": False, "error": f"Внутренняя ошибка: {error}"}, status=500)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Route not found")


def run() -> None:
    init_db()
    server = ThreadingHTTPServer((CONFIG.host, CONFIG.port), GoalMateHandler)
    print(f"GoalMate is running on http://{CONFIG.host}:{CONFIG.port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
