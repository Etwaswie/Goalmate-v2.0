#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GoalMate — Backend v2.2 (Full Auth + Full CRUD Modules/Lessons)
"""
from __future__ import annotations
import json
import os
import sqlite3
import hashlib
import secrets
import mimetypes
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import base64

# === Конфигурация ===
ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = ROOT_DIR / "data"
UPLOADS_DIR = ROOT_DIR / "uploads"
DB_PATH = DATA_DIR / "goalmate.db"
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8000"))
TOKEN_EXPIRY_HOURS = 24

# === Инициализация папок ===
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# === Схема БД ===
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('creator', 'participant')),
    avatar_bg TEXT DEFAULT '#D4E8FF',
    created_at TEXT NOT NULL,
    last_active_at TEXT
);
-- Сессии
CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
-- Марафоны
CREATE TABLE IF NOT EXISTS programs (
    id INTEGER PRIMARY KEY,
    creator_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    goal_text TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
    cover_image TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE CASCADE
);
-- Коды приглашения
CREATE TABLE IF NOT EXISTS invitation_codes (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    code TEXT NOT NULL UNIQUE,
    max_uses INTEGER DEFAULT 1,
    used_count INTEGER DEFAULT 0,
    expires_at TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
);
-- Участие
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    invitation_code_id INTEGER,
    progress_percent REAL DEFAULT 0,
    xp INTEGER DEFAULT 0,
    completed_lessons INTEGER DEFAULT 0,
    total_lessons INTEGER DEFAULT 0,
    streak_days INTEGER DEFAULT 0,
    joined_at TEXT NOT NULL,
    last_activity_at TEXT,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (invitation_code_id) REFERENCES invitation_codes(id),
    UNIQUE (program_id, participant_id)
);
-- Модули
CREATE TABLE IF NOT EXISTS modules (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    position INTEGER NOT NULL,
    unlock_date TEXT,
    deadline TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE
);
-- Уроки
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY,
    module_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content_html TEXT,
    position INTEGER NOT NULL,
    unlock_date TEXT,
    deadline TEXT,
    points INTEGER DEFAULT 100,
    estimated_minutes INTEGER DEFAULT 15,
    created_at TEXT NOT NULL,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
);
-- Вложения
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    lesson_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
);
-- Прогресс
CREATE TABLE IF NOT EXISTS lesson_progress (
    id INTEGER PRIMARY KEY,
    lesson_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'locked' CHECK (status IN ('locked', 'available', 'in_progress', 'completed')),
    progress_percent REAL DEFAULT 0,
    completed_at TEXT,
    last_interaction_at TEXT NOT NULL,
    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (lesson_id, participant_id)
);
-- Комментарии
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    lesson_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES users(id) ON DELETE CASCADE
);
-- Оценки
CREATE TABLE IF NOT EXISTS ratings (
    id INTEGER PRIMARY KEY,
    lesson_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (lesson_id, participant_id)
);
-- Достижения
CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY,
    participant_id INTEGER NOT NULL,
    achievement_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    icon TEXT NOT NULL,
    unlocked_at TEXT NOT NULL,
    FOREIGN KEY (participant_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (participant_id, achievement_key)
);
-- Метрики
CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL,
    metric_date TEXT NOT NULL,
    active_participants INTEGER DEFAULT 0,
    lessons_completed INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    avg_rating REAL DEFAULT 0,
    FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE CASCADE,
    UNIQUE (program_id, metric_date)
);
-- Индексы
CREATE INDEX IF NOT EXISTS idx_auth_tokens_token ON auth_tokens(token);
CREATE INDEX IF NOT EXISTS idx_invitation_codes_code ON invitation_codes(code);
CREATE INDEX IF NOT EXISTS idx_enrollments_participant ON enrollments(participant_id);
CREATE INDEX IF NOT EXISTS idx_lessons_module ON lessons(module_id);
CREATE INDEX IF NOT EXISTS idx_progress_participant ON lesson_progress(participant_id);
CREATE INDEX IF NOT EXISTS idx_comments_lesson ON comments(lesson_id);
CREATE INDEX IF NOT EXISTS idx_ratings_lesson ON ratings(lesson_id);
"""

def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None: salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return hashed.hex(), salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    hashed, _ = hash_password(password, salt)
    return hashed == password_hash

def generate_token() -> str:
    return secrets.token_urlsafe(32)

def generate_invitation_code() -> str:
    return secrets.token_hex(4).upper()

def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(force_reset: bool = False) -> None:
    if force_reset and DB_PATH.exists():
        DB_PATH.unlink()
    with connect_db() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None: return None
    return {key: row[key] for key in row.keys()}

def get_user_by_token(token: str) -> dict | None:
    with connect_db() as conn:
        result = conn.execute("""
            SELECT u.*, t.expires_at FROM users u
            JOIN auth_tokens t ON t.user_id = u.id
            WHERE t.token = ? AND t.expires_at > ?
        """, (token, now_iso())).fetchone()
        return row_to_dict(result)

