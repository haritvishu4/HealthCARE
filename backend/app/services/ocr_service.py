import io

from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool

from .provider import ServiceError, post_json


def classify(text):
    lower = text.lower()
    if any(x in lower for x in ("reference range", "haemoglobin", "hemoglobin", "laboratory")):
        return "lab_report"
    if any(x in lower for x in ("prescription", "rx:", "dosage")):
        return "prescription"
    return "medical_document"


def extract_pdf_text(file):
    try:
        reader = PdfReader(io.BytesIO(file))
        if reader.is_encrypted:
            raise ServiceError("OCR", "Password-protected PDFs are not supported.", 422)
        if len(reader.pages) > 20:
            raise ServiceError("OCR", "Use a PDF with at most 20 pages.", 422)
        page_text = []
        for page in reader.pages:
            content = page.get_contents()
            if content and len(content.get_data()) > 5 * 1024 * 1024:
                raise ServiceError("OCR", "PDF page content is too large.", 413)
            page_text.append((page.extract_text() or "").strip())
        # Do not silently omit image-only pages in a mixed document.
        if page_text and all(len(t) >= 30 for t in page_text):
            text = "\n\n".join(page_text)
            if len(text) > 32000:
                raise ServiceError("OCR", "Extracted text exceeds 32,000 characters.", 422)
            return {
                "text": text,
                "document_type": classify(text),
                "confidence": None,
                "provider": "pdf_text",
            }
    except ServiceError:
        raise
    except Exception:
        raise ServiceError(
            "OCR", "This PDF could not be read. Upload a valid PDF or image.", 422
        ) from None
    return None


async def extract_medical_text(file, *, settings, client, filename, content_type):
    """Extract text; scanned PDFs/images use OCR.space. Confidence is unknown, not invented."""
    if content_type == "application/pdf":
        native = await run_in_threadpool(extract_pdf_text, file)
        if native is not None:
            return native
    if not settings.ocr_api_key:
        raise ServiceError(
            "OCR", "Set OCR_API_KEY in backend/.env for scanned PDFs and images.", 503
        )
    result = await post_json(
        client,
        "OCR",
        "https://api.ocr.space/parse/image",
        headers={"apikey": settings.ocr_api_key},
        data={
            "language": settings.ocr_language,
            "isOverlayRequired": "false",
            "OCREngine": "2",
            "scale": "true",
        },
        files={"file": (filename, file, content_type)},
    )
    pages = result.get("ParsedResults") or []
    if (
        result.get("IsErroredOnProcessing")
        or not isinstance(pages, list)
        or not pages
        or any(
            not isinstance(p, dict)
            or p.get("FileParseExitCode") not in (1, "1")
            or not isinstance(p.get("ParsedText"), str)
            for p in pages
        )
    ):
        raise ServiceError(
            "OCR",
            "The OCR provider could not extract all pages. Check file quality and account limits.",
            422,
        )
    text = "\n\n".join(p.get("ParsedText", "") for p in pages).strip()
    if not text:
        raise ServiceError(
            "OCR", "No readable text was found. Clinical images are not diagnosed by OCR.", 422
        )
    if len(text) > 32000:
        raise ServiceError("OCR", "Extracted text exceeds 32,000 characters.", 422)
    return {
        "text": text,
        "document_type": classify(text),
        "confidence": None,
        "provider": "ocrspace",
    }
