# morgen-mcp

An MCP server that connects your [Morgen](https://morgen.so) calendar to any MCP-compatible AI client.

---

## The idea

Calendar apps give you the technical skeleton of your day; what you did and when. Physical journals capture the feeling of it. This tool lives in between.

`morgen-mcp` exposes your Morgen schedule as tools that your AI client can call. At the end of the day, ask it to write a diary entry: it fetches your actual events, you add how it felt, and it writes something that reads like a real diary and  not a meeting log.

Pair it with an Obsidian MCP and the entry saves directly to your daily note. No extra subscriptions, no extra API keys. Works with whatever AI client you already use.

---

## How it works

`morgen-mcp` is an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server. It exposes 3 tools:

| Tool | Description |
|---|---|
| `get_events` | Fetch events for a given date across selected calendars |
| `list_accounts` | List connected Morgen accounts and their IDs |
| `list_calendars` | List calendars under an account |

The AI client calls these tools to get your schedule. Writing the diary entry and saving it is up to the client and whatever other MCP tools you have connected.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A [Morgen](https://morgen.so) account - get your API key at [platform.morgen.so](https://platform.morgen.so)
- Any MCP-compatible client (Claude Desktop, Cursor, Windsurf, etc.)

---

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/morgen-mcp
cd morgen-mcp
uv sync
```

### 1. Get your Morgen API key

Go to [platform.morgen.so](https://platform.morgen.so) > Developers > API Keys.

### 2. Configure environment

```bash
cp .env.example .env
# Add your API key to .env
```

Then run this to fetch your account IDs and get a ready-to-paste env line:

```bash
uv run morgen-mcp --list-accounts
```

It will print something like:

```
Accounts:
  abc123def456  Your Name  [icloud]
  xyz789ghi012  Your Name  [google]
  ...

Add to your .env:
  MORGEN_ACCOUNT_ID=abc123def456,xyz789ghi012,...
```

Copy that line into your `.env`. Include only the accounts whose events you want — see the [rate limits](#rate-limits) note below.

### 3. Register with your MCP client

**Claude Code:**

```bash
claude mcp add --scope user morgen-mcp -- uv --directory /absolute/path/to/morgen-mcp run morgen-mcp
```

Run once. Available across all projects. Credentials are picked up from `.env` automatically.

**Other clients** (Claude Desktop, Cursor, Windsurf, etc.) — add to your client's MCP config file:

```json
{
  "mcpServers": {
    "morgen-mcp": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/morgen-mcp", "run", "morgen-mcp"],
      "env": {
        "MORGEN_API_KEY": "$MORGEN_API_KEY",
        "MORGEN_ACCOUNT_ID": "$MORGEN_ACCOUNT_ID"
      }
    }
  }
}
```

---

## Usage

Just talk to your AI client:

```
"Write my diary entry for today"
"What did I have on my calendar yesterday?"
"Summarize my week"
```

### Suggested system prompt

If your client supports project-level instructions, add something like:

> When I ask for a diary entry: fetch my Morgen events for that day, ask me how it felt, then write a personal diary entry that combines what I did with how I felt about it. Keep it human — not a bullet list, not a report. Append it to my Obsidian daily note under a "### End of Day" heading.

---

## Output example

```markdown
### End of Day

Morning focus block finally broke the deadlock on the data layer —
that one took longer than it should have but shipping it felt like
putting down something heavy. Three back-to-back meetings killed the
afternoon momentum. The kind of day where you do more than it felt like.
```

---

## Rate limits

The Morgen API allows 100 points per 15-minute window. Each `/list` call (calendars, events) costs 10 points.

`get_events` makes one calendars fetch plus one events fetch per configured account. With 6 accounts that's 70 points — leaving 30 to spare. Fine for a diary tool used a few times a day, but avoid calling it in rapid succession.

If you hit a 429, wait a few minutes and try again.

---

## Privacy

Event data is fetched from Morgen and passed to your AI client for processing. No data is stored or sent anywhere else. Your AI client's own privacy policy applies to how it handles that data.

---

## Contributing

Small tool, open door. PRs welcome — keep it simple.

---

## License

MIT
