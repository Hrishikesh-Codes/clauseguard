import re
import io
from typing import List, Tuple


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, int]:
    """Extract text and page count from PDF bytes. Returns (text, page_count)."""
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber not installed")

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if pdf.metadata.get("Encrypt"):
                raise ValueError("PASSWORD_PROTECTED")

            page_count = len(pdf.pages)
            pages_text = []

            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

            full_text = "\n\n".join(pages_text)

            if not full_text.strip():
                raise ValueError("SCANNED_PDF")

            return full_text, page_count

    except ValueError:
        raise
    except Exception as e:
        if "password" in str(e).lower() or "encrypt" in str(e).lower():
            raise ValueError("PASSWORD_PROTECTED")
        raise RuntimeError(f"PDF_PARSE_ERROR: {str(e)}")


SECTION_HEADER_PATTERNS = [
    r"^\s*(\d+\.)\s+([A-Z][A-Z\s]{3,})\s*$",
    r"^\s*([A-Z][A-Z\s]{5,})\s*$",
    r"^\s*(\d+\.\d+\.?)\s+(.+?)\s*$",
    r"^\s*(ARTICLE\s+[IVX\d]+[.:]\s*.+?)\s*$",
    r"^\s*(SECTION\s+\d+[.:]\s*.+?)\s*$",
    r"^\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\n",
]

LEASE_SECTION_KEYWORDS = [
    "rent", "deposit", "security", "term", "termination", "renewal", "subletting",
    "sublease", "pets", "utilities", "maintenance", "repairs", "entry", "access",
    "notice", "liability", "indemnification", "alterations", "modifications",
    "parking", "storage", "noise", "quiet enjoyment", "insurance", "holding over",
    "default", "remedies", "governing law", "entire agreement", "late fees",
    "early termination", "move-in", "move-out", "inspection", "keys",
    "appliances", "hvac", "smoking", "guests", "occupants", "assignment"
]


def segment_clauses(text: str) -> List[str]:
    """Split document text into individual clauses/sections."""
    lines = text.split("\n")
    clauses: List[str] = []
    current_clause: List[str] = []
    current_header = ""

    def flush():
        nonlocal current_header
        if current_clause:
            combined = " ".join(" ".join(current_clause).split())
            if len(combined.strip()) > 50:
                clauses.append(combined.strip())
        current_clause.clear()
        current_header = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        is_header = False

        # Numbered section like "1. RENT" or "2.3 Late Fees"
        if re.match(r"^\d+\.(\d+\.?)?\s+[A-Z]", stripped):
            is_header = True
        # All-caps line likely a section title
        elif re.match(r"^[A-Z\s]{6,}$", stripped) and len(stripped) < 60:
            is_header = True
        # "Article" / "Section" prefix
        elif re.match(r"^(ARTICLE|SECTION|CLAUSE)\s+", stripped, re.IGNORECASE):
            is_header = True
        # Mixed-case header matching common lease terms
        elif any(kw in stripped.lower() for kw in LEASE_SECTION_KEYWORDS) and len(stripped) < 80 and stripped.endswith(":"):
            is_header = True

        if is_header and current_clause:
            flush()
            current_header = stripped
            current_clause.append(stripped)
        else:
            current_clause.append(stripped)

    flush()

    # If we got very few clauses, fall back to paragraph splitting
    if len(clauses) < 3:
        clauses = split_by_paragraphs(text)

    # Cap to 40 clauses max to keep prompt size manageable
    return clauses[:40]


def split_by_paragraphs(text: str) -> List[str]:
    """Fallback: split by double newlines and keep substantial paragraphs."""
    paragraphs = re.split(r"\n{2,}", text)
    result = []
    for p in paragraphs:
        cleaned = " ".join(p.split())
        if len(cleaned) > 100:
            result.append(cleaned)
    return result[:40]


def detect_doc_type(text: str) -> str:
    """Detect what kind of document this is."""
    text_lower = text.lower()

    counts = {
        "Residential Lease": sum(1 for kw in ["lease agreement", "tenant", "landlord", "rent", "premises", "dwelling"] if kw in text_lower),
        "Commercial Lease": sum(1 for kw in ["commercial lease", "lessee", "lessor", "tenant", "commercial property", "square feet"] if kw in text_lower),
        "Employment Contract": sum(1 for kw in ["employment", "employee", "employer", "salary", "termination", "non-compete"] if kw in text_lower),
        "Service Agreement": sum(1 for kw in ["service agreement", "client", "contractor", "services", "deliverables", "scope of work"] if kw in text_lower),
        "NDA": sum(1 for kw in ["non-disclosure", "confidential", "proprietary", "nda", "trade secret"] if kw in text_lower),
        "Purchase Agreement": sum(1 for kw in ["purchase", "buyer", "seller", "closing", "title", "escrow"] if kw in text_lower),
    }

    best = max(counts, key=lambda k: counts[k])
    if counts[best] >= 2:
        return best
    return "Legal Document"


def count_words(text: str) -> int:
    return len(text.split())
