import os
import time
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
        analyzed_clauses, safety, summary = analyze_document(clauses_text, doc_type, full_text)
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
    )

    return AnalysisResponse(meta=meta, safety=safety, clauses=analyzed_clauses, summary=summary)
