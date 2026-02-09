import json
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bs4 import BeautifulSoup


@dataclass
class OrarendEvent:
    uid: str
    summary: str
    start: datetime
    end: datetime
    location: str
    description: str


def normalize_text(s: str) -> str:
    return " ".join(s.split())


def parse_subject(cell_text: str) -> tuple[str, str]:
    lines = [l.strip() for l in cell_text.split("\n") if l.strip()]
    if not lines:
        return "", ""
    name = lines[0]
    code = lines[1] if len(lines) > 1 else ""
    return name, code


def parse_course_type(cell_text: str) -> tuple[str, str, str]:
    lines = [l.strip() for l in cell_text.split("\n") if l.strip()]
    course_type = lines[0] if lines else ""
    group = ""
    course_code = ""
    # Typically: type, optional group in bold, and course code
    if len(lines) == 2:
        course_code = lines[1]
    elif len(lines) >= 3:
        group = lines[1]
        course_code = lines[2]
    return course_type, group, course_code


def parse_table(html: str, tz: str) -> List[OrarendEvent]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    target = None
    for t in tables:
        headers = [normalize_text(th.get_text(" ", strip=True)) for th in t.find_all("th")]
        if "Nap" in headers and "Idősáv" in headers:
            target = t
            break

    if target is None:
        return []

    out: List[OrarendEvent] = []
    try:
        zone = ZoneInfo(tz)
    except ZoneInfoNotFoundError as e:
        raise RuntimeError(
            f"Time zone '{tz}' not found. Install tzdata: pip install tzdata"
        ) from e

    for row in target.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        day_raw = cells[0].get_text(" ", strip=True)
        time_raw = cells[1].get_text(" ", strip=True)
        subject_raw = cells[2].get_text("\n", strip=True)
        type_raw = cells[3].get_text("\n", strip=True)
        room_raw = cells[4].get_text(" ", strip=True)
        teacher_raw = cells[5].get_text(" ", strip=True)

        if not day_raw or not time_raw:
            continue

        # Date format: YYYY.MM.DD
        try:
            date_obj = datetime.strptime(day_raw.strip(), "%Y.%m.%d")
        except ValueError:
            continue

        if "-" not in time_raw:
            continue
        start_s, end_s = [t.strip() for t in time_raw.split("-", 1)]
        try:
            start_dt = datetime.strptime(start_s, "%H:%M").replace(
                year=date_obj.year, month=date_obj.month, day=date_obj.day, tzinfo=zone
            )
            end_dt = datetime.strptime(end_s, "%H:%M").replace(
                year=date_obj.year, month=date_obj.month, day=date_obj.day, tzinfo=zone
            )
        except ValueError:
            continue

        subject_name, subject_code = parse_subject(subject_raw)
        course_type, group, course_code = parse_course_type(type_raw)

        course_type_lower = course_type.lower()
        is_lecture = course_type_lower.startswith("lecture") or course_type_lower.startswith("előadás")

        # For lectures, keep only groups containing letter K (case-insensitive)
        if is_lecture:
            if "k" not in group.lower():
                continue

        summary = subject_name
        if course_type:
            summary = f"{summary} ({course_type})"

        location = room_raw
        description_parts = [
            f"Tárgykód: {subject_code}" if subject_code else "",
            f"Kurzustípus: {course_type}" if course_type else "",
            f"Csoport: {group}" if group else "",
            f"Kurzuskód: {course_code}" if course_code else "",
            f"Oktató(k): {teacher_raw}" if teacher_raw else "",
            f"Hely: {room_raw}" if room_raw else "",
            "Megjegyzés: (nincs adat)",
        ]
        description = "\n".join([p for p in description_parts if p])

        # Stable UID for dedupe (future events only)
        uid_raw = f"{day_raw}|{time_raw}|{subject_code}|{course_code}|{room_raw}|{teacher_raw}"
        uid = hashlib.sha1(uid_raw.encode("utf-8")).hexdigest()

        out.append(
            OrarendEvent(
                uid=uid,
                summary=summary,
                start=start_dt,
                end=end_dt,
                location=location,
                description=description,
            )
        )

    return out


def parse_snapshot(path: str, tz: str = "Europe/Budapest") -> List[OrarendEvent]:
    html = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_table(html, tz)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parser.py <snapshot.html>")
        raise SystemExit(1)

    events = parse_snapshot(sys.argv[1])
    print(json.dumps([e.__dict__ for e in events], ensure_ascii=False, default=str, indent=2))
