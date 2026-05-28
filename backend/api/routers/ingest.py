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

from brd_module.storage import store_chunks
from storage import copy_session_chunks
from classifier import classify_chunks
from schema import ClassifiedChunk, SignalLabel

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

@router.post("/upload")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    source_type: str = Form("email")
):
    """
    DEMO MODE: Accepts and discards any uploaded file, then copies pre-classified
    chunks from DEMO_CACHE_SESSION_ID into this session — instant DB copy.
    """
    await file.read()  # discard — we never process the real file
    filename = file.filename or "uploaded_file"

    try:
        copied = copy_session_chunks(DEMO_CACHE_SESSION_ID, session_id)
        if copied > 0:
            return {
                "message": f"Upload complete. {copied} chunks classified and stored.",
                "chunk_count": copied,
                "filename": filename,
                "demo_mode": True,
            }
        raise HTTPException(
            status_code=503,
            detail="Demo cache is empty. Run the /demo endpoint first to seed it."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")



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


