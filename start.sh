#!/usr/bin/env bash
set -euo pipefail

: "${PORT:=8000}"
: "${BRIDGE_PORT:=8080}"
: "${BRIDGE_STORE_DIR:=/app/whatsapp-bridge/store}"

mkdir -p "$BRIDGE_STORE_DIR" /tmp/whatsapp-api-uploads

export MESSAGES_DB_PATH="${MESSAGES_DB_PATH:-$BRIDGE_STORE_DIR/messages.db}"
export WHATSAPP_API_BASE_URL="${WHATSAPP_API_BASE_URL:-http://localhost:${BRIDGE_PORT}/api}"

echo "Starting WhatsApp bridge on port ${BRIDGE_PORT}..."
/app/whatsapp-bridge/whatsapp-bridge &
bridge_pid=$!

echo "Waiting briefly for bridge health..."
for i in $(seq 1 10); do
  if curl -sf --max-time 2 "http://localhost:${BRIDGE_PORT}/health" >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl -sf --max-time 2 "http://localhost:${BRIDGE_PORT}/health" >/dev/null; then
  echo "Bridge health not ready yet; continuing to start API."
fi

cd /app/whatsapp-mcp-server
echo "Starting API on port ${PORT}..."
python -c "import sys; print('Python:', sys.version)" || true
python -c "import uvicorn; print('Uvicorn:', uvicorn.__version__)" || true
exec python -m uvicorn api:app --host 0.0.0.0 --port "${PORT}" --log-level info
