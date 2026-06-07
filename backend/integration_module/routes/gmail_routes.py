import os
import re
import sys
import secrets
import time
import threading
import hashlib
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Request, HTTPException, Response, Query  # type: ignore
from fastapi.responses import RedirectResponse  # type: ignore
from google_auth_oauthlib.flow import Flow  # type: ignore
from google.oauth2.credentials import Credentials  # type: ignore
from pydantic import BaseModel  # type: ignore

# Add parent directories to sys.path if needed
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
NOISE_FILTER_PATH = os.path.join(PROJECT_ROOT, "Noise filter module")
if NOISE_FILTER_PATH not in sys.path:
    sys.path.append(NOISE_FILTER_PATH)

from .. import gmail  # type: ignore
from .. import pdf  # type: ignore
from ..state import user_credentials  # type: ignore
from brd_module.storage import store_chunks  # type: ignore
from classifier import classify_chunks  # type: ignore
from schema import ClassifiedChunk, SignalLabel  # type: ignore

import google.auth.exceptions  # type: ignore
from google.auth.transport.requests import Request as AuthRequest  # type: ignore

router = APIRouter(prefix="/integrations/gmail", tags=["Gmail Integration"])

# Relax token scope requirement to avoid "Scope has changed" errors
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# Configuration
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "")
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]
OAUTH_STATE_TTL_SECONDS = 10 * 60
_oauth_states = {}


def _clean_stale_states():
    now = time.time()
    stale = [
        key for key, created in _oauth_states.items() 
        if now - (created['timestamp'] if isinstance(created, dict) else created) > OAUTH_STATE_TTL_SECONDS
    ]
    for key in stale:
        _oauth_states.pop(key, None)

def _get_uid_from_request(request: Request):
    uid = request.headers.get("X-User-UID")
    if not uid:
        uid = request.query_params.get("uid")
    return uid

_user_request_log = {}  # uid -> [timestamp, timestamp, ...]

def _check_rate_limit(uid: str, max_requests: int = 15, period: int = 60):
    """
    Simple in-memory Rate Limiter. 
    Allows max_requests in a rolling 'period' (seconds) window.
    """
    if not uid:
        return True  # If no UID, we skip for now (or track by IP)
        
    now = time.time()
    if uid not in _user_request_log:
        _user_request_log[uid] = []
    history = _user_request_log[uid]
    
    # Filter out requests that are older than the time window
    updated_history = [t for t in history if now - t < period]
    _user_request_log[uid] = updated_history
    
    if len(updated_history) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again after a minute.")
        
    _user_request_log[uid].append(now)
    return True

def _get_redirect_uri():
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if redirect_uri:
        normalized = redirect_uri.strip().rstrip("/")
        # Auto-migrate stale legacy callback paths to the active API callback route.
        if normalized.endswith("/gmail/oauth_redirect"):
            backend_public_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")
            return f"{backend_public_url}/integrations/gmail/auth/callback"
        return normalized

    backend_public_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return f"{backend_public_url}/integrations/gmail/auth/callback"

def _get_frontend_profile_url():
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{frontend_url}/profile"


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

class GmailIngestRequest(BaseModel):
    session_id: str
    message_ids: List[str]
    include_attachments: bool = True


def _get_google_client_config(redirect_uri: str):
    web = {
        "client_id": CLIENT_ID,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": CLIENT_SECRET,
        "redirect_uris": [redirect_uri],
    }
    if GOOGLE_PROJECT_ID:
        web["project_id"] = GOOGLE_PROJECT_ID
    return {"web": web}

@router.get("/auth/start")
def gmail_login(request: Request):
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google credentials not configured in .env")
    
    uid = _get_uid_from_request(request)
    if not uid:
        raise HTTPException(status_code=400, detail="Missing user UID for authentication.")
        
    redirect_uri = _get_redirect_uri()
    client_config = _get_google_client_config(redirect_uri)
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    
    _clean_stale_states()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    # Save the code verifier, timestamp and UID
    _oauth_states[state] = {
        'timestamp': time.time(),
        'code_verifier': getattr(flow, 'code_verifier', None),
        'uid': uid
    }
    
    return RedirectResponse(authorization_url)

