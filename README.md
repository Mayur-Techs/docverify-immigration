# DocVerify AI — Immigration Document Intelligence

AI-powered extraction engine for immigration documents. Built for law firms handling I-129, I-140, I-485, passports, L-1 petitions, DS-160 and more.

## Stack
- **Backend**: FastAPI + Python 3.12
- **AI**: Groq LLaMA 3.3-70B (primary) → LLaMA 3.1-8B (fallback)
- **PDF parsing**: pdfplumber (primary) → pymupdf (fallback)
- **Database**: PostgreSQL + SQLAlchemy + Alembic
- **Auth**: JWT (python-jose + passlib bcrypt)
- **Frontend**: React 18 + Vite + Zustand
- **Infra**: Docker Compose, GitHub Actions CI/CD, Nginx

## Confidence Routing
| Score | Outcome |
|-------|---------|
| ≥ 90% | Auto-verified, no action needed |
| 75–89% | Completed, fields flagged for spot-check |
| < 75% | Routed to HITL queue — human review required |

## Quick Start

### 1. Clone and configure
```bash
git clone https://github.com/Mayur-Techs/docverify-immigration
cd docverify-immigration
cp backend/.env.example backend/.env
# Edit backend/.env — add your GROQ_API_KEY and SECRET_KEY
```

### 2. Run with Docker (recommended)
```bash
docker compose up -d
# API: http://localhost:8001
# Frontend: http://localhost:3000
# API docs: http://localhost:8001/docs
```

### 3. Run locally (dev)
```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8001

# Frontend (new terminal)
cd frontend
npm install
npm run dev
# http://localhost:5173
```

### 4. Database migrations
```bash
cd backend
alembic upgrade head
```

### 5. Run tests
```bash
cd backend
pytest tests/ -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/signup` | Create account |
| POST | `/api/v1/auth/login` | Login (returns JWT) |
| GET | `/api/v1/auth/me` | Current user |
| POST | `/api/v1/documents/upload` | Upload PDF |
| POST | `/api/v1/documents/batch/upload` | Upload up to 20 PDFs |
| GET | `/api/v1/documents/` | List documents |
| GET | `/api/v1/documents/stats/summary` | Dashboard stats |
| GET | `/api/v1/documents/search?q=` | Search documents |
| GET | `/api/v1/documents/export` | Export CSV |
| GET | `/api/v1/documents/{id}` | Document detail |
| GET | `/api/v1/documents/{id}/fields` | All extracted fields |
| PATCH | `/api/v1/documents/{id}/fields/{fid}/verify` | Verify / correct field |
| POST | `/api/v1/documents/{id}/reprocess` | Re-run extraction |
| DELETE | `/api/v1/documents/{id}` | Delete document |
| GET | `/api/v1/documents/hitl/queue` | HITL review queue |
| POST | `/api/v1/documents/hitl/{id}/resolve` | Resolve HITL item |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Get free at console.groq.com |
| `SECRET_KEY` | 64-char random string for JWT signing |
| `DATABASE_URL` | PostgreSQL connection string |
| `CONFIDENCE_HITL_THRESHOLD` | Below this → HITL queue (default: 75) |
| `CONFIDENCE_REVIEW_THRESHOLD` | Below this → flag for review (default: 90) |

## Getting a Groq API Key (Free)
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up → API Keys → Create Key
3. Paste into `backend/.env` as `GROQ_API_KEY`

Groq's free tier gives you 14,400 requests/day on LLaMA 3.3-70B.

## Deployment (Render)
1. Push to GitHub
2. Create a new Web Service on [render.com](https://render.com)
3. Connect your repo
4. Set build command: `pip install -r backend/requirements.txt`
5. Set start command: `cd backend && uvicorn app:app --host 0.0.0.0 --port $PORT`
6. Add all environment variables from `.env.example`
7. Add a PostgreSQL database from Render's dashboard

---
Built by [Mayur Nikumbh](https://github.com/Mayur-Techs)
