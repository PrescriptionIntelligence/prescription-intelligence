# Prescription Intelligence

**AI-powered prescription intelligence and medication safety platform.**

A decision-support tool for pharmacists and healthcare professionals. Turns prescription images into structured, reviewed medicine data with confidence scoring, safety intelligence, and human-verification workflows built in.

---

## Product overview

Prescription Intelligence helps pharmacists and clinical staff turn prescription images into structured data:

1. **Upload** a prescription image (JPG/PNG)
2. **OCR** extracts text using multi-mode Tesseract with quality scoring
3. **Medicine candidates** are detected from prescription markers and strengths
4. **Normalization** matches candidates against a curated vocabulary with confidence scoring
5. **Safety analysis** checks duplicates, known interactions, dose anomalies, and structural issues
6. **Review** the result with full confidence information before dispensing

All uncertain identifications are explicitly flagged. The system never silently accepts a low-confidence medicine identity.

---

## Medical disclaimer

> Prescription Intelligence is a **decision-support tool only**. It is designed to assist qualified pharmacists and healthcare professionals — not replace them. All AI output must be verified by a qualified professional before any clinical action. The system explicitly flags uncertain identifications and safety concerns; these must be reviewed before dispensing.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Next.js)                     │
│   Landing · Sign-in/up · Dashboard · Analyze · History      │
│               Analysis Detail · Review                      │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/REST
┌────────────────────────▼────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  Auth · Prescriptions · Dashboard Stats · Medicine Lookup   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                 Prescription Pipeline                        │
│  OCR Service → Candidate Detection → Normalization          │
│  Dose Calculator → Validator → Safety Checker               │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              PostgreSQL + Alembic migrations                 │
│  organizations · users · prescriptions · medicines          │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

### Core pipeline
- **Image preprocessing** — grayscale, contrast enhancement, sharpening
- **Multi-mode OCR** — Tesseract PSM 3/4/6/11/12, best output selected by quality score
- **OCR quality assessment** — scored 0–100 with level (good/fair/poor/failed)
- **Medicine candidate detection** — marker-based (Tab/Cap/Inj) + strength pattern detection
- **Medicine normalization** — fuzzy vocabulary matching with confidence scores and ambiguity detection
- **Dose calculation** — daily dose = strength × dose × frequency; combination strengths supported
- **Structural validation** — missing name, strength, dose, frequency, invalid values
- **Safety intelligence**:
  - Duplicate medicine detection
  - Known drug-drug interactions (conservative, evidence-based list)
  - Low-confidence / ambiguous identification flags
  - Daily dose limit checks (Paracetamol, Ibuprofen, Cetirizine, Omeprazole, Metformin, Amoxicillin)

### Authentication
- JWT-based authentication (bcrypt passwords, HS256 tokens)
- Register with pharmacy/clinic name (creates Organization)
- Login returns token + user + organization

### API
- `GET /health` — health check
- `GET /dashboard/stats` — aggregate statistics
- `POST /prescriptions/upload` — upload + analyze prescription image
- `GET /prescriptions` — paginated history
- `GET /prescriptions/{id}` — analysis detail
- `GET /medicines/lookup?q=` — medicine name search
- `POST /auth/register` — create account
- `POST /auth/login` — authenticate
- `GET /users/me` — authenticated user profile
- `GET /uploads/{filename}` — serve prescription images

### Frontend pages
- `/` — Landing page
- `/sign-in` — Login
- `/sign-up` — Register
- `/forgot-password` — Password reset
- `/dashboard` — Dashboard with real stats from backend
- `/analyze` — Upload and analyze prescription
- `/analysis/[id]` — Analysis detail with medicines, safety, OCR
- `/history` — Paginated prescription history
- `/review` — Legacy review page

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy, Pydantic, Alembic |
| Database | PostgreSQL (psycopg v3) |
| OCR | Tesseract / pytesseract, Pillow |
| AI/ML | difflib fuzzy matching, curated vocabulary |
| Auth | python-jose (JWT), passlib (bcrypt) |
| Frontend | Next.js 16, TypeScript, Tailwind CSS v4 |

---

## Project structure

