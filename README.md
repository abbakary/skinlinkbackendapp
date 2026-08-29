# SkinLink FastAPI Backend

REST API for the SkinLink tele-dermatology platform. Powers the **Village Clinic** Flutter app and can be wired to the Next.js web dashboard.

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

## Demo credentials (clinic app)

| Role | Email | Password |
|------|-------|----------|
| Clinician | `neema@mwanzahealth.org` | `clinic123` |
| Org admin | `amina@mwanzahealth.org` | `clinic123` |

## Key endpoints

- `POST /api/v1/auth/login` — JWT login
- `GET /api/v1/cases/dashboard` — mobile home stats
- `POST /api/v1/cases/submit-referral` — full referral submission
- `POST /api/v1/cases/upload-image` — lesion photo upload
- `GET/POST /api/v1/drafts` — offline draft sync

Data persists to `backend/data/skinlink_db.json`.

## Mobile app connection

- **Android emulator:** `http://10.0.2.2:8000`
- **iOS simulator:** `http://127.0.0.1:8000`
- **Physical device:** use your machine's LAN IP, e.g. `http://192.168.1.x:8000`
