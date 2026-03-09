# GoalMate Demo

Локальная демка `GoalMate` для проверки основных сценариев:

- участник: задачи, мягкий возврат, отчёты, лидерборд, мини-команда
- организатор: дашборд, white-label, аналитика, no-code конструктор, дублирование программ
- growth: приватные челленджи друзей поверх B2B-потока

## Запуск

```bash
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

## Сброс демо

В интерфейсе есть кнопка `Сбросить демо`, она заново разворачивает seeded состояние базы.
