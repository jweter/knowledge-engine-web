#!/bin/sh
# Start the private Ollama service and ensure the configured research model is
# present on the persistent model disk before declaring the process durable.

set -eu

model="${OLLAMA_MODEL:-qwen2.5:1.5b}"
export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-/var/data/models}"

mkdir -p "$OLLAMA_MODELS"

ollama serve &
server_pid=$!

cleanup() {
  kill "$server_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Wait for the local API before asking it to inspect/pull model state.
while ! ollama list >/dev/null 2>&1; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    wait "$server_pid"
    exit $?
  fi
  sleep 1
done

if ! ollama show "$model" >/dev/null 2>&1; then
  ollama pull "$model"
fi

# The model may be unloaded between requests; OLLAMA_MODELS persists the
# artifact so restarts/redeploys do not re-download it.
wait "$server_pid"