def create_auth_token(user_id: int) -> str:
    token = generate_token()
    expires_at = (datetime.now() + timedelta(hours=TOKEN_EXPIRY_HOURS)).isoformat(sep=" ")
    with connect_db() as conn:
        conn.execute("INSERT INTO auth_tokens (user_id, token, expires_at, created_at) VALUES (?, ?, ?, ?)",
                     (user_id, token, expires_at, now_iso()))
        conn.commit()
    return token

def touch_user_activity(user_id: int) -> None:
    with connect_db() as conn:
        conn.execute("UPDATE users SET last_active_at = ? WHERE id = ?", (now_iso(), user_id))
        conn.commit()

def check_achievement_unlocks(participant_id: int, program_id: int) -> list[dict]:
    unlocked = []
    with connect_db() as conn:
        completed = conn.execute("SELECT COUNT(*) as cnt FROM lesson_progress WHERE participant_id = ? AND status = 'completed'", (participant_id,)).fetchone()["cnt"]
        if completed >= 1:
            achievements = [
                ("first_step", "Первый шаг", "Вы прошли свой первый урок! 🎉", "🏆"),
                ("week_warrior", "Недельный воин", "7 дней активности подряд! 🔥", "⚡"),
                ("top_rater", "Эксперт", "Вы поставили 10 оценок! ⭐", "🌟"),
                ("commentator", "Комментатор", "Вы оставили 5 комментариев! 💬", "💭"),
            ]
            for key, title, desc, icon in achievements:
                existing = conn.execute("SELECT id FROM achievements WHERE participant_id = ? AND achievement_key = ?", (participant_id, key)).fetchone()
                if not existing:
                    condition = False
                    if key == "first_step": condition = completed >= 1
                    elif key == "week_warrior": condition = completed >= 7
                    elif key == "top_rater": condition = conn.execute("SELECT COUNT(*) as c FROM ratings WHERE participant_id = ?", (participant_id,)).fetchone()["c"] >= 10
                    elif key == "commentator": condition = conn.execute("SELECT COUNT(*) as c FROM comments WHERE participant_id = ?", (participant_id,)).fetchone()["c"] >= 5
                    
                    if condition:
                        conn.execute("INSERT INTO achievements (participant_id, achievement_key, title, description, icon, unlocked_at) VALUES (?, ?, ?, ?, ?, ?)",
                                     (participant_id, key, title, desc, icon, now_iso()))
                        unlocked.append({"key": key, "title": title, "description": desc, "icon": icon})
        conn.commit()
    return unlocked

# === API: Авторизация ===
def register_user(payload: dict) -> dict:
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "").strip()
    full_name = payload.get("full_name", "").strip()
    role = payload.get("role", "").strip()
    if not all([email, password, full_name, role]) or role not in ("creator", "participant"):
        raise ValueError("Заполните все поля корректно")
    if len(password) < 6: raise ValueError("Пароль должен быть не менее 6 символов")
    with connect_db() as conn:
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            raise ValueError("Пользователь с таким email уже существует")
        pwd_hash, salt = hash_password(password)
        cursor = conn.execute("INSERT INTO users (email, password_hash, full_name, role, created_at, last_active_at) VALUES (?, ?, ?, ?, ?, ?)",
                              (email, f"{salt}:{pwd_hash}", full_name, role, now_iso(), now_iso()))
        user_id = cursor.lastrowid
        conn.commit()
    return {"user_id": user_id, "token": create_auth_token(user_id), "role": role, "full_name": full_name}

def login_user(payload: dict) -> dict:
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "").strip()
    if not email or not password: raise ValueError("Введите email и пароль")
    with connect_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user: raise ValueError("Неверный email или пароль")
        stored = user["password_hash"]
        salt, stored_hash = stored.split(":", 1) if ":" in stored else ("", stored)
        if not verify_password(password, stored_hash, salt): raise ValueError("Неверный email или пароль")
    token = create_auth_token(user["id"])
    touch_user_activity(user["id"])
    return {"user_id": user["id"], "token": token, "role": user["role"], "full_name": user["full_name"], "avatar_bg": user["avatar_bg"]}

def logout_user(token: str) -> bool:
    with connect_db() as conn:
        conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
        conn.commit()
    return True

# === API: Марафоны ===
def create_program(creator_id: int, payload: dict) -> dict:
    name = payload.get("name", "").strip()
    description = payload.get("description", "").strip()
    goal_text = payload.get("goal_text", "").strip()
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    if not all([name, description, goal_text, start_date, end_date]): raise ValueError("Заполните все обязательные поля")
    slug = name.lower().replace(" ", "-") + "-" + secrets.token_hex(2)
    with connect_db() as conn:
        cursor = conn.execute("INSERT INTO programs (creator_id, name, slug, description, goal_text, start_date, end_date, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
                              (creator_id, name, slug, description, goal_text, start_date, end_date, now_iso(), now_iso()))
        program_id = cursor.lastrowid
        code = generate_invitation_code()
        conn.execute("INSERT INTO invitation_codes (program_id, code, max_uses, created_at) VALUES (?, ?, 100, ?)", (program_id, code, now_iso()))
        conn.commit()
    return {"program_id": program_id, "slug": slug, "invitation_code": code}