def _get_credentials(uid: str):
    if not uid:
        raise HTTPException(status_code=401, detail="User ID is missing on arequest.")
        
    creds_data = user_credentials.get(uid)
    if not creds_data:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    
    creds = Credentials(**creds_data)
    
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(AuthRequest())
                # Update store
                user_credentials[uid].update({
                    "token": creds.token,
                    "refresh_token": creds.refresh_token
                })
            except google.auth.exceptions.RefreshError as e:
                del user_credentials[uid]
                raise HTTPException(status_code=401, detail=f"Session expired: {str(e)}")
        else:
            raise HTTPException(status_code=401, detail="Session expired and no refresh token available.")
            
    return creds

@router.get("/auth/callback")
def gmail_oauth_redirect(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    frontend_profile = _get_frontend_profile_url()
    
    if not code or not state:
        return RedirectResponse(f"{frontend_profile}?gmail=error&reason=missing_code_or_state")

    _clean_stale_states()
    if state not in _oauth_states:
        return RedirectResponse(f"{frontend_profile}?gmail=error&reason=invalid_state")
    state_data = _oauth_states.pop(state, None)
    
    redirect_uri = _get_redirect_uri()
    client_config = _get_google_client_config(redirect_uri)
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    
    # Inject the saved code_verifier
    uid = None
    if isinstance(state_data, dict):
        if state_data.get('code_verifier'):
            flow.code_verifier = state_data['code_verifier']
        uid = state_data.get('uid')
        
    if not uid:
        return RedirectResponse(f"{frontend_profile}?gmail=error&reason=missing_uid_state")
    
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        message = quote(str(e), safe="")
        return RedirectResponse(f"{frontend_profile}?gmail=error&reason={message}")
    
    credentials = flow.credentials
    user_credentials[uid] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes
    }
    
    return RedirectResponse(f"{frontend_profile}?gmail=connected")

@router.get("/status")
def gmail_status(request: Request):
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=40)  # Status can be polished often
    creds_data = user_credentials.get(uid) if uid else None
    connected = bool(creds_data)
    available = bool(CLIENT_ID and CLIENT_SECRET)
    
    message = "Gmail is connected." if connected else "Gmail is available but not connected."
    if not available:
        message = "Gmail API is not configured on this backend."
        
    return {
        "available": available,
        "connected": connected,
        "message": message
    }

@router.post("/disconnect")
def gmail_disconnect(request: Request):
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=5)
    if uid and uid in user_credentials:
        del user_credentials[uid]
    return {"message": "Gmail disconnected."}

@router.get("/profile")
def gmail_profile(request: Request):
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=15)
    credentials = _get_credentials(uid)
    try:
        from googleapiclient.discovery import build  # type: ignore
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = gmail.execute_with_retry(service.userinfo().get())
        return {
            "name": user_info.get("name"),
            "email": user_info.get("email"),
            "picture": user_info.get("picture")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/labels")
def gmail_labels(request: Request):
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=15)
    credentials = _get_credentials(uid)
    try:
        service = gmail.get_gmail_service(credentials)
        results = gmail.execute_with_retry(service.users().labels().list(userId='me'))
        labels = results.get('labels', [])
        
        filtered_labels = []
        for l in labels:
            if l.get('type') == 'user' and l.get('labelListVisibility') != 'labelHide':
                filtered_labels.append(l)
        
        return {"labels": filtered_labels}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/threads/{thread_id}")
