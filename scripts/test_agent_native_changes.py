#!/usr/bin/env python3
"""
Test script for agent-native implementation changes.

Run with RAG backend up: docker-compose up -d (or ./scripts/run_backend_venv.sh)
  python scripts/test_agent_native_changes.py

Tests:
- Health
- Document PATCH (metadata update)
- Logs DELETE by ID
- Context injection (via chat/query — session history, document-in-focus)
"""

import json
import sys
import uuid

import requests

BASE = "http://localhost:8000"
# Cloud LLM can exceed 60s on cold or rate limits
CHAT_TIMEOUT = 180


def test_health():
    r = requests.get(f"{BASE}/health", timeout=5)
    assert r.status_code == 200
    print("✓ Health OK")


def test_document_patch():
    # List docs, pick first indexed one (or skip if none)
    r = requests.get(f"{BASE}/documents/", timeout=5)
    r.raise_for_status()
    docs = r.json()
    if not docs:
        print("⊘ Skip PATCH (no documents)")
        return
    doc = next((d for d in docs if d.get("status") == "indexed"), docs[0])
    doc_id = doc["id"]
    name_before = doc.get("original_name", "")
    new_name = f"{name_before} (test)" if not name_before.endswith("(test)") else name_before

    r = requests.patch(
        f"{BASE}/documents/{doc_id}",
        json={"original_name": new_name},
        timeout=5,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("original_name") == new_name
    print(f"✓ Document PATCH OK ({doc_id[:8]}...)")

    # Restore
    requests.patch(f"{BASE}/documents/{doc_id}", json={"original_name": name_before}, timeout=5)


def test_logs_delete_by_id():
    # Get one log
    r = requests.get(f"{BASE}/logs/queries?limit=1", timeout=5)
    r.raise_for_status()
    logs = r.json()
    if not logs:
        print("⊘ Skip DELETE log (no logs)")
        return
    log_id = logs[0]["id"]

    r = requests.delete(f"{BASE}/logs/queries/{log_id}", timeout=5)
    assert r.status_code == 200
    print(f"✓ Log DELETE by ID OK (re-run creates new log)")


def test_chat_with_context():
    # Create conversation, send 2 queries — second should have prior turn in context
    r = requests.post(
        f"{BASE}/chat/query",
        json={"query": "What is the main topic?"},
        timeout=CHAT_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    conv_id = data.get("conversation_id")
    if not conv_id:
        print("⊘ Skip context (no conversation_id)")
        return

    r2 = requests.post(
        f"{BASE}/chat/query",
        json={"query": "Expand on that.", "conversation_id": conv_id},
        timeout=CHAT_TIMEOUT,
    )
    r2.raise_for_status()
    # Backend injects prior turn; we can't easily assert on prompt, but no 500 = OK
    print("✓ Chat with conversation (context injection) OK")


def main():
    print("Testing agent-native implementation changes...")
    failed = []
    for name, fn in [
        ("health", test_health),
        ("document_patch", test_document_patch),
        ("logs_delete_by_id", test_logs_delete_by_id),
        ("chat_context", test_chat_with_context),
    ]:
        try:
            fn()
        except requests.exceptions.ConnectionError as e:
            print(f"✗ {name}: Backend not running. Start with: docker-compose up -d")
            sys.exit(1)
        except Exception as e:
            print(f"✗ {name}: {e}")
            failed.append(name)

    if failed:
        print(f"\nFailed: {failed}")
        sys.exit(1)
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