def get_creator_programs(creator_id: int) -> list[dict]:
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT p.*, COUNT(DISTINCT e.id) as enrolled_count, COUNT(DISTINCT m.id) as modules_count, COUNT(DISTINCT l.id) as lessons_count
            FROM programs p LEFT JOIN enrollments e ON e.program_id = p.id
            LEFT JOIN modules m ON m.program_id = p.id LEFT JOIN lessons l ON l.module_id = m.id
            WHERE p.creator_id = ? GROUP BY p.id ORDER BY p.updated_at DESC
        """, (creator_id,)).fetchall()
        return [row_to_dict(r) for r in rows]

def update_program(program_id: int, creator_id: int, payload: dict) -> dict:
    with connect_db() as conn:
        if not conn.execute("SELECT id FROM programs WHERE id = ? AND creator_id = ?", (program_id, creator_id)).fetchone():
            raise ValueError("Марафон не найден")
        updates, params = [], []
        for field in ["name", "description", "goal_text", "start_date", "end_date", "status", "cover_image"]:
            if field in payload:
                updates.append(f"{field} = ?")
                params.append(payload[field])
        updates.append("updated_at = ?"); params.append(now_iso())
        params.append(program_id)
        conn.execute(f"UPDATE programs SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone())

def generate_invitation_code_api(program_id: int, creator_id: int, payload: dict) -> dict:
    max_uses = int(payload.get("max_uses", 1))
    expires_at = payload.get("expires_at")
    with connect_db() as conn:
        if not conn.execute("SELECT id FROM programs WHERE id = ? AND creator_id = ?", (program_id, creator_id)).fetchone():
            raise ValueError("Марафон не найден")
        code = generate_invitation_code()
        conn.execute("INSERT INTO invitation_codes (program_id, code, max_uses, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
                     (program_id, code, max_uses, expires_at, now_iso()))
        conn.commit()
        return {"code": code, "max_uses": max_uses, "expires_at": expires_at}

def validate_invitation_code(code: str, participant_id: int) -> dict:
    code = code.strip().upper()
    with connect_db() as conn:
        invitation = conn.execute("""
            SELECT ic.*, p.id as program_id, p.name as program_name, p.creator_id
            FROM invitation_codes ic JOIN programs p ON p.id = ic.program_id
            WHERE ic.code = ? AND ic.is_active = 1 AND (ic.expires_at IS NULL OR ic.expires_at > ?) AND ic.used_count < ic.max_uses
        """, (code, now_iso())).fetchone()
        if not invitation: raise ValueError("Недействительный или истёкший код приглашения")
        if conn.execute("SELECT id FROM enrollments WHERE program_id = ? AND participant_id = ?", (invitation["program_id"], participant_id)).fetchone():
            raise ValueError("Вы уже присоединены к этому марафону")
        
        conn.execute("UPDATE invitation_codes SET used_count = used_count + 1 WHERE id = ?", (invitation["id"],))
        conn.execute("INSERT INTO enrollments (program_id, participant_id, invitation_code_id, joined_at, last_activity_at) VALUES (?, ?, ?, ?, ?)",
                     (invitation["program_id"], participant_id, invitation["id"], now_iso(), now_iso()))
        
        lessons = conn.execute("""
            SELECT l.id, m.unlock_date, l.unlock_date as lesson_unlock FROM lessons l
            JOIN modules m ON m.id = l.module_id WHERE m.program_id = ?
        """, (invitation["program_id"],)).fetchall()
        now = now_iso()
        for lesson in lessons:
            status = "locked"
            if (not lesson["unlock_date"] or lesson["unlock_date"] <= now) and (not lesson["lesson_unlock"] or lesson["lesson_unlock"] <= now):
                status = "available"
            conn.execute("INSERT INTO lesson_progress (lesson_id, participant_id, status, last_interaction_at) VALUES (?, ?, ?, ?)",
                         (lesson["id"], participant_id, status, now))
        
        conn.execute("UPDATE enrollments SET total_lessons = ? WHERE program_id = ? AND participant_id = ?",
                     (len(lessons), invitation["program_id"], participant_id))
        conn.commit()
        return {"program_id": invitation["program_id"], "program_name": invitation["program_name"], "enrolled": True}

# === API: Модули и Уроки (FULL CRUD) ===
def get_program_modules(program_id: int, creator_id: int) -> list[dict]:
    with connect_db() as conn:
        if not conn.execute("SELECT id FROM programs WHERE id = ? AND creator_id = ?", (program_id, creator_id)).fetchone():
            raise ValueError("Доступ запрещен")
        modules = []
        for mod in conn.execute("SELECT * FROM modules WHERE program_id = ? ORDER BY position", (program_id,)).fetchall():
            m = row_to_dict(mod)
            m["lessons"] = [row_to_dict(l) for l in conn.execute("SELECT * FROM lessons WHERE module_id = ? ORDER BY position", (m["id"],)).fetchall()]
            modules.append(m)
        return modules

def create_module(program_id: int, creator_id: int, payload: dict) -> dict:
    title = payload.get("title", "").strip()
    if not title: raise ValueError("Название обязательно")
    with connect_db() as conn:
        if not conn.execute("SELECT id FROM programs WHERE id = ? AND creator_id = ?", (program_id, creator_id)).fetchone(): raise ValueError("Марафон не найден")
        pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM modules WHERE program_id = ?", (program_id,)).fetchone()[0]
        cursor = conn.execute("INSERT INTO modules (program_id, title, description, position, unlock_date, deadline, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (program_id, title, payload.get("description",""), pos, payload.get("unlock_date"), payload.get("deadline"), now_iso()))
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM modules WHERE id = ?", (cursor.lastrowid,)).fetchone())

def update_module(module_id: int, creator_id: int, payload: dict) -> dict:
    with connect_db() as conn:
        if not conn.execute("SELECT m.id FROM modules m JOIN programs p ON p.id=m.program_id WHERE m.id=? AND p.creator_id=?", (module_id, creator_id)).fetchone():
            raise ValueError("Модуль не найден")
        updates, params = [], []
        for field in ["title", "description", "unlock_date", "deadline"]:
            if field in payload:
                updates.append(f"{field} = ?")
                params.append(payload[field])
        params.append(module_id)
        conn.execute(f"UPDATE modules SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone())

def delete_module(module_id: int, creator_id: int) -> dict:
    with connect_db() as conn:
        if not conn.execute("SELECT m.id FROM modules m JOIN programs p ON p.id=m.program_id WHERE m.id=? AND p.creator_id=?", (module_id, creator_id)).fetchone():
            raise ValueError("Модуль не найден")
        conn.execute("DELETE FROM modules WHERE id = ?", (module_id,))
        conn.commit()
        return {"deleted": True, "id": module_id}

def create_lesson(module_id: int, creator_id: int, payload: dict) -> dict:
    title = payload.get("title", "").strip()
    if not title: raise ValueError("Название урока обязательно")
    with connect_db() as conn:
        mod = conn.execute("SELECT m.id, m.program_id FROM modules m JOIN programs p ON p.id=m.program_id WHERE m.id=? AND p.creator_id=?", (module_id, creator_id)).fetchone()
        if not mod: raise ValueError("Модуль не найден")
        pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM lessons WHERE module_id = ?", (module_id,)).fetchone()[0]
        cursor = conn.execute("INSERT INTO lessons (module_id, title, content_html, position, unlock_date, deadline, points, estimated_minutes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (module_id, title, payload.get("content_html",""), pos, payload.get("unlock_date"), payload.get("deadline"), int(payload.get("points",100)), int(payload.get("estimated_minutes",15)), now_iso()))
        
        participants = conn.execute("SELECT participant_id FROM enrollments WHERE program_id = ?", (mod["program_id"],)).fetchall()
        for p in participants:
            status = "available" if (not payload.get("unlock_date") or payload.get("unlock_date") <= now_iso()) else "locked"
            conn.execute("INSERT OR IGNORE INTO lesson_progress (lesson_id, participant_id, status, last_interaction_at) VALUES (?, ?, ?, ?)",
                         (cursor.lastrowid, p["participant_id"], status, now_iso()))
            conn.execute("UPDATE enrollments SET total_lessons = total_lessons + 1 WHERE program_id = ? AND participant_id = ?", (mod["program_id"], p["participant_id"]))
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM lessons WHERE id = ?", (cursor.lastrowid,)).fetchone())

def update_lesson(lesson_id: int, creator_id: int, payload: dict) -> dict:
    with connect_db() as conn:
        if not conn.execute("SELECT l.id FROM lessons l JOIN modules m ON l.module_id=m.id JOIN programs p ON m.program_id=p.id WHERE l.id=? AND p.creator_id=?", (lesson_id, creator_id)).fetchone():
            raise ValueError("Урок не найден")
        updates, params = [], []
        for field in ["title", "content_html", "unlock_date", "deadline", "points", "estimated_minutes"]:
            if field in payload:
                updates.append(f"{field} = ?")
                params.append(payload[field] if field not in ["points", "estimated_minutes"] else int(payload[field]))
        params.append(lesson_id)
        conn.execute(f"UPDATE lessons SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone())

def delete_lesson(lesson_id: int, creator_id: int) -> dict:
    with connect_db() as conn:
        if not conn.execute("SELECT l.id FROM lessons l JOIN modules m ON l.module_id=m.id JOIN programs p ON m.program_id=p.id WHERE l.id=? AND p.creator_id=?", (lesson_id, creator_id)).fetchone():
            raise ValueError("Урок не найден")
        conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        conn.commit()
        return {"deleted": True, "id": lesson_id}

def upload_attachment(lesson_id: int, creator_id: int, filename: str, content_b64: str, mime_type: str) -> dict:
    try: file_content = base64.b64decode(content_b64.split(",")[1] if "," in content_b64 else content_b64)
    except Exception: raise ValueError("Некорректные данные файла")
    allowed = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4", "audio/mpeg", "text/plain"}
    if mime_type not in allowed: raise ValueError("Неподдерживаемый формат")
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    file_path = UPLOADS_DIR / f"{lesson_id}_{safe_name}"
    file_path.write_bytes(file_content)
    with connect_db() as conn:
        if not conn.execute("SELECT l.id FROM lessons l JOIN modules m ON l.module_id=m.id JOIN programs p ON p.id=m.program_id WHERE l.id=? AND p.creator_id=?", (lesson_id, creator_id)).fetchone():
            raise ValueError("Урок не найден")
        cursor = conn.execute("INSERT INTO attachments (lesson_id, filename, original_name, mime_type, size_bytes, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                              (lesson_id, safe_name, filename, mime_type, len(file_content), now_iso()))
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM attachments WHERE id = ?", (cursor.lastrowid,)).fetchone())

# === API: Участник ===
def get_participant_programs(participant_id: int) -> list[dict]:
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT p.*, e.progress_percent, e.xp, e.completed_lessons, e.total_lessons, e.streak_days, e.joined_at, ic.code as invitation_code
            FROM enrollments e JOIN programs p ON p.id = e.program_id LEFT JOIN invitation_codes ic ON ic.id = e.invitation_code_id
            WHERE e.participant_id = ? ORDER BY e.last_activity_at DESC
        """, (participant_id,)).fetchall()
        return [row_to_dict(r) for r in rows]

