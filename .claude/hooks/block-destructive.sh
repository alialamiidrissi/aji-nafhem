#!/bin/bash
# PreToolUse hook — blocks destructive shell commands and asks Claude to get
# explicit user confirmation before proceeding.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if echo "$COMMAND" | grep -qE '(^|[;&|])\s*(rm|rmdir|shred|dd|truncate)\s'; then
  echo ""
  echo "🚫 DESTRUCTIVE COMMAND BLOCKED"
  echo "   Command: $COMMAND"
  echo ""
  echo "   You must ask the user for explicit confirmation before running any"
  echo "   rm / rmdir / shred / dd / truncate command."
  echo "   Do NOT retry automatically — wait for the user to approve."
  echo ""
  exit 2
fi

exit 0
