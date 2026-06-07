---
name: hermes-team-chat
description: Internal agent-to-agent messaging and shared team room for Hermes profiles. SQLite queue + smart responder powered by your existing Hermes models (Nous free tiers recommended). Zero token cost for coordination.
---

# Hermes Team Chat

Enables reliable internal communication between Hermes agents (HAL, George, Ratatoskr, Prometheus, Heimdall, etc.).

## Core Principles
- Use for task handoffs, status updates, and coordination.
- Prefer direct `send` over user relay.
- Support both point-to-point and shared "team room" broadcast.
- **Zero token transport** — the queue itself costs nothing.
- Responder uses your unlocked models (Nous free tiers are excellent here).

## Usage

```bash
# Send direct message
python3 chat.py send hal george "Task complete — see handoff file"

# Broadcast to team room
python3 chat.py send prometheus team "New research lead on pricing"

# Poll inbox (call this from startup or crons)
python3 chat.py poll george

# Check status
python3 chat.py status
```

## Recommended Responder Model

```bash
export HERMES_RESPONDER_MODEL="nvidia/nemotron-3-ultra:free"
# Alternative fast free model:
# export HERMES_RESPONDER_MODEL="stepfun/step-3.7-flash:free"
```

The script will invoke `hermes chat -m $HERMES_RESPONDER_MODEL` so it reuses all your auth.

## Permissions & Ownership

The database must be writable by the user running the agents:

```bash
sudo chown -R debian:debian /home/debian/.hermes/team-chat/
chmod 664 /home/debian/.hermes/team-chat/team-chat.db
```

## Team Room Pattern

Use recipient `team` (or the `broadcast` command) for messages visible to the whole group. This is the recommended way to reduce user-as-middleman friction.

## Integration Points

- Add `python3 .../chat.py poll <YOUR_AGENT>` at the top of morning/eod crons.
- Wire into wake-processor for cross-agent notifications.
- Use alongside (not instead of) file handoffs for anything that needs audit trail.

## Files in This Skill

- `chat.py` — the complete implementation (modernized, Nous-aware)
- `README.md` — user-facing documentation and examples
- `SKILL.md` — this file

## Related Skills

- `kanban-orchestrator`
- `agent-wake-processor`
- `model-router`

This is a cleaned, standalone version of the team chat primitive originally developed inside a multi-agent Hermes deployment.