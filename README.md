# ClauseGuard

**Live at → [tryclauseguard.vercel.app](https://tryclauseguard.vercel.app)**

ClauseGuard reads leases and contracts so you don't have to decode them alone. Upload any PDF lease, rental agreement, employment contract, or NDA — and the app extracts every clause, explains it in plain English, assigns a risk level, and tells you exactly what to watch out for. High-risk clauses (automatic renewals, no-notice entry, unlimited liability, no-sublet) are flagged immediately. A safety score (0–100) summarizes the overall document risk at a glance.

The app is fully stateless: no account required, no documents stored. Your PDF is processed in memory and discarded after analysis. ClauseGuard runs on free-tier infrastructure (Groq for AI, Railway for backend, Vercel for frontend) and costs nothing to operate.

---

## Legal disclaimer

**ClauseGuard is not a law firm and does not provide legal advice.** All analysis is for informational and educational purposes only. Nothing in this application constitutes legal advice. Always consult a qualified attorney before making any legal decisions based on a contract or lease. ClauseGuard makes no warranties about the accuracy, completeness, or applicability of any analysis to your specific situation.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | [React 18](https://react.dev) + [TypeScript](https://www.typescriptlang.org) + [Vite](https://vitejs.dev) |
| Routing | [React Router v6](https://reactrouter.com) |
| Styling | Custom CSS with design tokens (no framework) |
| Backend | [FastAPI](https://fastapi.tiangolo.com) (Python 3.11) |
| PDF parsing | [pdfplumber](https://github.com/jsvine/pdfplumber) |
| AI | [Groq](https://groq.com) — Llama 3.3 70B (`llama-3.3-70b-versatile`) |
| Frontend hosting | [Vercel](https://vercel.com) |
| Backend hosting | [Railway](https://railway.app) |

---

## Local development

### Prerequisites
- Node.js 18+
- Python 3.11+
- A free [Groq API key](https://console.groq.com)

### 1. Clone the repo

```bash
git clone https://github.com/Hrishikesh-Codes/clauseguard.git
cd clauseguard
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the `backend/` directory:
```
GROQ_API_KEY=your_groq_api_key_here
FRONTEND_URL=http://localhost:5173
```

Start the backend:
```bash
uvicorn main:app --reload --port 8000
```

Test it:
```bash
curl http://localhost:8000/api/health
# → {"status":"ok"}
```

### 3. Frontend setup

```bash
cd ../frontend
npm install
```

Create a `.env.local` file in `frontend/`:
```
VITE_API_URL=http://localhost:8000
```

Start the dev server:
```bash
npm run dev
# → http://localhost:5173
```

---

## Deployment

### Backend → Railway

1. Push code to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. In service **Settings → Root Directory**, set it to `backend`
4. Add environment variables in Railway dashboard:
   - `GROQ_API_KEY` — your Groq API key
   - `FRONTEND_URL` — your Vercel URL (add after deploying frontend, then redeploy)
5. Railway assigns a public URL like `https://clauseguard-production.up.railway.app`

The `backend/railway.toml` and `backend/Procfile` handle the build and start commands automatically.

### Frontend → Vercel

1. Go to [vercel.com](https://vercel.com) → New Project → Import GitHub repo
2. Vercel reads `vercel.json` automatically (build from `frontend/`, output `frontend/dist`)
3. Add environment variable:
   - `VITE_API_URL` — your Railway backend URL
4. Deploy — Vercel assigns a URL (custom domain can be set in Vercel dashboard)

Both deployments trigger automatically on every `git push` to `main`.

---

## How clause analysis works

**Step 1 — PDF parsing** (`backend/parser.py`)  
pdfplumber extracts full text from every page. Scanned PDFs (no extractable text) and password-protected PDFs are detected early and return clear error messages. Max file size: 10 MB.

**Step 2 — Clause segmentation** (`backend/parser.py`)  
A regex-based two-pass algorithm identifies section headers (numbered items like `1. RENT`, all-caps titles, `ARTICLE`/`SECTION` prefixes) and splits the document into individual clauses. Falls back to paragraph splitting for unstructured documents.

**Step 3 — Batched AI analysis** (`backend/analyzer.py`)  
All extracted clauses are sent in a single call to Groq's Llama 3.3 70B model. Capped at 20 clauses, each truncated to 600 characters, to stay within Groq's free-tier TPM limits. The system prompt instructs the model to return structured JSON with: clause type, risk level (`high`/`medium`/`standard`/`favorable`), risk score (1–5), a plain-English explanation, and a verdict. One call per document.

**Step 4 — Safety scoring** (`backend/analyzer.py`)  
```
score = 100
score -= high_risk_count × 20
score -= medium_risk_count × 8
score += favorable_count × 5
score = clamp(0, 100)
```
Score ≥ 75 = green. Score 50–74 = amber. Score < 50 = red.

---

## What gets analyzed

- Residential leases
- Commercial leases
- Employment contracts
- NDAs
- Service agreements
- Purchase agreements
- Roommate agreements
- Sublease agreements

---

## Privacy

Your document is never stored. PDFs are processed in memory and discarded immediately after analysis. No account is required. The app is fully stateless on the backend.
