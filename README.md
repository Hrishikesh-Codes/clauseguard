# ClauseGuard

ClauseGuard is a lease and contract plain-English explainer. Upload any PDF lease, rental agreement, employment contract, or NDA — and the app extracts every clause, explains it in plain English, assigns a risk level, and tells you exactly what to do about each one. High-risk clauses (automatic renewals, no-notice entry, unlimited liability) are flagged immediately. A safety score summarizes the overall document risk at a glance.

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
| Styling | Custom CSS (design tokens) + [Tailwind CSS](https://tailwindcss.com) (layout utilities) |
| Backend | [FastAPI](https://fastapi.tiangolo.com) (Python) |
| PDF parsing | [pdfplumber](https://github.com/jsvine/pdfplumber) |
| AI | [Groq](https://groq.com) — Llama 3.1 70B via OpenAI-compatible SDK |
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
git clone https://github.com/yourname/clauseguard.git
cd clauseguard
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env
cp ../.env.example .env
# Edit .env and add your GROQ_API_KEY
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

# Create .env.local
echo "VITE_API_URL=http://localhost:8000" > .env.local
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
3. Select the repo — Railway auto-detects the `backend/` directory via `railway.json`
4. Add environment variables in Railway dashboard:
   - `GROQ_API_KEY` — your Groq API key
   - `FRONTEND_URL` — your Vercel URL (add after deploying frontend, then redeploy)
5. Railway assigns a public URL like `https://clauseguard-production.up.railway.app`

### Frontend → Vercel

1. Go to [vercel.com](https://vercel.com) → New Project → Import GitHub repo
2. Vercel reads `vercel.json` automatically (build from `frontend/`, output `frontend/dist`)
3. Add environment variable:
   - `VITE_API_URL` — your Railway backend URL
4. Deploy — Vercel assigns `https://clauseguard.vercel.app` (or custom domain)

Both deployments trigger automatically on every `git push` to `main`.

---

## How clause analysis works

**Step 1 — PDF parsing** (`backend/parser.py`)  
pdfplumber extracts full text from every page. Scanned PDFs (no extractable text) and password-protected PDFs are detected early and return clear error messages.

**Step 2 — Clause segmentation** (`backend/parser.py`)  
A regex-based two-pass algorithm identifies section headers (numbered items like `1. RENT`, all-caps titles, `ARTICLE`/`SECTION` prefixes) and splits the document into individual clauses. Falls back to paragraph splitting for unstructured documents. Caps at 40 clauses to keep prompt size manageable.

**Step 3 — Batched AI analysis** (`backend/analyzer.py`)  
All extracted clauses are sent in a single call to Groq's Llama 3.1 70B model. The system prompt instructs the model to return structured JSON with: clause type, risk level (`high`/`medium`/`standard`/`favorable`), risk score (1–5), a plain-English explanation, a verdict, and an action prompt. One call per document — no per-clause calls.

**Step 4 — Safety scoring** (`backend/analyzer.py`, `frontend/src/utils/score.ts`)  
```
score = 100
score -= high_risk_count × 20
score -= medium_risk_count × 8
score += favorable_count × 5
score = clamp(0, 100)
```
Score < 50 = red. Score 50–74 = amber. Score ≥ 75 = green.

---

## Why Groq free tier is sufficient

Token math for a typical residential lease:
- Average lease length: ~5,000 words ≈ ~6,500 tokens input
- Analysis output (JSON for ~20 clauses): ~2,000 tokens
- **Total per analysis: ~8,500 tokens**

Groq free tier limits:
- `llama-3.1-70b-versatile`: 6,000 tokens/min, **14,400 requests/day**
- A single analysis uses ~8,500 tokens — fits in ~2 minutes of token budget
- At typical usage (1 analysis every few minutes), free tier is effectively unlimited

For high-traffic scenarios, Groq's paid tier starts at $0.59/million tokens input — a full analysis costs less than $0.01.

---

## LinkedIn post (copy-paste ready)

> Just shipped ClauseGuard — a free tool that reads your lease so you don't get surprised.
>
> Upload any PDF lease or contract and it:
> → Extracts every clause automatically
> → Explains each one in plain English (no legal jargon)
> → Flags high-risk clauses like automatic renewals, no-notice entry, and unlimited liability
> → Gives you a safety score and tells you exactly what to do
>
> Built with FastAPI, pdfplumber, Groq (Llama 3.1 70B), React + TypeScript, deployed on Railway + Vercel. Total infrastructure cost: $0.
>
> The wild part? Most leases have 3–5 high-risk clauses buried in standard-looking language. Most people sign them without realizing.
>
> Try it free at clauseguard.vercel.app — no account, no storage, no catch.
>
> #buildinpublic #webdev #legaltech #react #fastapi #groq
