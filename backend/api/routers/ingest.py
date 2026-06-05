import os
import sys
import csv
import io
import re
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from typing import List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, "Noise filter module"))
sys.path.append(os.path.join(PROJECT_ROOT, "integration_module"))

from brd_module.storage import store_chunks
from storage import copy_session_chunks
from classifier import classify_chunks
from schema import ClassifiedChunk, SignalLabel
import pdf

# Session ID of the pre-classified 300-email Enron demo cache
DEMO_CACHE_SESSION_ID = os.environ.get("DEMO_CACHE_SESSION_ID", "default_session")

router = APIRouter(
    prefix="/sessions/{session_id}/ingest",
    tags=["Ingestion"]
)

class RawDataChunk(BaseModel):
    source_type: str
    source_ref: str
    speaker: str = "Unknown"
    text: str

class IngestRequest(BaseModel):
    chunks: List[RawDataChunk]


def _fallback_label_for_text(text: str) -> SignalLabel:
    lower = (text or "").lower()
    tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{1,}", lower))

    if tokens & {"decided", "approved", "finalized", "selected", "agreed"}:
        return SignalLabel.DECISION
    if tokens & {"deadline", "milestone", "launch", "rollout", "delivery", "phase", "golive", "go-live"}:
        return SignalLabel.TIMELINE_REFERENCE
    if tokens & {"feedback", "prefer", "concern", "issue", "friction", "request", "suggest"}:
        return SignalLabel.STAKEHOLDER_FEEDBACK
    if tokens & {"must", "should", "need", "needs", "require", "required", "shall", "support", "enable", "allow"}:
        return SignalLabel.REQUIREMENT
    return SignalLabel.NOISE

