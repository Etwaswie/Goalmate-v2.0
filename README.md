# GoalMate Demo

Локальная демка `GoalMate` для проверки основных сценариев:

- участник: задачи, мягкий возврат, отчёты, лидерборд, мини-команда
- организатор: дашборд, white-label, аналитика, no-code конструктор, дублирование программ
- growth: приватные челленджи друзей поверх B2B-потока

## Запуск

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Открой:

```text
http://127.0.0.1:8000
```

## Demo Auth

В development-режиме приложение по-прежнему работает через `development fallback`, даже если ты не логинился. Но теперь в локальной базе уже есть настоящие demo-пользователи и cookie-сессии:

- `demo@goalmate.local` / `goalmate-demo`
- `participant@goalmate.local` / `goalmate-participant`
- `organizer@goalmate.local` / `goalmate-organizer`

## Хранение данных

- локальная база: `data/goalmate.db`
- статика: `static/`
- сервер: `app.py`

## База данных

По умолчанию GoalMate работает на `SQLite`.

- локальный fallback: `DATABASE_URL=` пустой, используется `DATABASE_PATH`
- целевой online-режим: `DATABASE_URL=postgresql://...`

Сейчас `db`-слой уже распознаёт `PostgreSQL` и использует `psycopg`, но staging-переезд имеет смысл делать только после отдельной проверки с реальной Postgres-базой.

## Сброс демо

В интерфейсе есть кнопка `Сбросить демо`, она заново разворачивает seeded состояние базы.
