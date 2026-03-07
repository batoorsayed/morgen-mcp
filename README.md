# morgen-diary

An MCP server that exposes your [Morgen](https://morgen.so) calendar as tools for any MCP-compatible AI client.

Built for end-of-day journaling: fetch your actual schedule, add how it felt, let the AI write the entry, save it where you want.

---

## Tools

| Tool | Description |
|---|---|
| `get_events` | Fetch events for a given date across selected calendars |
| `list_accounts` | List connected Morgen accounts and their IDs |
| `list_calendars` | List calendars under an account |

Writing the diary entry and saving it (e.g. to Obsidian) is handled by your AI client and its other connected tools.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A [Morgen](https://morgen.so) account — API key from [platform.morgen.so](https://platform.morgen.so)
- Any MCP-compatible client (Claude Desktop, Cursor, Windsurf, etc.)

---

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/morgen-diary
cd morgen-diary
uv sync
```

### Find your account and calendar IDs

```bash
# List accounts
uv run morgen-diary --list-accounts

# List calendars for an account
uv run morgen-diary --list-calendars <account_id>
```

### Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
MORGEN_API_KEY=your_api_key
MORGEN_ACCOUNT_ID=your_account_id

# Optional: comma-separated calendar IDs to include
# Leave unset to fetch all calendars under the account
MORGEN_CALENDAR_IDS=cal_id_1,cal_id_2
```

### Add to your MCP client

```json
{
  "mcpServers": {
    "morgen-diary": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/morgen-diary", "run", "morgen-diary"],
      "env": {
        "MORGEN_API_KEY": "your_key",
        "MORGEN_ACCOUNT_ID": "your_account_id",
        "MORGEN_CALENDAR_IDS": "cal_id_1,cal_id_2"
      }
    }
  }
}
```

Restart your client. The tools will be available.

---

## Calendar selection

- **All calendars** — leave `MORGEN_CALENDAR_IDS` unset
- **Specific calendars** — set `MORGEN_CALENDAR_IDS` to a comma-separated list of IDs

Use `list_calendars` to find the IDs you want.

---

## License

MIT
