#!/usr/bin/env python3
"""
Hermes Team Chat v1.1
Lightweight, token-free internal messaging for Hermes Agent profiles.

Features:
- SQLite message queue (no tokens for transport)
- Point-to-point + "team" broadcast room
- Robust responder fallback (tries Hermes chat, then clean static ack)
- Designed for cron / startup polling by agents (HAL, George, Ratatoskr, etc.)

Usage examples:
  python3 chat.py send hal george "Task handoff complete. See TO_GEORGE.md"
  python3 chat.py poll george
  python3 chat.py send prometheus team "New research lead on pricing models"
  python3 chat.py status

Environment:
  HERMES_RESPONDER_MODEL   - Model to use for the responder attempt (default: nvidia/nemotron-3-ultra:free)
                             Set this to a model your 'hermes chat' can actually access.
  HERMES_PATH              - Path to hermes binary if not in PATH

Repo: https://github.com/gdsmnorm6-create/hermes-team-chat
"""

import sqlite3
import os
import subprocess
import sys
import time
import re
from datetime import datetime

# --- Configuration ---
DB_PATH = os.environ.get('HERMES_TEAM_CHAT_DB', '/home/debian/.hermes/team-chat/team-chat.db')
AGENTS = ['hal', 'george', 'ratatoskr', 'prometheus', 'heimdall', 'team']

# Default responder model. Change via env var to one your Hermes instance has access to.
DEFAULT_RESPONDER_MODEL = os.environ.get(
    'HERMES_RESPONDER_MODEL', 
    'nvidia/nemotron-3-ultra:free'
)

