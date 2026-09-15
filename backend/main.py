import hashlib
import os
import time
from collections import OrderedDict
from typing import Optional, Tuple
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from models import AnalysisResponse, DocumentMeta, ErrorResponse
from parser import extract_text_from_pdf, segment_clauses, detect_doc_type, count_words
from analyzer import analyze_document

app = FastAPI(title="ClauseGuard API", version="1.0.0")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# ── Result cache ────────────────────────────────────────────────────────────────
# Groq allows only about 8000 tokens per minute and one analysis uses most of it,
# so re-uploading the same document would otherwise burn the whole allowance and
# rate-limit the next visitor. Keyed by a hash of the file bytes.
#
# Privacy: this holds ANALYSIS RESULTS ONLY, never the uploaded PDF, only in
# memory, capped and short-lived. Nothing is written to disk. Restarting the
# Space clears it.
CACHE_TTL_SECONDS = 900   # 15 minutes
CACHE_MAX_ENTRIES = 24

_cache: "OrderedDict[str, Tuple[float, AnalysisResponse]]" = OrderedDict()


def _cache_get(key: str) -> Optional[AnalysisResponse]:
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if time.time() - stored_at > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)   # least-recently-used ordering
    return value


def _cache_put(key: str, value: AnalysisResponse) -> None:
    _cache[key] = (time.time(), value)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(file: UploadFile = File(...)):
    # Validate content type
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        # Also check extension for browsers that may send wrong MIME
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail={"error": "Please upload a PDF file.", "code": "NOT_PDF"},
            )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={"error": "This file is too large. Please upload a PDF under 10MB.", "code": "TOO_LARGE"},
        )

    # An identical file re-uploaded within the TTL is served from memory, which
    # costs no tokens and leaves the rate limit free for other visitors.
    cache_key = hashlib.sha256(content).hexdigest()
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    start_ms = int(time.time() * 1000)

    try:
        full_text, page_count = extract_text_from_pdf(content)
    except ValueError as e:
        code = str(e)
        if code == "PASSWORD_PROTECTED":
            raise HTTPException(
                status_code=400,
                detail={"error": "This PDF is password protected. Please remove the password and try again.", "code": code},
            )
        if code == "SCANNED_PDF":
            raise HTTPException(
                status_code=400,
                detail={"error": "This PDF appears to be scanned. We can only analyze text-based PDFs for now.", "code": code},
            )
        raise HTTPException(status_code=400, detail={"error": str(e), "code": "PARSE_ERROR"})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to parse PDF. Please try another file.", "code": "PARSE_ERROR"},
        )

    doc_type = detect_doc_type(full_text)
    word_count = count_words(full_text)
    clauses_text = segment_clauses(full_text)

    if not clauses_text:
        raise HTTPException(
            status_code=400,
            detail={"error": "Could not extract any clauses from this document.", "code": "NO_CLAUSES"},
        )

    try:
        analyzed_clauses, safety, summary, n_analyzed = analyze_document(
            clauses_text, doc_type, full_text
        )
    except Exception as e:
        import traceback
        print("GROQ ERROR:", str(e))
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"error": "Analysis failed. Please try again in a moment.", "code": "GROQ_ERROR"},
        )

    end_ms = int(time.time() * 1000)
    elapsed = end_ms - start_ms

    meta = DocumentMeta(
        filename=file.filename or "document.pdf",
        page_count=page_count,
        word_count=word_count,
        doc_type=doc_type,
        analysis_time_ms=elapsed,
        clauses_found=len(clauses_text),
        clauses_analyzed=n_analyzed,
    )

    response = AnalysisResponse(
        meta=meta, safety=safety, clauses=analyzed_clauses, summary=summary
    )
    _cache_put(cache_key, response)
    return response
