#!/bin/sh
# Serve Ollama on the Space port, then load the model into GPU memory so the first reply after a wake-up is quick.
set -eu
mkdir -p "$HOME"
ollama serve &
server=$!
for i in $(seq 1 120); do ollama list >/dev/null 2>&1 && break; sleep 1; done
ollama run llama3.2:3b "" >/dev/null 2>&1 || echo "Preloading llama3.2:3b failed; it loads on the first request." >&2
wait "$server"
