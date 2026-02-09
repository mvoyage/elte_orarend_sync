import json
import time
import traceback
from datetime import datetime

from scraper import download_orarend
from parser import parse_snapshot
from sync_calendar import sync_events
from emailer import RunSummary, send_run_email


def main() -> None:
    start_wall = datetime.now()
    start_perf = time.perf_counter()
    snapshot_path = ""
    events = []
    metrics = {
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "unchanged": 0,
        "created_details": [],
        "updated_details": [],
        "deleted_details": [],
        "unchanged_details": [],
    }
    errors = []
    status = "success"

    calendar_id = ""
    calendar_name = ""
    email_cfg = {}
    lecture_group_letter = "K"
    try:
        with open("config.json", "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
            calendar_id = (cfg.get("calendar_id") or "").strip()
            calendar_name = (cfg.get("calendar_name") or "").strip()
            email_cfg = cfg.get("email") or {}
            lecture_group_letter = (cfg.get("lecture_group_letter") or "K").strip()
    except OSError:
        pass

    email_enabled = bool(email_cfg.get("enabled"))
    print(
        "Email config | "
        f"enabled={email_enabled} | "
        f"from={email_cfg.get('from_addr', '') or '-'} | "
        f"to={email_cfg.get('to_addr', '') or '-'} | "
        f"credentials_file={email_cfg.get('credentials_file', '') or '-'} | "
        f"token_file={email_cfg.get('token_file', '') or '-'}"
    )

    try:
        snapshot_path = str(download_orarend())
        events = parse_snapshot(snapshot_path, lecture_group_letter=lecture_group_letter)
        if not events:
            raise RuntimeError("No events parsed from the Órarend table.")
        metrics = sync_events(events)
    except Exception as exc:
        status = "failure"
        errors.append(f"{type(exc).__name__}: {exc}")
        errors.append(traceback.format_exc())
        raise
    finally:
        elapsed_s = time.perf_counter() - start_perf
        finished_at = datetime.now()

        summary = RunSummary(
            status=status,
            started_at=start_wall,
            finished_at=finished_at,
            elapsed_s=elapsed_s,
            snapshot_path=snapshot_path or "-",
            events_parsed=len(events),
            created=metrics.get("created", 0),
            updated=metrics.get("updated", 0),
            deleted=metrics.get("deleted", 0),
            unchanged=metrics.get("unchanged", 0),
            calendar_id=calendar_id,
            calendar_name=calendar_name,
            created_details=metrics.get("created_details", []),
            updated_details=metrics.get("updated_details", []),
            deleted_details=metrics.get("deleted_details", []),
            unchanged_details=metrics.get("unchanged_details", []),
            errors=errors,
        )

        send_on_failure = bool(email_cfg.get("send_on_failure"))
        if email_enabled and (status == "success" or send_on_failure):
            try:
                send_run_email(summary, email_cfg)
            except Exception as email_exc:
                print(f"Email send failed: {email_exc}")
        elif not email_enabled:
            print("Email not sent: email.enabled is false or email config missing.")

        print(
            "Run summary | "
            f"raw_exported={len(events)} | "
            f"created={summary.created} | "
            f"updated={summary.updated} | "
            f"deleted={summary.deleted} | "
            f"unchanged={summary.unchanged} | "
            f"snapshot={summary.snapshot_path} | "
            f"calendar_id={calendar_id or '-'} | "
            f"calendar_name={calendar_name or '-'} | "
            f"elapsed_s={elapsed_s:.2f}"
        )


if __name__ == "__main__":
    main()
