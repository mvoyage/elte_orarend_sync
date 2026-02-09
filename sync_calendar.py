import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from parser import OrarendEvent

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def load_config(path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def get_calendar_service():
    creds = None
    token_path = Path(TOKEN_FILE)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CREDENTIALS_FILE).exists():
                raise RuntimeError(
                    f"Missing {CREDENTIALS_FILE}. Download OAuth client JSON and place it next to sync_calendar.py."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)


def event_to_gcal(e: OrarendEvent, tz: str) -> Dict:
    return {
        "summary": e.summary,
        "location": e.location,
        "description": e.description,
        "start": {"dateTime": e.start.isoformat(), "timeZone": tz},
        "end": {"dateTime": e.end.isoformat(), "timeZone": tz},
        "extendedProperties": {
            "private": {
                "elte_orarend_uid": e.uid,
            }
        },
    }


def fetch_future_events(service, calendar_id: str, time_min: str) -> List[Dict]:
    events = []
    page_token = None
    while True:
        resp = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events


def sync_events(events: List[OrarendEvent]) -> Dict[str, int]:
    cfg = load_config()
    tz = cfg.get("timezone", "Europe/Budapest")
    calendar_id = cfg.get("calendar_id", "").strip() or None
    calendar_name = cfg.get("calendar_name", "").strip() or None

    if not calendar_id and not calendar_name:
        raise RuntimeError("Set calendar_id or calendar_name in config.json.")

    service = get_calendar_service()

    # Resolve calendar_id by name if provided
    if not calendar_id and calendar_name:
        clist = service.calendarList().list().execute().get("items", [])
        match = next((c for c in clist if c.get("summary") == calendar_name), None)
        if not match:
            raise RuntimeError(f"Calendar named '{calendar_name}' not found.")
        calendar_id = match["id"]

    try:
        zone = ZoneInfo(tz)
    except ZoneInfoNotFoundError as e:
        raise RuntimeError(
            f"Time zone '{tz}' not found. Install tzdata: pip install tzdata"
        ) from e
    now_dt = datetime.now(tz=zone)
    now = now_dt.isoformat()

    existing = fetch_future_events(service, calendar_id, now)
    existing_by_uid: Dict[str, Dict] = {}
    for ev in existing:
        uid = (
            ev.get("extendedProperties", {})
            .get("private", {})
            .get("elte_orarend_uid")
        )
        if uid:
            existing_by_uid[uid] = ev

    current_uids = set()

    created = 0
    updated = 0
    deleted = 0
    unchanged = 0

    for e in events:
        # Skip events that are in the past or currently in progress.
        if e.start <= now_dt:
            continue
        current_uids.add(e.uid)
        gcal_event = event_to_gcal(e, tz)
        if e.uid in existing_by_uid:
            ev = existing_by_uid[e.uid]
            # Update only if key fields changed
            changed = False
            for key in ("summary", "location", "description", "start", "end"):
                if ev.get(key) != gcal_event.get(key):
                    changed = True
                    break
            if changed:
                service.events().update(
                    calendarId=calendar_id,
                    eventId=ev["id"],
                    body=gcal_event,
                ).execute()
                updated += 1
            else:
                unchanged += 1
        else:
            service.events().insert(calendarId=calendar_id, body=gcal_event).execute()
            created += 1

    # Delete future events that no longer exist in current scrape
    for uid, ev in existing_by_uid.items():
        if uid not in current_uids:
            service.events().delete(calendarId=calendar_id, eventId=ev["id"]).execute()
            deleted += 1

    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "unchanged": unchanged,
    }


if __name__ == "__main__":
    raise SystemExit("Run main.py instead.")
