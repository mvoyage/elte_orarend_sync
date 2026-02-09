import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup


def load_config(path: str = "config.json") -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def cookie_string_to_dict(cookie: str) -> Dict[str, str]:
    parts = [p.strip() for p in cookie.split(";") if p.strip()]
    out: Dict[str, str] = {}
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def find_orarend_url(html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    # Try to find the Órarend menu link
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        href = a["href"]
        if "órarend" in text or "orarend" in text:
            if href.startswith("http"):
                return href
            if href.startswith("/"):
                return "https://inform.gtk.elte.hu" + href
            # relative to base
            return requests.compat.urljoin(base_url, href)

    # Fallback: known site=2
    if "site=100" in base_url:
        return base_url.replace("site=100", "site=2")
    return None


def save_snapshot(html: str, snapshots_dir: Path, keep: int) -> Path:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    path = snapshots_dir / f"{stamp}.html"
    path.write_text(html, encoding="utf-8")

    # Keep only last N snapshots (by mtime)
    files = sorted(snapshots_dir.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
    return path


def _extract_form(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    return soup.find("form")


def _build_form_payload(form: BeautifulSoup) -> Dict[str, str]:
    payload: Dict[str, str] = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        payload[name] = inp.get("value", "")
    return payload


def _submit_form(
    session: requests.Session, form: BeautifulSoup, base_url: str, payload: Dict[str, str]
) -> requests.Response:
    action = form.get("action")
    if not action or action == "?":
        action = base_url
    method = (form.get("method") or "post").lower()
    action_url = requests.compat.urljoin(base_url, action)
    if method == "get":
        return session.get(action_url, params=payload, timeout=30)
    return session.post(action_url, data=payload, timeout=30)


def _follow_saml_posts(
    session: requests.Session, resp: requests.Response, max_steps: int = 5, debug_dir: Optional[Path] = None
) -> requests.Response:
    current = resp
    for _ in range(max_steps):
        soup = BeautifulSoup(current.text, "html.parser")
        form = _extract_form(soup)
        if form is None:
            break
        payload = _build_form_payload(form)
        has_saml = "SAMLResponse" in payload or "RelayState" in payload
        has_password = any(
            inp.get("type", "").lower() == "password" for inp in form.find_all("input")
        )
        if not has_saml and has_password:
            # Likely a login form again; stop here
            break
        if not has_saml and len(payload) == 0:
            break
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"saml_step_{_+1}.html").write_text(current.text, encoding="utf-8")
        current = _submit_form(session, form, current.url, payload)
        current.raise_for_status()
    return current


def login(session: requests.Session, cfg: dict, start_url: Optional[str] = None) -> None:
    login_url = cfg.get("login_url", "").strip()
    creds = cfg.get("credentials", {})
    username = creds.get("username", "").strip()
    password = creds.get("password", "").strip()

    if not login_url and not start_url:
        raise RuntimeError("Missing login_url in config.json.")
    if not username or not password:
        raise RuntimeError("Missing credentials.username or credentials.password in config.json.")

    debug_dir = Path(cfg.get("debug_dir", "data/debug"))

    # Load login page (either explicit login_url or start_url which should redirect to login)
    first_url = login_url or start_url
    resp = session.get(first_url, timeout=30, allow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    form = _extract_form(soup)
    if form is None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "login_not_found.html").write_text(resp.text, encoding="utf-8")
        raise RuntimeError("Login form not found. Update login_url or adjust parser.")

    payload = _build_form_payload(form)

    user_field = creds.get("username_field", "username")
    pass_field = creds.get("password_field", "password")
    payload[user_field] = username
    payload[pass_field] = password

    extra_fields = creds.get("extra_fields", {}) or {}
    for k, v in extra_fields.items():
        payload[k] = v

    r = _submit_form(session, form, resp.url, payload)
    r.raise_for_status()

    # Follow any SAML auto-post forms
    _follow_saml_posts(session, r, debug_dir=debug_dir)

def download_orarend() -> Path:
    cfg = load_config()

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    cookie = cfg.get("cookie", "").strip()
    if cookie:
        s.cookies.update(cookie_string_to_dict(cookie))

    # Always login at each run (start from site=0 to trigger IdP redirect)
    start_url = cfg.get("login_start_url", "").strip() or None
    if not start_url:
        start_url = cfg.get("orarend_url", "").strip() or None
    login(s, cfg, start_url=start_url)

    base_url = cfg.get("base_url", "https://inform.gtk.elte.hu/index.php?site=100")
    orarend_url = cfg.get("orarend_url", "").strip() or None

    # Hit base URL after login (establish session on inform.gtk.elte.hu)
    base_resp = s.get(base_url, timeout=30)
    base_resp.raise_for_status()

    if not orarend_url:
        orarend_url = find_orarend_url(base_resp.text, base_url)

    if not orarend_url:
        raise RuntimeError("Could not determine Órarend URL. Set 'orarend_url' in config.json.")

    resp = s.get(orarend_url, timeout=30)
    resp.raise_for_status()

    # Some pages are served with legacy encodings; try to recover if needed
    if "charset" not in resp.headers.get("Content-Type", ""):
        resp.encoding = resp.apparent_encoding or "utf-8"

    html = resp.text
    if "Nincs jogosults" in html or "Nincs jogosultsága" in html:
        debug_dir = Path(cfg.get("debug_dir", "data/debug"))
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "orarend_denied.html").write_text(html, encoding="utf-8")
        raise RuntimeError(
            "Login failed or no access to Órarend page. "
            "Saved debug HTML to data/debug/orarend_denied.html"
        )
    snapshots_dir = Path(cfg.get("snapshots_dir", "data/snapshots"))
    keep = int(cfg.get("keep_snapshots", 7))
    return save_snapshot(html, snapshots_dir, keep)


if __name__ == "__main__":
    path = download_orarend()
    print(str(path))
