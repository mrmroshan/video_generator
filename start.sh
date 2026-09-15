#!/usr/bin/env bash
# start.sh — Start the Video Maker Review Dashboard (API + UI)
# Usage: bash start.sh

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "🎬 Video Maker Dashboard"
echo ""

# Start FastAPI backend on port 8001
echo "▶ Starting API server on http://localhost:8001 ..."
cd "$ROOT"
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8001 &
API_PID=$!

# Wait for API to be ready (up to 10s)
for i in {1..10}; do
  sleep 1
  if curl -s http://localhost:8001/jobs > /dev/null 2>&1; then
    echo "  ✓ API ready"
    break
  fi
done

# Start Vite frontend
echo "▶ Starting dashboard UI on http://localhost:5173 ..."
cd "$ROOT/dashboard"
npm run dev &
UI_PID=$!

echo ""
echo "✅ Dashboard running:"
echo "   UI  → http://localhost:5173"
echo "   API → http://localhost:8001/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Wait for both
wait $API_PID $UI_PID