```
prescription-intelligence/
├── backend/
│   ├── main.py              # FastAPI app, all routes
│   ├── models.py            # SQLAlchemy ORM models
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── database.py          # DB connection + session
│   ├── auth.py              # JWT auth dependency
│   ├── security.py          # Password hashing + JWT utils
│   ├── routers/
│   │   ├── auth.py          # /auth/register, /auth/login
│   │   └── users.py         # /users/me
│   └── services/
│       ├── ocr_service.py   # Tesseract OCR + preprocessing
│       ├── prescription_pipeline.py  # Main pipeline orchestrator
│       ├── prescription_parser.py    # Medicine extraction from text
│       ├── medicine_normalizer.py    # Fuzzy vocab matching
│       ├── medicine_candidate_detector.py
│       ├── dose_calculator.py
│       ├── prescription_validator.py
│       ├── safety_checker.py
│       └── ...
├── frontend/
│   ├── app/
│   │   ├── page.tsx          # Landing
│   │   ├── sign-in/          # Login
│   │   ├── sign-up/          # Register
│   │   ├── dashboard/        # Dashboard
│   │   ├── analyze/          # Upload + analyze
│   │   ├── analysis/[id]/    # Analysis detail
│   │   ├── history/          # History
│   │   └── review/           # Legacy review
│   └── lib/
│       └── auth.ts           # Auth helpers + API calls
├── migrations/               # Alembic migrations
├── data/medicines/
│   └── medicine_vocabulary.csv
├── tests/
│   └── test_backend.py      # 49 unit tests
├── uploads/                 # Uploaded prescription images (gitignored)
└── .env                     # Environment variables (not committed)
```

---

## Environment variables

Create a `.env` file in the project root:

```env
# Database
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=prescription_intelligence

# Security — REQUIRED in production
SECRET_KEY=your-long-random-secret-key-here

# Optional
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Frontend (already configured in `frontend/.env.local`):

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

---

## Database setup

```bash
# Create database
createdb prescription_intelligence

# Run all migrations
alembic upgrade head
```

The migration chain:
1. `4b74d017f7dc` — Create prescriptions and medicines tables
2. `a9390d44a32c` — Add file metadata to prescriptions
3. `7f4ecab9d546` — Add daily dose fields to medicines
4. `e1a2b3c4d5e6` — Full schema v2 (organizations, users, customers, all missing columns)

---

## Backend setup

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# or: source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install fastapi uvicorn sqlalchemy alembic psycopg pillow pytesseract \
            python-jose passlib python-multipart python-dotenv pydantic[email]

# Run migrations
alembic upgrade head

# Start server
uvicorn backend.main:app --reload --port 8000
```

**Requires:** Tesseract OCR installed and in PATH.
- Windows: https://github.com/UB-Mannheim/tesseract/wiki
- Linux: `sudo apt install tesseract-ocr`

---

## Frontend setup

```bash
cd frontend
npm install
npm run dev  # Development server at http://localhost:3000
npm run build  # Production build
```

---

## Running

1. Start PostgreSQL
2. Run `alembic upgrade head`
3. Start backend: `uvicorn backend.main:app --reload`
4. Start frontend: `cd frontend && npm run dev`
5. Open http://localhost:3000

---

## API documentation

Interactive API docs available at:
- http://localhost:8000/docs (Swagger UI)
- http://localhost:8000/redoc (ReDoc)

---

## Testing

```bash
# Install pytest (if not already installed)
pip install pytest

# Run all tests
python -m pytest tests/test_backend.py -v
```

Test coverage:
- Duplicate medicine detection
- Drug interaction checks
- Ambiguous medicine flagging
- Daily dose limit checks
- Dose calculation (normal + combination strengths)
- Prescription structural validation
- OCR quality assessment
- Full pipeline (process_prescription)
- OCR text scoring

---

## Limitations and external dependencies

### OCR
- Requires Tesseract OCR to be installed separately
- Handwritten prescriptions with poor image quality will produce low-confidence results
- Non-Latin scripts are not supported

### Medicine vocabulary
- The medicine vocabulary is a curated CSV file (`data/medicines/medicine_vocabulary.csv`)
- It does not cover all medicines — unrecognized medicines receive "UNKNOWN" status
- Never invent medicine identities from noisy OCR text

### Safety data
- The drug interaction list is limited and conservative
- Daily dose limits are for commonly known medicines only
- This is **not** a replacement for authoritative drug databases (BNF, Micromedex, etc.)

### Authentication
- Password reset is not implemented (frontend placeholder only)
- No OAuth/SSO integration

### Image support
- JPG and PNG only (no PDF)
- Maximum 10 MB per file
