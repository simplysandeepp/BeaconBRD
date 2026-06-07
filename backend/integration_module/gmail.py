import base64
import re
import time
import random
from googleapiclient.discovery import build  # type: ignore
from googleapiclient.errors import HttpError  # type: ignore

def execute_with_retry(request, max_retries=5):
    """Execute a Google API request with exponential backoff on 429 and 5xx errors."""
    for n in range(max_retries):
        try:
            return request.execute()
        except HttpError as e:
            if e.resp.status in [429, 500, 502, 503, 504]:
                sleep_time = (2 ** n) + random.random()
                time.sleep(sleep_time)
            else:
                raise e
    return request.execute()

def strip_html_tags(text: str):
    """Remove HTML tags, CSS, URLs and all newline characters, returning a single line of text."""
    # Remove style and script tags and their content
    text = re.sub(r'<(style|script)[^>]*>.*?</\1>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove remaining tags
    clean = re.compile('<.*?>', flags=re.DOTALL)
    text = re.sub(clean, ' ', text)
    # Remove URLs (http, https, www)
    text = re.sub(r'https?://\S+|www\.\S+', ' ', text)
    # Replace newlines and carriage returns with spaces
    text = text.replace('\n', ' ').replace('\r', ' ')
    # Normalize whitespace: replace multiple spaces with a single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_body(payload: dict):
    """Recursively extract and decode the body from a Gmail message payload."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            mimeType = part.get("mimeType")
            data = part.get("body", {}).get("data")
            if mimeType == "text/plain" and data:
                plain_text = base64.urlsafe_b64decode(data).decode("utf-8")
                body += strip_html_tags(str(plain_text)) + " "
            elif mimeType == "text/html" and data:
                html_content = base64.urlsafe_b64decode(data).decode("utf-8")
                if not body.strip():
                    body += strip_html_tags(str(html_content)) + " "
            elif "parts" in part:
                body += get_body(part) + " "
    else:
        data = payload.get("body", {}).get("data")
        if data:
            content = base64.urlsafe_b64decode(data).decode("utf-8")
            body = strip_html_tags(str(content))
    return body

def get_email_details(service, msg_id):
    """Fetch and parse email details including subject, sender, and body."""
    msg = execute_with_retry(service.users().messages().get(userId="me", id=msg_id))
    headers = msg.get("payload", {}).get("headers", [])
    subject = "No Subject"
    sender = "Unknown"
    for header in headers:
        if header["name"].lower() == "subject":
            subject = header["value"]
        if header["name"].lower() == "from":
            sender = header["value"]
    
    body = get_body(msg.get("payload", {}))
    # Final normalization to ensure no double spaces or newlines remain
    body = body.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    body = re.sub(r'\s+', ' ', body).strip()
    
    attachments = get_attachments(msg.get("payload", {}))
    
    return {
        "subject": subject,
        "from": sender,
        "body": body.strip(),
        "snippet": msg.get("snippet", ""),
        "message_id": msg_id,
        "thread_id": msg.get("threadId"),
        "attachments": attachments,
        "labelIds": msg.get("labelIds", [])
    }

def get_attachments(payload):
    """Recursively find all attachments in a message payload."""
    attachments = []
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("filename"):
                attachments.append({
                    "filename": part.get("filename"),
                    "mimeType": part.get("mimeType"),
                    "attachment_id": part.get("body", {}).get("attachmentId"),
                    "size": part.get("body", {}).get("size")
                })
            if "parts" in part:
                attachments.extend(get_attachments(part))
    return attachments

def download_attachment(service, message_id, attachment_id):
    """Fetch the content of an attachment."""
    attachment = execute_with_retry(service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ))
    return base64.urlsafe_b64decode(attachment.get("data").encode("UTF-8"))

def batch_get_email_details(service, msg_ids):
    """Fetch multiple email details in a single batch HTTP request.
    
    Uses the Gmail API's batch endpoint to collapse N sequential
    messages.get() calls into 1 HTTP round-trip (up to 100 per batch).
    Falls back to sequential fetching on batch failure.
    """
    if not msg_ids:
        return []

    results = {}
    errors = {}

    def _callback(request_id, response, exception):
        if exception is not None:
            errors[request_id] = exception
        else:
            results[request_id] = response

    try:
        batch = service.new_batch_http_request(callback=_callback)
        for msg_id in msg_ids:
            batch.add(
                service.users().messages().get(userId="me", id=msg_id),
                request_id=msg_id
            )
        batch.execute()
    except Exception:
        # Batch call itself failed — fall back to sequential
        return [get_email_details(service, mid) for mid in msg_ids]

    emails = []
    for msg_id in msg_ids:
        if msg_id in errors:
            # Skip messages that failed individually within the batch
            continue
        msg = results.get(msg_id)
        if not msg:
            continue
        headers = msg.get("payload", {}).get("headers", [])
        subject = "No Subject"
        sender = "Unknown"
        for header in headers:
            if header["name"].lower() == "subject":
                subject = header["value"]
            if header["name"].lower() == "from":
                sender = header["value"]

        body = get_body(msg.get("payload", {}))
        body = body.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        body = re.sub(r'\s+', ' ', body).strip()

        attachments = get_attachments(msg.get("payload", {}))

        emails.append({
            "subject": subject,
            "from": sender,
            "body": body.strip(),
            "snippet": msg.get("snippet", ""),
            "message_id": msg_id,
            "thread_id": msg.get("threadId"),
            "attachments": attachments,
            "labelIds": msg.get("labelIds", [])
        })

    return emails


def get_gmail_service(credentials):
    """Initialize and return the Gmail API service."""
    return build("gmail", "v1", credentials=credentials)