def get_program_structure(program_id: int, participant_id: int) -> dict:
    with connect_db() as conn:
        program = row_to_dict(conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone())
        if not program: raise ValueError("Марафон не найден")
        enrolled = conn.execute("SELECT * FROM enrollments WHERE program_id = ? AND participant_id = ?", (program_id, participant_id)).fetchone()
        if not enrolled: raise ValueError("Вы не присоединены к этому марафону")
        
        now = now_iso()
        modules = []
        for mod in conn.execute("SELECT * FROM modules WHERE program_id = ? ORDER BY position", (program_id,)).fetchall():
            module = row_to_dict(mod)
            module["status"] = "locked" if (module["unlock_date"] and module["unlock_date"] > now) else "available"
            lessons = []
            for lesson in conn.execute("""
                SELECT l.*, lp.status as progress_status, lp.progress_percent, lp.completed_at,
                       (SELECT AVG(r.rating) FROM ratings r WHERE r.lesson_id = l.id) as avg_rating,
                       (SELECT COUNT(*) FROM ratings r WHERE r.lesson_id = l.id) as rating_count,
                       (SELECT COUNT(*) FROM comments c WHERE c.lesson_id = l.id) as comments_count
                FROM lessons l LEFT JOIN lesson_progress lp ON lp.lesson_id = l.id AND lp.participant_id = ?
                WHERE l.module_id = ? ORDER BY l.position
            """, (participant_id, module["id"])).fetchall():
                l = row_to_dict(lesson)
                if module["status"] == "locked": l["status"] = "locked"
                elif l["unlock_date"] and l["unlock_date"] > now: l["status"] = "locked"
                elif l["deadline"] and l["deadline"] < now and l["progress_status"] != "completed": l["status"] = "expired"
                else: l["status"] = l["progress_status"] or "available"
                
                l["attachments"] = [row_to_dict(a) for a in conn.execute("SELECT * FROM attachments WHERE lesson_id = ?", (l["id"],)).fetchall()]
                l["comments"] = [row_to_dict(c) for c in conn.execute("""
                    SELECT c.*, u.full_name, u.avatar_bg FROM comments c JOIN users u ON u.id = c.participant_id
                    WHERE c.lesson_id = ? ORDER BY c.created_at DESC
                """, (l["id"],)).fetchall()]
                my_rating = conn.execute("SELECT rating FROM ratings WHERE lesson_id = ? AND participant_id = ?", (l["id"], participant_id)).fetchone()
                l["my_rating"] = my_rating["rating"] if my_rating else None
                lessons.append(l)
            module["lessons"] = lessons
            modules.append(module)
        
        stats = row_to_dict(conn.execute("""
            SELECT COUNT(CASE WHEN lp.status = 'completed' THEN 1 END) as completed,
                   COUNT(CASE WHEN lp.status = 'in_progress' THEN 1 END) as in_progress,
                   SUM(l.points) FILTER (WHERE lp.status = 'completed') as earned_xp
            FROM lessons l LEFT JOIN lesson_progress lp ON lp.lesson_id = l.id AND lp.participant_id = ?
            WHERE l.module_id IN (SELECT id FROM modules WHERE program_id = ?)
        """, (participant_id, program_id)).fetchone())
        
        achievements = [row_to_dict(a) for a in conn.execute("SELECT * FROM achievements WHERE participant_id = ? ORDER BY unlocked_at DESC", (participant_id,)).fetchall()]
        return {"program": program, "modules": modules, "stats": stats or {"completed": 0, "in_progress": 0, "earned_xp": 0}, "achievements": achievements, "progress": enrolled["progress_percent"]}

