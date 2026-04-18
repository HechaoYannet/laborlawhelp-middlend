# Middlend Backend Scaffold

## 1. Install

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Run API

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 2.1 Runtime Modes

- `storage_backend=memory` (default): in-memory store for fast local integration.
- `storage_backend=postgres`: PostgreSQL + Redis mode.

Example `.env` for postgres mode:

```env
storage_backend=postgres
database_url=postgresql://postgres:postgres@127.0.0.1:5432/laborlawhelp
redis_url=redis://127.0.0.1:6379/0
oh_use_mock=true
auth_mode=anonymous
jwt_secret_key=change-me
```

Initialize schema:

```powershell
psql -d laborlawhelp -f .\sql\init_schema.sql
```

## 3. Run Tests

```powershell
pytest -q
```

## 3.1 JWT Phase-2 Switch

Set in `.env`:

```env
auth_mode=jwt
```

Auth endpoints:
- POST `/api/v1/auth/sms/send`
- POST `/api/v1/auth/sms/login`
- POST `/api/v1/auth/refresh`
- POST `/api/v1/auth/logout`

Use `Authorization: Bearer <access_token>` for protected endpoints when `auth_mode=jwt`.

## 4. Smoke Script

In another terminal:

```powershell
cd scripts
.\smoke-chat.ps1
```

## 5. Implemented Endpoints
- POST `/api/v1/cases`
- GET `/api/v1/cases`
- GET `/api/v1/cases/{case_id}`
- POST `/api/v1/cases/{case_id}/sessions`
- GET `/api/v1/cases/{case_id}/sessions`
- GET `/api/v1/sessions/{session_id}/messages`
- PATCH `/api/v1/sessions/{session_id}/end`
- POST `/api/v1/sessions/{session_id}/chat`
- POST `/api/v1/auth/sms/send`
- POST `/api/v1/auth/sms/login`
- POST `/api/v1/auth/refresh`
- POST `/api/v1/auth/logout`

## 6. Anonymous Migration Scripts

```powershell
python .\scripts\migrate_anonymous_to_user.py --database-url "postgresql://postgres:postgres@127.0.0.1:5432/laborlawhelp" --anonymous-id "anon-1" --user-id "00000000-0000-0000-0000-000000000001"
python .\scripts\rollback_anonymous_migration.py --database-url "postgresql://postgres:postgres@127.0.0.1:5432/laborlawhelp" --anonymous-id "anon-1" --user-id "00000000-0000-0000-0000-000000000001"
```
