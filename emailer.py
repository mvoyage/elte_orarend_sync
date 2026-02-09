from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


@dataclass
class RunSummary:
    status: str
    started_at: datetime
    finished_at: datetime
    elapsed_s: float
    snapshot_path: str
    events_parsed: int
    created: int
    updated: int
    deleted: int
    unchanged: int
    calendar_id: str
    calendar_name: str
    created_details: List[Dict[str, str]]
    updated_details: List[Dict[str, str]]
    deleted_details: List[Dict[str, str]]
    unchanged_details: List[Dict[str, str]]
    errors: List[str]


def _format_errors(errors: List[str]) -> str:
    if not errors:
        return "none"
    return "\n".join(f"- {err}" for err in errors)


def _format_event_details(label: str, items: List[Dict[str, str]]) -> str:
    if not items:
        return f"{label}: none\n"
    lines = [f"{label}:"]
    for item in items:
        summary = item.get("summary") or "(no title)"
        uid = item.get("uid") or "-"
        lines.append(f"- {summary} | uid={uid}")
    lines.append("")
    return "\n".join(lines)


def _build_body(summary: RunSummary) -> str:
    details_block = (
        _format_event_details("Created events", summary.created_details)
        + _format_event_details("Updated events", summary.updated_details)
        + _format_event_details("Deleted events", summary.deleted_details)
        + _format_event_details("Unchanged events", summary.unchanged_details)
    )
    return (
        "ELTE órarend sync run summary\n"
        "\n"
        f"Status: {summary.status}\n"
        f"Started: {summary.started_at.isoformat()}\n"
        f"Finished: {summary.finished_at.isoformat()}\n"
        f"Elapsed: {summary.elapsed_s:.2f}s\n"
        "\n"
        "Procedure:\n"
        "- Download órarend snapshot\n"
        "- Parse events\n"
        "- Sync Google Calendar\n"
        "\n"
        f"Snapshot: {summary.snapshot_path}\n"
        f"Events parsed: {summary.events_parsed}\n"
        "\n"
        "Calendar changes:\n"
        f"- Created: {summary.created}\n"
        f"- Updated: {summary.updated}\n"
        f"- Deleted: {summary.deleted}\n"
        f"- Unchanged: {summary.unchanged}\n"
        "\n"
        f"Calendar ID: {summary.calendar_id or '-'}\n"
        f"Calendar name: {summary.calendar_name or '-'}\n"
        "\n"
        f"{details_block}"
        "Errors:\n"
        f"{_format_errors(summary.errors)}\n"
    )


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_TOKEN_FILE = "token_gmail.json"
GMAIL_CREDENTIALS_FILE = "credentials.json"


def _get_gmail_service(token_file: str, credentials_file: str):
    token_path = Path(token_file)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(credentials_file).exists():
                raise RuntimeError(
                    f"Missing {credentials_file}. Download OAuth client JSON and place it next to emailer.py."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def send_run_email(summary: RunSummary, email_cfg: Dict) -> bool:
    if not email_cfg or not email_cfg.get("enabled"):
        return False

    to_addr = (email_cfg.get("to_addr") or "").strip()
    from_addr = (email_cfg.get("from_addr") or "").strip()
    subject_prefix = (email_cfg.get("subject_prefix") or "ELTE órarend sync").strip()
    token_file = (email_cfg.get("token_file") or GMAIL_TOKEN_FILE).strip()
    credentials_file = (email_cfg.get("credentials_file") or GMAIL_CREDENTIALS_FILE).strip()

    if not (to_addr and from_addr):
        raise RuntimeError("Email config incomplete. Fill email.* in config.json.")

    status_label = "SUCCESS" if summary.status == "success" else "FAILURE"
    subject = f"{subject_prefix} | {status_label}"

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(_build_body(summary))

    service = _get_gmail_service(token_file, credentials_file)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service.users().messages().send(userId="me", body={"raw": raw}).execute()

    return True