def update_lesson_progress(lesson_id: int, participant_id: int, status: str, progress: float = None) -> dict:
    if status not in ("available", "in_progress", "completed"): raise ValueError("Недопустимый статус")
    with connect_db() as conn:
        access = conn.execute("""
            SELECT l.id, m.program_id, e.id as enrollment_id FROM lessons l
            JOIN modules m ON m.id = l.module_id JOIN enrollments e ON e.program_id = m.program_id
            WHERE l.id = ? AND e.participant_id = ? AND (l.unlock_date IS NULL OR l.unlock_date <= ?) AND (m.unlock_date IS NULL OR m.unlock_date <= ?)
        """, (lesson_id, participant_id, now_iso(), now_iso())).fetchone()
        if not access: raise ValueError("Урок недоступен")
        
        updates, params = ["status = ?", "last_interaction_at = ?"], [status, now_iso()]
        if progress is not None: updates.append("progress_percent = ?"); params.append(min(100, max(0, progress)))
        if status == "completed":
            updates.append("completed_at = ?"); params.append(now_iso())
            lesson = conn.execute("SELECT points FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
            conn.execute("""
                UPDATE enrollments SET completed_lessons = completed_lessons + 1, xp = xp + ?,
                progress_percent = ROUND(100.0 * completed_lessons / NULLIF(total_lessons, 1), 1),
                streak_days = streak_days + 1, last_activity_at = ? WHERE enrollment_id = ?
            """, (lesson["points"], now_iso(), access["enrollment_id"]))
            check_achievement_unlocks(participant_id, access["program_id"])
        params.extend([lesson_id, participant_id])
        conn.execute(f"UPDATE lesson_progress SET {', '.join(updates)} WHERE lesson_id = ? AND participant_id = ?", params)
        conn.commit()
        return {"status": status, "progress": progress}

def add_comment(lesson_id: int, participant_id: int, content: str) -> dict:
    content = content.strip()
    if not content or len(content) > 2000: raise ValueError("Комментарий от 1 до 2000 символов")
    with connect_db() as conn:
        if not conn.execute("SELECT l.id FROM lessons l JOIN modules m ON l.module_id=m.id JOIN enrollments e ON e.program_id=m.program_id WHERE l.id=? AND e.participant_id=?", (lesson_id, participant_id)).fetchone():
            raise ValueError("Доступ запрещён")
        cursor = conn.execute("INSERT INTO comments (lesson_id, participant_id, content, created_at) VALUES (?, ?, ?, ?)", (lesson_id, participant_id, content, now_iso()))
        check_achievement_unlocks(participant_id, None)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM comments WHERE id = ?", (cursor.lastrowid,)).fetchone())

def add_rating(lesson_id: int, participant_id: int, rating: int) -> dict:
    if rating not in range(1, 6): raise ValueError("Оценка от 1 до 5")
    with connect_db() as conn:
        if not conn.execute("SELECT l.id FROM lessons l JOIN modules m ON l.module_id=m.id JOIN enrollments e ON e.program_id=m.program_id WHERE l.id=? AND e.participant_id=?", (lesson_id, participant_id)).fetchone():
            raise ValueError("Доступ запрещён")
        conn.execute("""
            INSERT INTO ratings (lesson_id, participant_id, rating, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(lesson_id, participant_id) DO UPDATE SET rating = ?, updated_at = ?
        """, (lesson_id, participant_id, rating, now_iso(), rating, now_iso()))
        check_achievement_unlocks(participant_id, None)
        conn.commit()
        return {"rating": rating, "lesson_id": lesson_id}

def get_participant_dashboard(participant_id: int) -> dict:
    with connect_db() as conn:
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (participant_id,)).fetchone())
        stats = row_to_dict(conn.execute("""
            SELECT COUNT(DISTINCT e.program_id) as programs_joined, SUM(e.completed_lessons) as total_completed,
                   SUM(e.xp) as total_xp, MAX(e.streak_days) as best_streak, COUNT(DISTINCT a.id) as achievements_count
            FROM enrollments e LEFT JOIN achievements a ON a.participant_id = e.participant_id WHERE e.participant_id = ?
        """, (participant_id,)).fetchone())
        recent = [row_to_dict(r) for r in conn.execute("""
            SELECT p.name as program_name, l.title as lesson_title, lp.completed_at, lp.status
            FROM lesson_progress lp JOIN lessons l ON l.id = lp.lesson_id JOIN modules m ON m.id = l.module_id
            JOIN programs p ON p.id = m.program_id WHERE lp.participant_id = ? AND lp.status = 'completed'
            ORDER BY lp.completed_at DESC LIMIT 5
        """, (participant_id,)).fetchall()]
        achievements = [row_to_dict(a) for a in conn.execute("SELECT * FROM achievements WHERE participant_id = ? ORDER BY unlocked_at DESC", (participant_id,)).fetchall()]
        active_programs = [row_to_dict(r) for r in conn.execute("""
            SELECT p.id, p.name, p.cover_image, e.progress_percent, e.xp, e.streak_days
            FROM enrollments e JOIN programs p ON p.id = e.program_id
            WHERE e.participant_id = ? AND p.status = 'active' ORDER BY e.last_activity_at DESC
        """, (participant_id,)).fetchall()]
        return {"user": user, "stats": stats or {}, "recent": recent, "achievements": achievements, "active_programs": active_programs}

