import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env from repo root regardless of working directory
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


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _api_key() -> str:
    key = os.getenv("MORGEN_API_KEY", "")
    if not key:
        raise RuntimeError("MORGEN_API_KEY is not set")
    return key


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"ApiKey {_api_key()}"}


def _account_ids() -> list[str]:
    """Return account IDs from MORGEN_ACCOUNT_ID env var (comma-separated)."""
    raw = os.getenv("MORGEN_ACCOUNT_ID", "").strip()
    if not raw:
        raise RuntimeError("MORGEN_ACCOUNT_ID is not set")
    return [aid.strip() for aid in raw.split(",") if aid.strip()]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_iso_duration(duration: str) -> timedelta | None:
    """Parse ISO 8601 duration (e.g. PT25M, PT1H30M, P2D) into a timedelta."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", duration)
    if not m or not any(m.groups()):
        return None
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    return timedelta(days=days, hours=hours, minutes=minutes)


def _parse_event_start(ev: dict) -> datetime:
    """Parse event start and attach its timezone. Falls back to UTC.

    Morgen returns start times WITHOUT a timezone offset — the timezone
    lives in a separate "timeZone" field. For all-day events
    (showWithoutTime=true) we skip timezone conversion entirely because
    only the date portion matters and converting would shift the date.
    """
    s = datetime.fromisoformat(ev.get("start", ""))
    tz_str = ev.get("timeZone", "")
    # Only apply timezone for timed events — all-day dates stay as-is
    if tz_str and not ev.get("showWithoutTime", False):
        try:
            return s.replace(tzinfo=ZoneInfo(tz_str))
        except (ZoneInfoNotFoundError, KeyError):
            pass
    return s.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _fetch_all_calendars(client: httpx.Client) -> list[dict]:
    """Fetch all calendars across all accounts."""
    resp = client.get(f"{MORGEN_BASE_URL}/calendars/list", headers=_auth_headers())
    resp.raise_for_status()
    return resp.json().get("data", {}).get("calendars", [])


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_accounts() -> str:
    """List all connected Morgen accounts and their IDs."""
    try:
        with httpx.Client() as client:
            resp = client.get(
                f"{MORGEN_BASE_URL}/integrations/accounts/list",
                headers=_auth_headers(),
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return f"Error {e.response.status_code}: {e.response.text}"
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
    # Determine target date (local time)
    if date.strip():
        try:
            target = datetime.strptime(date.strip(), "%Y-%m-%d").date()
        except ValueError:
            return "Invalid date format. Use YYYY-MM-DD."
    else:
        target = datetime.now().astimezone().date()

    # Query window: local midnight-to-midnight, converted to UTC for the API
    local_tz = datetime.now().astimezone().tzinfo
    start = datetime(target.year, target.month, target.day, tzinfo=local_tz)
    end = start + timedelta(days=1)
    start_str = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fetch events from all configured accounts
    all_events: list[dict] = []
    warnings: list[str] = []
    headers = _auth_headers()
    with httpx.Client() as client:
        all_calendars = _fetch_all_calendars(client)
        for account_id in _account_ids():
            # Each API call takes one accountId; calendarIds must belong to it
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
            try:
                resp = client.get(
                    f"{MORGEN_BASE_URL}/events/list", headers=headers, params=params
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                warnings.append(
                    f"Warning: failed to fetch account {account_id} "
                    f"(HTTP {e.response.status_code})"
                )
                continue
            all_events.extend(resp.json().get("data", {}).get("events", []))

    if not all_events:
        msg = f"No events found for {target}."
        if warnings:
            msg += "\n" + "\n".join(warnings)
        return msg

    # Sort by timezone-aware UTC time so cross-timezone events land in order
    def _sort_key(ev: dict) -> datetime:
        try:
            return _parse_event_start(ev).astimezone(timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    all_events.sort(key=_sort_key)

    # Format each event into a human-readable line
    lines = [f"Events for {target}:"]
    for ev in all_events:
        title = ev.get("title", "(no title)")
        duration_str = ev.get("duration", "")
        show_without_time = ev.get("showWithoutTime", False)

        try:
            dur = _parse_iso_duration(duration_str)

            if show_without_time:
                # All-day: use the raw date from the API (no timezone shift)
                raw_date = datetime.fromisoformat(ev.get("start", "")).date()
                if dur and dur.days > 1:
                    end_date = raw_date + dur - timedelta(days=1)
                    span = f"{raw_date.strftime('%b %-d')}–{end_date.strftime('%b %-d')}"
                    lines.append(f"  all-day ({span})  {title}")
                else:
                    lines.append(f"  all-day  {title}")
            else:
                # Timed event: convert from event timezone to local for display
                s = _parse_event_start(ev).astimezone()
                e_dt = s + dur if dur else None

                if e_dt:
                    duration_min = int((e_dt - s).total_seconds() // 60)
                    if e_dt.date() > s.date():
                        # Spans midnight — include date on end time
                        lines.append(
                            f"  {s.strftime('%H:%M')}–{e_dt.strftime('%b %-d %H:%M')} ({duration_min}m)  {title}"
                        )
                    else:
                        lines.append(
                            f"  {s.strftime('%H:%M')}–{e_dt.strftime('%H:%M')} ({duration_min}m)  {title}"
                        )
                else:
                    lines.append(f"  {s.strftime('%H:%M')}  {title}")
        except Exception:
            lines.append(f"  {title}")

    if warnings:
        lines.append("")
        lines.extend(warnings)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


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