def gmail_thread_detail(thread_id: str, request: Request):
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=25)
    credentials = _get_credentials(uid)
    try:
        service = gmail.get_gmail_service(credentials)
        thread = gmail.execute_with_retry(service.users().threads().get(userId='me', id=thread_id, format='full'))
        return thread
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages/{message_id}/attachments/{attachment_id}")
def gmail_attachment(message_id: str, attachment_id: str, request: Request):
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=20)
    credentials = _get_credentials(uid)
    try:
        service = gmail.get_gmail_service(credentials)
        attachment = gmail.execute_with_retry(service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ))
        return attachment
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Page-level and Message-level cache with background prefetch ────────
_gmail_email_cache: dict = {}  # uid -> { msg_id: { "email": dict, "timestamp": float } }
_gmail_page_cache: dict = {}   # uid -> { cache_key -> { "message_ids": List[str], "next_page_token": str | None, "timestamp": float } }
_GMAIL_CACHE_TTL = 5 * 60  # 5 minutes
_prefetch_locks: dict = {}  # uid -> threading.Lock  (prevents duplicate prefetches)

def _cache_key_for(query_string: str | None, page_token: str | None, count: int) -> str:
    """Build a stable cache key from query + page token + count."""
    raw = f"{query_string or ''}|{page_token or ''}|{count}"
    return hashlib.md5(raw.encode()).hexdigest()

def _get_cached_email_details(uid: str, msg_ids: List[str]) -> dict:
    """Check _gmail_email_cache for existing, valid messages. Return dict of msg_id -> email_details."""
    if not uid or uid not in _gmail_email_cache:
        return {}
    
    user_cache = _gmail_email_cache[uid]
    now = time.time()
    valid_emails = {}
    for msg_id in msg_ids:
        entry = user_cache.get(msg_id)
        if entry:
            if now - entry.get("timestamp", 0) <= _GMAIL_CACHE_TTL:
                valid_emails[msg_id] = entry["email"]
            else:
                user_cache.pop(msg_id, None)  # Evict expired
    return valid_emails

def _set_cached_email_details(uid: str, emails: List[dict]):
    """Store email details in _gmail_email_cache."""
    if not uid or not emails:
        return
    if uid not in _gmail_email_cache:
        _gmail_email_cache[uid] = {}
    
    now = time.time()
    for email in emails:
        msg_id = email.get("message_id")
        if msg_id:
            _gmail_email_cache[uid][msg_id] = {
                "email": email,
                "timestamp": now
            }

def _get_page_cache(uid: str, cache_key: str):
    """Return cached page data if valid, else None."""
    if not uid or uid not in _gmail_page_cache:
        return None
    entry = _gmail_page_cache[uid].get(cache_key)
    if not entry:
        return None
    if time.time() - entry.get("timestamp", 0) > _GMAIL_CACHE_TTL:
        _gmail_page_cache[uid].pop(cache_key, None)
        return None
    return entry

def _set_page_cache(uid: str, cache_key: str, message_ids: List[str], next_page_token: str | None):
    """Store page metadata in the cache."""
    if not uid:
        return
    if uid not in _gmail_page_cache:
        _gmail_page_cache[uid] = {}
    _gmail_page_cache[uid][cache_key] = {
        "message_ids": message_ids,
        "next_page_token": next_page_token,
        "timestamp": time.time()
    }

def _prefetch_next_page(
    uid: str,
    creds_data: dict,
    query_string: str | None,
    next_page_token: str,
    count: int
):
    """Background worker: fetch the next page and cache it."""
    lock = _prefetch_locks.setdefault(uid, threading.Lock())
    if not lock.acquire(blocking=False):
        return  # Another prefetch is already running for this user
    try:
        creds = Credentials(**creds_data)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(AuthRequest())
            else:
                return
        service = gmail.get_gmail_service(creds)
        list_kwargs = {"userId": "me", "maxResults": count}
        if query_string:
            list_kwargs["q"] = query_string
        list_kwargs["pageToken"] = next_page_token

        results = gmail.execute_with_retry(service.users().messages().list(**list_kwargs))
        messages = results.get("messages", [])
        npt = results.get("nextPageToken", None)

        if messages:
            msg_ids = [m["id"] for m in messages]
            cached_emails = _get_cached_email_details(uid, msg_ids)
            missing_ids = [mid for mid in msg_ids if mid not in cached_emails]
            
            if missing_ids:
                new_emails = gmail.batch_get_email_details(service, missing_ids)
                _set_cached_email_details(uid, new_emails)
            
            ck = _cache_key_for(query_string, next_page_token, count)
            _set_page_cache(uid, ck, msg_ids, npt)
    except Exception as e:
        print(f"[prefetch] error for uid={uid}: {e}")
    finally:
        lock.release()