def get_program_analytics(program_id: int, creator_id: int) -> dict:
    with connect_db() as conn:
        program = conn.execute("SELECT * FROM programs WHERE id = ? AND creator_id = ?", (program_id, creator_id)).fetchone()
        if not program: raise ValueError("Марафон не найден")
        stats = row_to_dict(conn.execute("""
            SELECT COUNT(DISTINCT e.participant_id) as total_participants, ROUND(AVG(e.progress_percent), 1) as avg_progress,
                   COUNT(CASE WHEN e.last_activity_at >= datetime('now', '-7 days') THEN 1 END) as active_week,
                   SUM(e.xp) as total_xp, COUNT(DISTINCT CASE WHEN lp.status = 'completed' THEN lp.id END) as lessons_completed
            FROM enrollments e LEFT JOIN lesson_progress lp ON lp.enrollment_id = e.id WHERE e.program_id = ?
        """, (program_id,)).fetchone())
        daily = [row_to_dict(r) for r in conn.execute("""
            SELECT metric_date, active_participants, lessons_completed, avg_rating FROM daily_metrics
            WHERE program_id = ? AND metric_date >= date('now', '-14 days') ORDER BY metric_date
        """, (program_id,)).fetchall()]
        top_participants = [row_to_dict(r) for r in conn.execute("""
            SELECT u.full_name, u.avatar_bg, e.progress_percent, e.xp, e.streak_days
            FROM enrollments e JOIN users u ON u.id = e.participant_id WHERE e.program_id = ?
            ORDER BY e.xp DESC, e.progress_percent DESC LIMIT 10
        """, (program_id,)).fetchall()]
        lesson_ratings = [row_to_dict(r) for r in conn.execute("""
            SELECT l.title, AVG(r.rating) as avg_rating, COUNT(r.id) as ratings_count
            FROM lessons l JOIN modules m ON m.id = l.module_id LEFT JOIN ratings r ON r.lesson_id = l.id
            WHERE m.program_id = ? GROUP BY l.id HAVING COUNT(r.id) > 0 ORDER BY avg_rating DESC
        """, (program_id,)).fetchall()]
        return {"program": row_to_dict(program), "stats": stats or {}, "daily": daily, "top_participants": top_participants, "lesson_ratings": lesson_ratings}

