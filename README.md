# ELTE Órarend Sync

This project logs in to ELTE, downloads your ELTE GTK órarend table, parses it, and syncs it into a Google Calendar. It only creates/updates/deletes **future** events. Past events are left untouched.

## Files
- `scraper.py`: logs in, downloads the órarend page, and saves a dated HTML snapshot
- `parser.py`: parses the órarend table into events
- `sync_calendar.py`: syncs events to Google Calendar (OAuth stub included)
- `main.py`: runs the full pipeline
- `config.example.json`: template for your settings

## Setup
1. Create `config.json` based on `config.example.json`.
2. Fill in:
   - `login_url`: the ELTE login URL (the long one with ReturnTo).
   - `credentials.username` and `credentials.password`.
   - `credentials.username_field` / `credentials.password_field`: input field names from the login form (if different).
   - `calendar_id` or `calendar_name`: your target calendar.
   - Optional: `orarend_url` if auto-discovery fails.

## Google Calendar OAuth (TODO)
`sync_calendar.py` contains placeholders and comments for OAuth setup. You will need:
- A Google Cloud project with Calendar API enabled.
- An OAuth client secrets JSON (download it and place in this folder).
- A `token.json` created on first run.

## Run
```powershell
python -m pip install -r requirements.txt
python main.py
```

## Scheduled Task (Windows Task Scheduler)
Create a task that runs daily at **1:00 AM**:
- Program: `python`
- Arguments: `main.py`
- Start in: `C:\Users\Csikós Péter\Documents\elte_orarend_sync`

## Notes
- Snapshots are stored in `data/snapshots` and only the last 7 are kept.
- Timezone is fixed to `Europe/Budapest`.
- If the login form changes, update `credentials.username_field` / `credentials.password_field` and/or add `credentials.extra_fields`.