def _load_api_key():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, "Noise filter module", ".env"), override=False)
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)
    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_CLOUD_API")
    if api_key and not os.environ.get("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = api_key
    return api_key

def _process_and_store(sess_id: str, chunk_dicts: list):
    """Core classify + store logic shared by both ingest endpoints."""
    api_key = _load_api_key()
    try:
        classified = classify_chunks(chunk_dicts, api_key=api_key)
    except Exception:
        # Keep ingestion functional for local/test runs without LLM credentials.
        classified = []
        for raw in chunk_dicts:
            text = (raw.get("cleaned_text") or "").strip()
            label = _fallback_label_for_text(text)
            classified.append(
                ClassifiedChunk(
                    session_id=sess_id,
                    source_type=raw.get("source_type", "file"),
                    source_ref=raw.get("source_ref", "unknown"),
                    speaker=raw.get("speaker", "Unknown"),
                    raw_text=text,
                    cleaned_text=text,
                    label=label,
                    confidence=0.6,
                    reasoning="Fallback local keyword classification (LLM unavailable).",
                    flagged_for_review=True,
                )
            )
    for c in classified:
        c.session_id = sess_id
    store_chunks(classified)

@router.post("/data")
def ingest_data(session_id: str, request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Receives raw data chunks (JSON) from external connectors (e.g. Slack ingestion script).
    Routes them through noise classification in the background.
    """
    chunk_dicts = [
        {
            "cleaned_text": rc.text,
            "source_ref": rc.source_ref,
            "speaker": rc.speaker,
            "source_type": rc.source_type
        } for rc in request.chunks
    ]
    background_tasks.add_task(_process_and_store, session_id, chunk_dicts)
    return {"message": f"Processing {len(request.chunks)} chunks in the background for session {session_id}."}

def _extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    """Extract plain text from uploaded file bytes based on extension."""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()

    if ext == "pdf":
        return pdf.extract_text_from_pdf_bytes(file_bytes)

    if ext == "docx":
        return pdf.extract_text_from_docx_bytes(file_bytes)

    if ext == "csv":
        # Decode CSV and concatenate all cell values into one text blob
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text = file_bytes.decode("latin-1", errors="ignore")
        reader = csv.reader(io.StringIO(text))
        rows = []
        for row in reader:
            rows.append(" ".join(row))
        return "\n".join(rows)

    # Default: treat as plain text (.txt, .md, .log, etc.)
    try:
        return file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return file_bytes.decode("latin-1", errors="ignore")


def _chunk_text(text: str, filename: str, source_type: str) -> list:
    """
    Split text into ~1500-char chunks at paragraph/sentence boundaries.
    Returns list of dicts in the format expected by classify_chunks().
    """
    chunks = []

    # Split on double newlines (paragraphs), or single newlines if no doubles
    paragraphs = re.split(r"\n\s*\n", text.strip())
    if len(paragraphs) <= 1:
        paragraphs = text.strip().split("\n")

    current_buf = ""
    chunk_idx = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph would exceed 1500 chars, flush the buffer first
        if current_buf and len(current_buf) + len(para) + 2 > 1500:
            chunks.append({
                "cleaned_text": current_buf.strip(),
                "source_ref": f"file:{filename}:chunk{chunk_idx}",
                "speaker": "Unknown",
                "source_type": source_type,
            })
            chunk_idx += 1
            current_buf = ""

        # If a single paragraph is > 1500 chars, split on sentences
        if len(para) > 1500:
            if current_buf:
                chunks.append({
                    "cleaned_text": current_buf.strip(),
                    "source_ref": f"file:{filename}:chunk{chunk_idx}",
                    "speaker": "Unknown",
                    "source_type": source_type,
                })
                chunk_idx += 1
                current_buf = ""

            sentences = re.split(r"(?<=[.!?])\s+", para)
            sentence_buf = ""
            for sent in sentences:
                if sentence_buf and len(sentence_buf) + len(sent) + 1 > 1500:
                    chunks.append({
                        "cleaned_text": sentence_buf.strip(),
                        "source_ref": f"file:{filename}:chunk{chunk_idx}",
                        "speaker": "Unknown",
                        "source_type": source_type,
                    })
                    chunk_idx += 1
                    sentence_buf = ""
                sentence_buf += (" " if sentence_buf else "") + sent

            if sentence_buf:
                current_buf = sentence_buf
            continue

        # Normal case: append paragraph to buffer
        current_buf += ("\n\n" if current_buf else "") + para

    # Flush remaining buffer
    if current_buf.strip():
        chunks.append({
            "cleaned_text": current_buf.strip(),
            "source_ref": f"file:{filename}:chunk{chunk_idx}",
            "speaker": "Unknown",
            "source_type": source_type,
        })

    return chunks


@router.post("/upload")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    source_type: str = Form("file")
):
    """
    Real file upload: extracts text from the uploaded file, classifies it
    through the noise filter pipeline, and stores chunks in the session.
    Supports .txt, .csv, .pdf, .docx.
    """
    filename = file.filename or "uploaded_file"
    file_bytes = await file.read()

    # 1. Extract text
    text = _extract_text_from_file(filename, file_bytes)
    if not text or len(text.strip()) < 15:
        raise HTTPException(
            status_code=400,
            detail=f"File '{filename}' contains no usable text (too short or empty)."
        )

    # 2. Chunk the text
    chunk_dicts = _chunk_text(text, filename, source_type)
    if not chunk_dicts:
        raise HTTPException(
            status_code=400,
            detail=f"File '{filename}' produced no classifiable chunks."
        )

    # 3. Classify via LLM pipeline (same as Slack / Gmail)
    api_key = _load_api_key()
    try:
        classified = classify_chunks(chunk_dicts, api_key=api_key)
    except Exception:
        # Fallback to heuristic labels when LLM is unavailable
        classified = []
        for raw in chunk_dicts:
            raw_text = (raw.get("cleaned_text") or "").strip()
            label = _fallback_label_for_text(raw_text)
            classified.append(
                ClassifiedChunk(
                    session_id=session_id,
                    source_type=raw.get("source_type", "file"),
                    source_ref=raw.get("source_ref", f"file:{filename}"),
                    speaker=raw.get("speaker", "Unknown"),
                    raw_text=raw_text,
                    cleaned_text=raw_text,
                    label=label,
                    confidence=0.6,
                    reasoning="Fallback local keyword classification (LLM unavailable).",
                    flagged_for_review=True,
                )
            )

    # 4. Set session_id on every chunk and store
    for c in classified:
        c.session_id = session_id
    store_chunks(classified)

    return {
        "message": f"Upload complete. {len(classified)} chunks classified and stored.",
        "chunk_count": len(classified),
        "filename": filename,
    }


@router.post("/upload-ocr")
async def upload_file_ocr(
    session_id: str,
    file: UploadFile = File(...),
):
    """
    OCR upload endpoint — accepts PDFs and images, extracts text via OCR,
    then classifies and stores chunks into the session.

    NOTE: This is a placeholder. The actual OCR integration (Tesseract, cloud
    OCR, etc.) will be wired in later. For now, for PDFs it falls back to
    PyMuPDF text extraction; for images it returns an error prompting the
    user to paste text manually or wait for OCR integration.
    """
    filename = file.filename or "uploaded_file"
    file_bytes = await file.read()
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()

    # For PDFs, fall back to PyMuPDF text extraction (works for text-based PDFs)
    if ext == "pdf":
        text = pdf.extract_text_from_pdf_bytes(file_bytes)
        if not text or len(text.strip()) < 15:
            raise HTTPException(
                status_code=400,
                detail=f"PDF '{filename}' contains no extractable text. "
                       "Scanned PDFs require OCR which is coming soon. "
                       "Please use a text-based PDF or paste the text directly."
            )
        chunk_dicts = _chunk_text(text, filename, "pdf")
        if not chunk_dicts:
            raise HTTPException(status_code=400, detail="No classifiable chunks produced from PDF.")

        api_key = _load_api_key()
        try:
            classified = classify_chunks(chunk_dicts, api_key=api_key)
        except Exception:
            classified = _heuristic_classify_fallback(chunk_dicts, session_id, "pdf", filename)

        for c in classified:
            c.session_id = session_id
        store_chunks(classified)

        return {
            "message": f"PDF processed. {len(classified)} chunks classified and stored.",
            "chunk_count": len(classified),
            "filename": filename,
        }

    # For images — OCR not yet integrated
    image_exts = {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "webp"}
    if ext in image_exts:
        raise HTTPException(
            status_code=501,
            detail=f"OCR for image files ({ext.upper()}) is not yet integrated. "
                   "Please paste the text from this image manually, or wait for OCR support."
        )

    # Unknown file type
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type '.{ext}' for OCR upload. "
               "Supported: PDF, PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP."
    )


def _heuristic_classify_fallback(chunk_dicts: list, session_id: str, source_type: str, filename: str) -> list:
    """Fallback heuristic classification when LLM is unavailable."""
    classified = []
    for raw in chunk_dicts:
        raw_text = (raw.get("cleaned_text") or "").strip()
        label = _fallback_label_for_text(raw_text)
        classified.append(
            ClassifiedChunk(
                session_id=session_id,
                source_type=source_type,
                source_ref=raw.get("source_ref", f"file:{filename}"),
                speaker=raw.get("speaker", "Unknown"),
                raw_text=raw_text,
                cleaned_text=raw_text,
                label=label,
                confidence=0.6,
                reasoning="Fallback local keyword classification (LLM unavailable).",
                flagged_for_review=True,
            )
        )
    return classified


@router.post("/demo")
async def ingest_demo_dataset(session_id: str, limit: int = 80):
    """
    Streaming: returns text/plain lines live via StreamingResponse.
    Watch with:  curl -N -X POST <url>
    """
    import csv as _csv
    import re as _re
    import queue as _queue
    import threading as _threading
    from fastapi.responses import StreamingResponse

    emails_path = os.path.join(
        PROJECT_ROOT, "Noise filter module", "emails.csv"
    )

    def _parse_email(raw: str):
        sender, subject, body_lines, in_body = "Unknown", "", [], False
        for line in raw.splitlines():
            if not in_body:
                if line.strip() == "": in_body = True
                elif line.lower().startswith("from:"): sender = line[5:].strip()
                elif line.lower().startswith("subject:"): subject = line[8:].strip()
            else:
                body_lines.append(line)
        body = _re.sub(r"\s+", " ", " ".join(body_lines).strip())
        return sender, subject, body

    log_q: _queue.Queue = _queue.Queue()
    DONE = object()

    def run_pipeline():
        def log(msg): log_q.put(msg + "\n")

        log(f"[DEMO INGEST] ▶  Reading up to {limit} emails from Enron dataset...")
        chunk_dicts = []
        if os.path.exists(emails_path):
            try:
                with open(emails_path, "r", encoding="utf-8", errors="ignore") as f:
                    reader = _csv.DictReader(f)
                    for i, row in enumerate(reader):
                        if i >= limit:
                            break
                        sender, subject, body = _parse_email(row.get("message", ""))
                        text = f"{subject} {body}".strip() if subject else body
                        if len(text) < 20:
                            continue
                        chunk_dicts.append({
                            "cleaned_text": text[:1500],
                            "source_ref": row.get("file", f"enron:row{i}"),
                            "speaker": sender,
                            "source_type": "email",
                        })
                        if (i + 1) % 50 == 0:
                            log(f"[DEMO INGEST]   Parsed {i+1}/{limit} rows — {len(chunk_dicts)} valid chunks so far")
            except Exception as e:
                log(f"[DEMO INGEST] ❌ Parse error: {e}")
                log_q.put(DONE)
                return
        else:
            log(f"[DEMO INGEST] ⚠  Dataset file missing at {emails_path}")
            log("[DEMO INGEST]    Falling back to built-in synthetic demo signals.")
            synthetic_rows = [
                ("PM", "Requirement", "The platform must support SSO authentication for all employees."),
                ("Security", "Decision", "MFA is mandatory for admin users before launch."),
                ("Finance", "Timeline", "The MVP launch target is Q3 with phased rollout in Q4."),
                ("Support", "Feedback", "Users asked for markdown and docx export options."),
                ("Engineering", "NFR", "API latency must remain below 200ms at p95."),
                ("Ops", "Assumption", "PostgreSQL remains the primary transactional database."),
                ("Stakeholder", "Metric", "Reduce onboarding drop-off by 30 percent."),
            ]
            for i in range(limit):
                speaker, subject, body = synthetic_rows[i % len(synthetic_rows)]
                chunk_dicts.append({
                    "cleaned_text": f"{subject}: {body}",
                    "source_ref": f"synthetic:row{i}",
                    "speaker": speaker,
                    "source_type": "email",
                })

        log(f"[DEMO INGEST] ✔  Parsed {len(chunk_dicts)} chunks — starting classification...")
        log(f"[DEMO INGEST]    Heuristic filter → Domain gate → Groq LLM (Llama 4 Maverick)")
        log(f"[DEMO INGEST] {'─'*60}")

        if not chunk_dicts:
            log("[DEMO INGEST] ❌ No usable email bodies found."); log_q.put(DONE); return

        try:
            api_key = _load_api_key()
            classified = classify_chunks(chunk_dicts, api_key=api_key, log_fn=log)
            for c in classified:
                c.session_id = session_id
            store_chunks(classified)
            log(f"[DEMO INGEST] {'─'*60}")
            log(f"[DEMO INGEST] ✅ Complete! {len(classified)} chunks stored for session '{session_id}'.")
        except Exception as e:
            log(f"[DEMO INGEST] ⚠  Classification error: {e}")
            log("[DEMO INGEST]    Falling back to local heuristic classification.")
            fallback_classified = []
            for raw in chunk_dicts:
                text = (raw.get("cleaned_text") or "").strip()
                label = _fallback_label_for_text(text)
                fallback_classified.append(
                    ClassifiedChunk(
                        session_id=session_id,
                        source_type=raw.get("source_type", "email"),
                        source_ref=raw.get("source_ref", "synthetic"),
                        speaker=raw.get("speaker", "Unknown"),
                        raw_text=text,
                        cleaned_text=text,
                        label=label,
                        confidence=0.6,
                        reasoning="Fallback local keyword classification (LLM unavailable).",
                        flagged_for_review=True,
                    )
                )

            store_chunks(fallback_classified)
            log(f"[DEMO INGEST] {'─'*60}")
            log(f"[DEMO INGEST] ✅ Complete! {len(fallback_classified)} chunks stored for session '{session_id}' (fallback mode).")

        log_q.put(DONE)

    _threading.Thread(target=run_pipeline, daemon=True).start()

    async def stream():
        import asyncio
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, log_q.get)
            if item is DONE:
                break
            yield item

    return StreamingResponse(stream(), media_type="text/plain",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


