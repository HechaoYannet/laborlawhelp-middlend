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

## 3. Run Tests

```powershell
pytest -q
```

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

Current scaffold uses in-memory storage for rapid integration. Swap to PostgreSQL/Redis repositories next.
