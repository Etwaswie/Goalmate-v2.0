from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler

from goalmate.config import AppConfig


@dataclass(frozen=True)
class RequestContext:
    organizer_id: int
    program_id: int
    participant_id: int
    source: str
    user_id: int | None = None
    session_id: int | None = None
    session_expires_at: str | None = None
    role: str = "demo"
    available_roles: tuple[str, ...] = ("participant", "organizer")
    is_authenticated: bool = False


def get_request_context(config: AppConfig, handler: BaseHTTPRequestHandler | None = None) -> RequestContext:
    # This stays on a development fallback until real auth/session resolution lands.
    _ = handler
    return RequestContext(
        organizer_id=config.dev_organizer_id,
        program_id=config.dev_program_id,
        participant_id=config.dev_participant_id,
        source="development-fallback",
        role="mixed",
        available_roles=("participant", "organizer"),
    )
