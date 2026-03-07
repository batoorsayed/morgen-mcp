import sys
from datetime import date, datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

import os

MORGEN_BASE_URL = "https://api.morgen.so/v3"

mcp = FastMCP("morgen-mcp")


def _api_key() -> str:
    key = os.getenv("MORGEN_API_KEY", "")
    if not key:
        raise RuntimeError("MORGEN_API_KEY is not set")
    return key


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"ApiKey {_api_key()}"}


def _account_id() -> str:
    aid = os.getenv("MORGEN_ACCOUNT_ID", "")
    if not aid:
        raise RuntimeError("MORGEN_ACCOUNT_ID is not set")
    return aid


def _fetch_calendar_ids_for_account(account_id: str) -> str:
    """Return comma-separated calendar IDs for the given account."""
    with httpx.Client() as client:
        resp = client.get(f"{MORGEN_BASE_URL}/calendars/list", headers=_auth_headers())
    resp.raise_for_status()
    calendars = resp.json().get("data", {}).get("calendars", [])
    ids = [c["id"] for c in calendars if c.get("accountId") == account_id]
    return ",".join(ids)


@mcp.tool()
def list_accounts() -> str:
    """List all connected Morgen accounts and their IDs."""
    with httpx.Client() as client:
        resp = client.get(f"{MORGEN_BASE_URL}/integrations/accounts/list", headers=_auth_headers())
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    accounts = data.get("data", {}).get("accounts", [])
    if not accounts:
        return "No accounts found."
    lines = ["Accounts:"]
    for acc in accounts:
        lines.append(
            f"  {acc.get('id', '?')}  {acc.get('providerUserId', '')}  "
            f"{acc.get('providerUserDisplayName', '')}  [{acc.get('integrationId', '')}]"
        )
    return "\n".join(lines)


@mcp.tool()
def list_calendars(account_id: str = "") -> str:
    """List calendars across all accounts, optionally filtered by account_id."""
    with httpx.Client() as client:
        resp = client.get(f"{MORGEN_BASE_URL}/calendars/list", headers=_auth_headers())
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    calendars = data.get("data", {}).get("calendars", [])
    aid = account_id.strip()
    if aid:
        calendars = [c for c in calendars if c.get("accountId") == aid]
    if not calendars:
        return "No calendars found."
    header = f"Calendars for account {aid}:" if aid else "All calendars:"
    lines = [header]
    for cal in calendars:
        lines.append(f"  {cal.get('id', '?')}  {cal.get('name', '')}  (account: {cal.get('accountId', '?')})")
    return "\n".join(lines)


@mcp.tool()
def get_events(date: str = "") -> str:
    """Fetch events for a given date (YYYY-MM-DD). Defaults to today if empty."""
    if date.strip():
        try:
            target = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            return "Invalid date format. Use YYYY-MM-DD."
    else:
        target = datetime.now(timezone.utc).date()

    start = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    params: dict[str, str] = {
        "accountId": _account_id(),
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
    }

    cal_ids = os.getenv("MORGEN_CALENDAR_IDS", "").strip()
    if not cal_ids:
        cal_ids = _fetch_calendar_ids_for_account(_account_id())
    if not cal_ids:
        return f"No calendars found for account {_account_id()}."
    params["calendarIds"] = cal_ids

    with httpx.Client() as client:
        resp = client.get(f"{MORGEN_BASE_URL}/events/list", headers=_auth_headers(), params=params)

    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"

    data = resp.json()
    events = data.get("data", {}).get("events", [])
    if not events:
        return f"No events found for {target}."

    events.sort(key=lambda e: e.get("start", ""))

    lines = [f"Events for {target}:"]
    for ev in events:
        title = ev.get("title", "(no title)")
        ev_start = ev.get("start", "")
        ev_end = ev.get("end", "")

        try:
            s = datetime.fromisoformat(ev_start.replace("Z", "+00:00"))
            e_dt = datetime.fromisoformat(ev_end.replace("Z", "+00:00"))
            duration_min = int((e_dt - s).total_seconds() // 60)
            start_fmt = s.strftime("%H:%M")
            end_fmt = e_dt.strftime("%H:%M")
            lines.append(f"  {start_fmt}–{end_fmt} ({duration_min}m)  {title}")
        except Exception:
            lines.append(f"  {ev_start} – {ev_end}  {title}")

    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]

    if "--list-accounts" in args:
        print(list_accounts())
        return

    if "--list-calendars" in args:
        idx = args.index("--list-calendars")
        aid = args[idx + 1] if idx + 1 < len(args) else ""
        print(list_calendars(aid))
        return

    mcp.run()


if __name__ == "__main__":
    main()