def get_hermes_binary():
    """Find hermes binary, respecting HERMES_PATH or common locations."""
    if 'HERMES_PATH' in os.environ:
        return os.environ['HERMES_PATH']
    try:
        result = subprocess.run(['which', 'hermes'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    candidates = [
        '/home/debian/.hermes/hermes-agent/venv/bin/hermes',
        os.path.expanduser('~/.hermes/hermes-agent/venv/bin/hermes'),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return 'hermes'

# --- Database Functions ---
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            from_agent TEXT,
            to_agent TEXT,
            message TEXT,
            time TEXT,
            read BOOLEAN,
            response_time TEXT,
            response_msg TEXT
        )
    ''')
    conn.commit()
    conn.close()

def send_message(from_agent, to_agent, message_content):
    if to_agent not in AGENTS and to_agent != 'broadcast':
        print(f"Error: Agent '{to_agent}' not recognized. Valid: {AGENTS}")
        return False

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO messages (from_agent, to_agent, message, time, read) VALUES (?, ?, ?, ?, ?)',
        (from_agent, to_agent, message_content, datetime.now().isoformat(), False)
    )
    conn.commit()
    conn.close()
    print(f"✅ Message queued for @{to_agent} from @{from_agent}.")
    return True

def get_unread_messages(agent_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        'SELECT id, from_agent, message, time FROM messages WHERE to_agent=? AND read=0 ORDER BY time',
        (agent_name,)
    )
    messages = cursor.fetchall()
    conn.close()
    return messages

def mark_as_read(message_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE messages SET read=1 WHERE id=?', (message_id,))
    conn.commit()
    conn.close()

def log_response(message_id, response_msg):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'UPDATE messages SET response_time=?, response_msg=? WHERE id=?',
        (datetime.now().isoformat(), response_msg, message_id)
    )
    conn.commit()
    conn.close()

# --- Smart Responder (v1.1 - robust cleaning + strong fallback) ---
def _clean_hermes_output(raw_output: str) -> str:
    """Strip Hermes CLI banners, debug dumps, session info, and return only the useful reply."""
    if not raw_output:
        return ""

    text = raw_output.strip()

    # Remove common Hermes debug / resume / banner lines
    lines = []
    for line in text.splitlines():
        l = line.strip()
        if not l:
            continue
        lower = l.lower()
        if any(bad in lower for bad in [
            "session:", "duration:", "messages:", "resume this session",
            "initializing", "query:", "🧾", "error code", "does not exist",
            "hermes --resume", "────────────────────────────────"
        ]):
            continue
        lines.append(l)

    cleaned = " ".join(lines).strip()

    # Take only the first 2-3 sentences
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    short = " ".join(sentences[:3]).strip()

    # If it's still mostly noise or very short, let caller fall back
    if len(short) < 12 or "hermes" in short.lower():
        return ""

    return short[:350]

def get_responder_response(agent, message_content):
    """
    Generate a short in-character acknowledgment.
    Tries Hermes chat first (using HERMES_RESPONDER_MODEL), then falls back to a clean static message.
    The static fallback is intentional — the responder's job is just to confirm receipt.
    """
    model = os.environ.get('HERMES_RESPONDER_MODEL', DEFAULT_RESPONDER_MODEL)
    hermes_bin = get_hermes_binary()

    # Attempt Hermes chat
    try:
        prompt = (
            f"You are the Hermes agent named {agent}. "
            f"You just received this internal message: '{message_content}'. "
            "Reply concisely in character (1-3 sentences maximum). "
            "Acknowledge receipt and note that it will be handled in your normal cycle. "
            "Do not start doing the work described in the message."
        )
        cmd = [hermes_bin, 'chat', '--query', prompt, '-m', model, '--cli']
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=70
        )

        raw = (result.stdout or result.stderr or "").strip()
        cleaned = _clean_hermes_output(raw)

        # Extra safety: reject if it looks like it echoed the prompt or is too prompt-like
        if cleaned and len(cleaned) > 8 and "internal message" not in cleaned.lower() and "acknowledge receipt" not in cleaned.lower():
            return cleaned
        # Otherwise fall through to clean static

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        print(f"[responder] Hermes chat attempt failed for model '{model}': {e}", file=sys.stderr)

    # Reliable zero-token fallback (this is the recommended path for most users)
    return f"@{agent} received your message and will process it in the next cycle."

# --- Command Handlers ---
def handle_send(args):
    if len(args) < 3:
        print("Usage: chat.py send <from_agent> <to_agent> <message>")
        sys.exit(1)
    from_agent = args[0].lower()
    to_agent = args[1].lower()
    message_content = ' '.join(args[2:])
    send_message(from_agent, to_agent, message_content)

def handle_poll(args):
    if len(args) < 1:
        print("Usage: chat.py poll <agent_name>")
        sys.exit(1)
    agent_name = args[0].lower()
    print(f"Polling messages for @{agent_name}...")
    messages = get_unread_messages(agent_name)
    if not messages:
        print(f"No new messages for @{agent_name}.")
        return

    for msg_id, from_agent, message_content, msg_time in messages:
        readable_time = datetime.fromisoformat(msg_time).strftime('%Y-%m-%d %H:%M:%S UTC')
        print(f"--- Message ID: {msg_id} ---")
        print(f"FROM: @{from_agent}")
        print(f"TIME: {readable_time}")
        print(f"MESSAGE: {message_content}")

        response = get_responder_response(agent_name, message_content)
        print(f"RESPONDER (@{agent_name}): {response}")
        log_response(msg_id, response)

        mark_as_read(msg_id)
        print("--------------------\n")

def handle_status(_):
    print(f"Team Chat Status (DB: {DB_PATH})")
    print(f"Responder model: {os.environ.get('HERMES_RESPONDER_MODEL', DEFAULT_RESPONDER_MODEL)}")
    print("Registered Agents:")
    for agent in AGENTS:
        conn = sqlite3.connect(DB_PATH)
        unread = conn.execute(
            'SELECT COUNT(*) FROM messages WHERE to_agent=? AND read=0', (agent,)
        ).fetchone()[0]
        total = conn.execute(
            'SELECT COUNT(*) FROM messages WHERE to_agent=?', (agent,)
        ).fetchone()[0]
        print(f"  @{agent}: {unread} unread, {total} total messages")
        conn.close()

def handle_broadcast(args):
    if len(args) < 1:
        print("Usage: chat.py broadcast <message>")
        sys.exit(1)
    message_content = ' '.join(args)
    print(f"Broadcasting to team room: '{message_content}'")
    for agent in AGENTS:
        if agent == 'team':
            continue
        send_message('team', agent, message_content)
        time.sleep(0.2)
    print("Broadcast complete.")

def handle_history(_):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        'SELECT from_agent, to_agent, message, time, read, response_msg FROM messages ORDER BY time DESC LIMIT 30'
    )
    history = cursor.fetchall()
    conn.close()

    print("\n--- Team Chat Recent History (Last 30) ---")
    if not history:
        print("No history yet.")
        return

    for msg in reversed(history):
        from_agent, to_agent, message_content, msg_time, read_status, response_msg = msg
        readable_time = datetime.fromisoformat(msg_time).strftime('%Y-%m-%d %H:%M:%S UTC')
        status = "READ" if read_status else "UNREAD"
        print(f"[{readable_time}] @{from_agent} -> @{to_agent} ({status}): {message_content}")
        if read_status and response_msg:
            print(f"  Responder: {response_msg}")
    print("------------------------------------------\n")

def main():
    init_db()

    if len(sys.argv) < 2:
        print("Hermes Team Chat v1.1 — internal agent messaging")
        print("Commands: send | poll | status | broadcast | history")
        print("Example: python3 chat.py send hal george \"Handoff ready\"")
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    if command == 'send':
        handle_send(args)
    elif command == 'poll':
        handle_poll(args)
    elif command == 'status':
        handle_status(args)
    elif command == 'broadcast':
        handle_broadcast(args)
    elif command == 'history':
        handle_history(args)
    else:
        print(f"Unknown command: {command}")
        print("Valid: send, poll, status, broadcast, history")

if __name__ == "__main__":
    main()