# === HTTP Handler ===
class GoalMateHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None: pass
    
    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    
    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
    
    def get_auth_token(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        return auth.replace("Bearer ", "") if auth.startswith("Bearer ") else None
    
    def require_auth(self, roles: list[str] = None) -> dict:
        token = self.get_auth_token()
        if not token: raise ValueError("Требуется авторизация")
        user = get_user_by_token(token)
        if not user: raise ValueError("Сессия истекла")
        if roles and user["role"] not in roles: raise ValueError("Нет прав")
        return user

    def serve_static(self, path: Path) -> None:
        if not path.exists(): self.send_error(404); return
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/": self.serve_static(STATIC_DIR / "index.html"); return
            if path in ("/styles.css", "/app.js"): self.serve_static(STATIC_DIR / path.lstrip("/")); return
            if path.startswith("/uploads/"): self.serve_static(UPLOADS_DIR / path.split("/")[-1]); return
            if path == "/api/health": self.send_json({"ok": True, "version": "2.2"}); return
            
            token = self.get_auth_token()
            if path == "/api/me":
                if not token: raise ValueError("Not auth")
                user = get_user_by_token(token)
                if not user: raise ValueError("Invalid token")
                touch_user_activity(user["id"])
                self.send_json({"ok": True, "data": user}); return
            
            if path == "/api/participant/dashboard":
                user = self.require_auth(["participant"])
                self.send_json({"ok": True, "data": get_participant_dashboard(user["id"])}); return
            if path == "/api/participant/programs":
                user = self.require_auth(["participant"])
                self.send_json({"ok": True, "data": get_participant_programs(user["id"])}); return
            if path.startswith("/api/programs/") and path.endswith("/structure"):
                pid = int(path.split("/")[3])
                user = self.require_auth(["participant"])
                self.send_json({"ok": True, "data": get_program_structure(pid, user["id"])}); return
            
            if path == "/api/creator/programs":
                user = self.require_auth(["creator"])
                self.send_json({"ok": True, "data": get_creator_programs(user["id"])}); return
            if path.startswith("/api/programs/") and path.endswith("/analytics"):
                pid = int(path.split("/")[3])
                user = self.require_auth(["creator"])
                self.send_json({"ok": True, "data": get_program_analytics(pid, user["id"])}); return
            
            # NEW: Get Modules List for Builder
            if path.startswith("/api/programs/") and path.endswith("/modules"):
                pid = int(path.split("/")[3])
                user = self.require_auth(["creator"])
                self.send_json({"ok": True, "data": get_program_modules(pid, user["id"])}); return

            if path.startswith("/api/attachments/"):
                aid = int(path.split("/")[3])
                with connect_db() as conn:
                    att = conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
                    if att: self.send_json({"ok": True, "data": row_to_dict(att)})
                    else: self.send_json({"ok": False, "error": "Not found"}, 404)
                return

            self.send_json({"ok": False, "error": "Route not found"}, 404)
        except ValueError as e: self.send_json({"ok": False, "error": str(e)}, 400)
        except Exception as e: self.send_json({"ok": False, "error": str(e)}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self.read_json_body()
            if path == "/api/auth/register":
                self.send_json({"ok": True, "data": register_user(payload)}); return
            if path == "/api/auth/login":
                self.send_json({"ok": True, "data": login_user(payload)}); return
            
            user = self.require_auth()
            if path == "/api/auth/logout":
                logout_user(self.get_auth_token()); self.send_json({"ok": True}); return
            
            if user["role"] == "creator":
                if path == "/api/programs":
                    self.send_json({"ok": True, "data": create_program(user["id"], payload)}); return
                if path.startswith("/api/programs/") and path.endswith("/update"):
                    pid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": update_program(pid, user["id"], payload)}); return
                if path.startswith("/api/programs/") and path.endswith("/invitation"):
                    pid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": generate_invitation_code_api(pid, user["id"], payload)}); return
                
                # Modules CRUD
                if path.startswith("/api/programs/") and path.endswith("/modules"):
                    pid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": create_module(pid, user["id"], payload)}); return
                if path.startswith("/api/modules/") and path.endswith("/update"):
                    mid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": update_module(mid, user["id"], payload)}); return
                if path.startswith("/api/modules/") and path.endswith("/delete"):
                    mid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": delete_module(mid, user["id"])}); return

                # Lessons CRUD
                if path.startswith("/api/modules/") and path.endswith("/lessons"):
                    mid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": create_lesson(mid, user["id"], payload)}); return
                if path.startswith("/api/lessons/") and path.endswith("/update"):
                    lid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": update_lesson(lid, user["id"], payload)}); return
                if path.startswith("/api/lessons/") and path.endswith("/delete"):
                    lid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": delete_lesson(lid, user["id"])}); return
                
                if path.startswith("/api/lessons/") and path.endswith("/attachments"):
                    lid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": upload_attachment(lid, user["id"], payload.get("filename",""), payload.get("content",""), payload.get("mime_type",""))}); return

            if user["role"] == "participant":
                if path.startswith("/api/lessons/") and path.endswith("/progress"):
                    lid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": update_lesson_progress(lid, user["id"], payload.get("status","in_progress"), payload.get("progress"))}); return
                if path.startswith("/api/lessons/") and path.endswith("/comments"):
                    lid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": add_comment(lid, user["id"], payload.get("content",""))}); return
                if path.startswith("/api/lessons/") and path.endswith("/rating"):
                    lid = int(path.split("/")[3])
                    self.send_json({"ok": True, "data": add_rating(lid, user["id"], int(payload.get("rating",5)))}); return
                
                if path.startswith("/api/programs/") and "/join" in path:
                    code = query.get("code", [None])[0] if (query := parse_qs(parsed.query)) else None # Fix for GET inside POST logic if needed, but join is usually GET. Keeping simple.
                    # Note: Join is typically GET, but if called via POST with body:
                    code = payload.get("code") if not code else code
                    if not code: raise ValueError("Нужен код")
                    self.send_json({"ok": True, "data": validate_invitation_code(code, user["id"])}); return

            self.send_json({"ok": False, "error": "Route not found"}, 404)
        except ValueError as e: self.send_json({"ok": False, "error": str(e)}, 400)
        except Exception as e: self.send_json({"ok": False, "error": str(e)}, 500)

def run():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), GoalMateHandler)
    print(f"✅ GoalMate запущен: http://{HOST}:{PORT}")
    print(f"📁 Данные: {DATA_DIR}")
    print(f"📁 Загрузки: {UPLOADS_DIR}")
    server.serve_forever()

if __name__ == "__main__":
    run()