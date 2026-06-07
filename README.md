# Hermes Team Chat

Lightweight, token-free internal messaging system for Hermes Agent profiles (HAL, George, Ratatoskr, Prometheus, etc.).

Uses a simple SQLite queue so agents can coordinate without burning tokens on every handoff. Includes a smart responder that uses your existing Hermes models — **Nous Research free tiers are recommended** (e.g. `nvidia/nemotron-3-ultra:free`).

## Why This Exists

Hermes agents often need quick coordination:
- "Task X is ready for you in the handoff file"
- Status broadcasts
- "I just finished the research you asked for"

Before this, people either used the user as a relay or wrote files. This gives a proper `send` / `poll` / `team room` primitive that agents (and crons) can use directly.

## Features

- Point-to-point messaging + shared `team` broadcast room
- Zero token cost for the transport layer
- Robust responder (tries your Hermes model first, then falls back to a clean static acknowledgment)
- Easy to poll from startup scripts or cron jobs
- Works across multiple Hermes profiles on the same machine
- Designed to be called from other skills (wake processor, kanban, etc.)

> **v1.1 note**: The responder is intentionally lightweight. Even if the model call is noisy or unavailable, you still get a clean "message received" confirmation. Set `HERMES_RESPONDER_MODEL` to any model your `hermes chat` can access.

## Quick Start

```bash
# Send a message
python3 chat.py send hal george "Handoff for the new feature is in TO_GEORGE.md"

# Poll as George
python3 chat.py poll george

# Broadcast to the whole team
python3 chat.py send prometheus team "New pricing research ready — see latest kanban card"

# Check everything
python3 chat.py status
```

## Recommended Setup (Nous Free Models)

Set the responder model to one of the strong free Nous models:

```bash
export HERMES_RESPONDER_MODEL="nvidia/nemotron-3-ultra:free"
# or
export HERMES_RESPONDER_MODEL="stepfun/step-3.7-flash:free"
```

These are available through the Nous Research inference endpoint when you have the Hermes portal / auth unlocked.

The script will automatically use `hermes chat -m $HERMES_RESPONDER_MODEL --query "..."` so it reuses all your existing credentials and model routing.

## Integration Ideas

### In a cron (example for George morning brief)
```bash
# At the start of George's morning cron:
python3 /path/to/chat.py poll george
```

### From the wake processor
When a wake ping arrives for another agent, you can now also fire a chat notification instead of (or in addition to) writing a handoff file.

### In your own skills
Just call the script. No heavy dependencies.

## Commands

| Command     | Example                                      | Description                          |
|-------------|----------------------------------------------|--------------------------------------|
| `send`      | `send hal george "message here"`             | Queue a message                      |
| `poll`      | `poll george`                                | Read + mark messages for an agent    |
| `broadcast` | `broadcast "Team update..."`                 | Send to everyone (via `team` room)   |
| `status`    | `status`                                     | Unread counts + responder model      |
| `history`   | `history`                                    | Last 30 messages with responses      |

## Database Location

Default: `/home/debian/.hermes/team-chat/team-chat.db`

You can override with:
```bash
export HERMES_TEAM_CHAT_DB=/some/other/path/team-chat.db
```

**Permissions tip**: If you get `readonly database` errors, run:
```bash
sudo chown -R debian:debian /home/debian/.hermes/team-chat/
chmod 664 /home/debian/.hermes/team-chat/team-chat.db
```

## How the Responder Works

When an agent polls and there are unread messages, the script generates a short acknowledgment using your Hermes installation + the model in `HERMES_RESPONDER_MODEL`.

This is **not** the agent doing real work — it's a lightweight "I got this, will handle in next cycle" simulation so you get immediate feedback in logs.

Real work still happens when the target agent actually runs its normal reasoning loop and sees the message (or the handoff file you also wrote).

## Making It Public / Reusable

This skill was extracted and cleaned from a production Hermes Agent setup (profile `hal`). The goal is a simple, reliable coordination primitive that any Hermes user can drop in.

Pull requests welcome for:
- Better error handling
- Additional responder backends
- Docker / multi-user support
- More integration examples

## License

MIT

## Changelog

**v1.1** (current)
- Much more robust responder logic with aggressive output cleaning
- Graceful fallback to clean static acknowledgment when Hermes model call fails or returns noise (this is now the reliable default behavior)
- Better documentation around model selection
- Updated default prompt and output parsing

**v1.0**
- Initial public release

## Related

- Original context: Hermes Agent by Nous Research
- Companion skills: kanban-orchestrator, agent-wake-processor, model-router

If this saves you from writing another "TO_GEORGE.md" file, give it a star.