@router.get("/check/cached")
def gmail_check_cached(request: Request):
    """Return cached first-page inbox emails for instant loading. Returns empty if cache miss."""
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=40)

    # Look up default inbox first-page cache.
    # We check if we have a cache entry for count=20 first, and if not, check count=10.
    cached = None
    if uid:
        key_20 = _cache_key_for(None, None, 20)
        cached = _get_page_cache(uid, key_20)
        if not cached:
            key_10 = _cache_key_for(None, None, 10)
            cached = _get_page_cache(uid, key_10)

    if not cached:
        return {"count": 0, "emails": [], "next_page_token": None, "cached": False}

    msg_ids = cached["message_ids"]
    cached_emails_dict = _get_cached_email_details(uid, msg_ids) if uid else {}
    
    # We want to return whatever cached email details we have (even if it's a subset)
    emails = []
    for mid in msg_ids:
        if mid in cached_emails_dict:
            emails.append(cached_emails_dict[mid])
            
    if not emails:
        return {"count": 0, "emails": [], "next_page_token": None, "cached": False}

    return {
        "count": len(emails),
        "emails": emails,
        "next_page_token": cached.get("next_page_token"),
        "cached": True
    }


@router.get("/check")
def gmail_check(
    request: Request,
    count: int = Query(default=10, ge=1, le=50),
    q: str = Query(default=None),
    from_mail: str = Query(default=None),
    to_mail: str = Query(default=None),
    content_search: str = Query(default=None),
    has_attachments: bool = Query(default=None),
    page_token: str = Query(default=None),
    bypass_cache: bool = Query(default=False)
):
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=20)  # Search queries rate limit
    credentials = _get_credentials(uid)
    
    # Build search query
    parts = []
    if q: parts.append(q)
    if from_mail: parts.append(f"from:{from_mail}")
    if to_mail: parts.append(f"to:{to_mail}")
    if content_search: parts.append(content_search)
    if has_attachments: parts.append("has:attachment")
    
    query_string = " ".join(parts) if parts else None
    
    # ── Check page cache first ─────────────────────────────────────
    ck = _cache_key_for(query_string, page_token, count)
    
    if not bypass_cache:
        cached_page = _get_page_cache(uid, ck) if uid else None
        if cached_page:
            msg_ids = cached_page["message_ids"]
            cached_emails_dict = _get_cached_email_details(uid, msg_ids)
            # Check if we have all email details cached
            if len(cached_emails_dict) == len(msg_ids):
                # Reconstruct emails in original order
                emails = [cached_emails_dict[mid] for mid in msg_ids]
                return {
                    "count": len(emails),
                    "emails": emails,
                    "query_used": query_string,
                    "next_page_token": cached_page.get("next_page_token"),
                    "prefetched": True
                }
    
    try:
        service = gmail.get_gmail_service(credentials)
        list_kwargs = {"userId": "me", "maxResults": count}
        if query_string:
            list_kwargs["q"] = query_string
        if page_token:
            list_kwargs["pageToken"] = page_token
            
        results = gmail.execute_with_retry(service.users().messages().list(**list_kwargs))
        messages = results.get("messages", [])
        next_page_token = results.get("nextPageToken", None)
        
        if not messages:
            # Cache empty result too so we don't re-fetch
            if uid:
                _set_page_cache(uid, ck, [], None)
            return {"count": 0, "emails": [], "next_page_token": None}
        
        msg_ids = [m["id"] for m in messages]
        
        # Check what is already in individual cache
        cached_emails_dict = {}
        if uid and not bypass_cache:
            cached_emails_dict = _get_cached_email_details(uid, msg_ids)
            
        missing_ids = [mid for mid in msg_ids if mid not in cached_emails_dict]
        
        new_emails = []
        if missing_ids:
            new_emails = gmail.batch_get_email_details(service, missing_ids)
            if uid:
                _set_cached_email_details(uid, new_emails)
        
        # Merge cached and new email details, maintaining order of msg_ids
        emails = []
        for mid in msg_ids:
            if mid in cached_emails_dict:
                emails.append(cached_emails_dict[mid])
            else:
                match = next((e for e in new_emails if e["message_id"] == mid), None)
                if match:
                    emails.append(match)
        
        # Cache this page metadata
        if uid:
            _set_page_cache(uid, ck, msg_ids, next_page_token)
        
        # ── Background prefetch next page ──────────────────────────
        if uid and next_page_token and not bypass_cache:
            creds_data = user_credentials.get(uid)
            if creds_data:
                t = threading.Thread(
                    target=_prefetch_next_page,
                    args=(uid, dict(creds_data), query_string, next_page_token, count),
                    daemon=True
                )
                t.start()
            
        return {
            "count": len(emails),
            "emails": emails,
            "query_used": query_string,
            "next_page_token": next_page_token
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest")
def gmail_ingest(body: GmailIngestRequest, request: Request):
    uid = _get_uid_from_request(request)
    _check_rate_limit(uid, max_requests=5)  # ingestion is heavy
    credentials = _get_credentials(uid)
    service = gmail.get_gmail_service(credentials)
    
    chunk_dicts = []
    
    try:
        for msg_id in body.message_ids:
            email_data = gmail.get_email_details(service, msg_id)
            
            # Primary email body chunk
            text = email_data["body"]
            if len(text) >= 15:
                chunk_dicts.append({
                    "cleaned_text": text[:2000],
                    "source_ref": f"gmail:{msg_id}",
                    "speaker": email_data["from"],
                    "source_type": "gmail",
                })
            
            # Attachment chunks
            if body.include_attachments:
                for att in email_data["attachments"]:
                    if att["filename"].lower().endswith(".pdf"):
                        try:
                            pdf_data = gmail.download_attachment(service, msg_id, att["attachment_id"])
                            extracted_text = pdf.extract_text_from_pdf_bytes(pdf_data)
                            if extracted_text and len(extracted_text) >= 15:
                                chunk_dicts.append({
                                    "cleaned_text": extracted_text[:2000],
                                    "source_ref": f"gmail:{msg_id}:att:{att['filename']}",
                                    "speaker": email_data["from"],
                                    "source_type": "gmail",
                                })
                        except Exception as e:
                            print(f"Failed to process attachment {att['filename']}: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gmail extraction failed: {e}")

    if not chunk_dicts:
        raise HTTPException(status_code=400, detail="No usable content found in selected emails.")

    # Classify and store
    try:
        api_key = os.environ.get("GROQ_CLOUD_API")
        classified = classify_chunks(chunk_dicts, api_key=api_key)
    except Exception:
        classified = []
        for raw in chunk_dicts:
            text = (raw.get("cleaned_text") or "").strip()
            label = _fallback_label_for_text(text)
            classified.append(
                ClassifiedChunk(
                    session_id=body.session_id,
                    source_type="gmail",
                    source_ref=raw.get("source_ref", "unknown"),
                    speaker=raw.get("speaker", "Unknown"),
                    raw_text=text,
                    cleaned_text=text,
                    label=label,
                    confidence=0.6,
                    reasoning="Fallback local keyword classification.",
                    flagged_for_review=True,
                )
            )

    for chunk in classified:
        chunk.session_id = body.session_id
    
    store_chunks(classified)

    return {
        "message": f"Ingested {len(chunk_dicts)} items from Gmail.",
        "session_id": body.session_id,
        "item_count": len(classified),
    }
