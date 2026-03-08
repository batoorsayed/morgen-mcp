import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MORGEN_BASE_URL = "https://api.morgen.so/v3"

mcp = FastMCP(
    "morgen-mcp",
    instructions=(
        "This server connects to the Morgen calendar API. "
        "Use get_events to fetch a user's calendar events for a given date (defaults to today). "
        "Use list_accounts to discover connected account IDs — useful during setup. "
        "Use list_calendars to explore calendars under a specific account. "
        "Event data is returned as plain text suitable for summarisation or diary writing."
    ),
)


def _api_key() -> str:
    key = os.getenv("MORGEN_API_KEY", "")
    if not key:
        raise RuntimeError("MORGEN_API_KEY is not set")
    return key


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"ApiKey {_api_key()}"}


def _account_ids() -> list[str]:
    raw = os.getenv("MORGEN_ACCOUNT_ID", "").strip()
    if not raw:
        raise RuntimeError("MORGEN_ACCOUNT_ID is not set")
    return [aid.strip() for aid in raw.split(",") if aid.strip()]


def _fetch_all_calendars(client: httpx.Client) -> list[dict]:
    """Return all calendars across all accounts."""
    resp = client.get(f"{MORGEN_BASE_URL}/calendars/list", headers=_auth_headers())
    resp.raise_for_status()
    return resp.json().get("data", {}).get("calendars", [])


@mcp.tool()
def list_accounts() -> str:
    """List all connected Morgen accounts and their IDs."""
    with httpx.Client() as client:
        resp = client.get(
            f"{MORGEN_BASE_URL}/integrations/accounts/list", headers=_auth_headers()
        )
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.text}"
    data = resp.json()
    accounts = data.get("data", {}).get("accounts", [])
    if not accounts:
        return "No accounts found."
    lines = ["Accounts:"]
    for acc in accounts:
        lines.append(
            f"  {acc.get('id', '?')}  {acc.get('providerUserDisplayName', '')}  [{acc.get('integrationId', '')}]"
        )
    all_ids = ",".join(acc.get("id", "") for acc in accounts)
    lines.append(f"\nAdd to your .env:\n  MORGEN_ACCOUNT_ID={all_ids}")
    lines.append(
        "\nSuggested CLAUDE.md snippet (edit to fit your workflow):\n"
        "---\n"
        "When I ask for a diary entry:\n"
        "1. Fetch my Morgen events for that day using get_events\n"
        "2. Check if today's daily note exists — if not, create it\n"
        "3. Read today's note and any recently flagged notes for context\n"
        "4. Ask me 2-3 short questions to capture what the calendar doesn't show\n"
        "5. Write a personal diary entry — human, not a bullet list\n"
        "6. Append it under a '### End of Day' heading\n"
        "---"
    )
    return "\n".join(lines)


@mcp.tool()
def list_calendars(account_id: str = "") -> str:
    """List calendars across all accounts, optionally filtered by account_id."""
    try:
        with httpx.Client() as client:
            calendars = _fetch_all_calendars(client)
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
    aid = account_id.strip()
    if aid:
        calendars = [c for c in calendars if c.get("accountId") == aid]
    if not calendars:
        return "No calendars found."
    header = f"Calendars for account {aid}:" if aid else "All calendars:"
    lines = [header]
    for cal in calendars:
        lines.append(
            f"  {cal.get('id', '?')}  {cal.get('name', '')}  (account: {cal.get('accountId', '?')})"
        )
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

    start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_events: list[dict] = []
    with httpx.Client() as client:
        all_calendars = _fetch_all_calendars(client)
        for account_id in _account_ids():
            cal_ids = ",".join(
                c["id"] for c in all_calendars if c.get("accountId") == account_id
            )
            if not cal_ids:
                continue
            params: dict[str, str] = {
                "accountId": account_id,
                "calendarIds": cal_ids,
                "start": start_str,
                "end": end_str,
            }
            resp = client.get(
                f"{MORGEN_BASE_URL}/events/list", headers=_auth_headers(), params=params
            )
            if resp.status_code != 200:
                return f"Error {resp.status_code} for account {account_id}: {resp.text}"
            all_events.extend(resp.json().get("data", {}).get("events", []))

    if not all_events:
        return f"No events found for {target}."

    all_events.sort(key=lambda e: e.get("start", ""))

    lines = [f"Events for {target}:"]
    for ev in all_events:
        title = ev.get("title", "(no title)")
        ev_start = ev.get("start", "")
        ev_end = ev.get("end", "")

        try:
            s = datetime.fromisoformat(ev_start)
            if len(ev_start.strip()) <= 10:
                lines.append(f"  all-day  {title}")
            elif ev_end:
                e_dt = datetime.fromisoformat(ev_end)
                duration_min = int((e_dt - s).total_seconds() // 60)
                lines.append(
                    f"  {s.strftime('%H:%M')}–{e_dt.strftime('%H:%M')} ({duration_min}m)  {title}"
                )
            else:
                lines.append(f"  {s.strftime('%H:%M')}  {title}")
        except Exception:
            lines.append(f"  {title}")

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
