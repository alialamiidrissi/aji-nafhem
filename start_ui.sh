#!/usr/bin/env bash
# Start both the FastAPI backend and Next.js frontend.
# Run from the project root.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Override with e.g.: RUNS_DIR=/path/to/runs ./start_ui.sh
export RUNS_DIR="${RUNS_DIR:-$SCRIPT_DIR/agentic_video_gen/runs}"

echo "🚀 Starting FastAPI backend on http://localhost:8080 ..."
echo "   RUNS_DIR: $RUNS_DIR"
conda run --no-capture-output -n audio_tts env RUNS_DIR="$RUNS_DIR" python web_server.py &
BACKEND_PID=$!

echo "🌐 Starting Next.js frontend on http://localhost:3000 ..."
cd web_ui && npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Both servers running."
echo "   Backend:  http://localhost:8080"
echo "   Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT TERM
wait
