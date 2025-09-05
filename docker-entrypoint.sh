#!/usr/bin/env sh
set -e

CLI="${STORYCRAFTR_CLI:-storycraftr}"
BOOKS_DIR="${BOOKS_CONTAINER_DIR:-/workspace/books}"
START_UI="${START_UI:-false}"
GRADIO_PORT="${GRADIO_PORT:-7860}"
GRADIO_HOST="${GRADIO_HOST:-0.0.0.0}"

# Ensure StoryCraftr config directory exists
mkdir -p /root/.storycraftr

# If an API key is provided via env, write it to the expected file for the CLI
if [ -n "$OPENAI_API_KEY" ]; then
  printf "%s" "$OPENAI_API_KEY" > /root/.storycraftr/openai_api_key.txt
fi

# Ensure mounted books directory exists
mkdir -p "$BOOKS_DIR"

if [ "$START_UI" = "true" ]; then
  # Start Gradio UI
  exec python -m storycraftr.gradio_app --server-name "$GRADIO_HOST" --server-port "$GRADIO_PORT"
fi

# Execute the chosen CLI with any passed arguments
exec "$CLI" "$@"
