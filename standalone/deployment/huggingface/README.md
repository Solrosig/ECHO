---
title: ECHO — Emotion in Voice
emoji: 🎙️
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 5.49.1
python_version: 3.10.13
app_file: app.py
pinned: false
---

# ECHO conversational system

Independent installation of ECHO with 45-clip Listening, Test and Explore. Mount a PRIVATE bucket at /data and use one replica. Before the first launch, add the Space secret `ECHO_ADMIN_PASSWORD` (16–256 characters); only its salted hash is stored. Kokoro runs on the listener device; other speech uses the Python service. Explore replies need the conversation model set up as described below. Local SQLite is checkpointed to verified private snapshots before successful research-write acknowledgement. Preserve licences in backend.zip. Set your retention and backup-erasure policy before recruitment. See the parent distribution deployment guide for setup and limitations.

## Conversation model

Explore replies come from Ollama with `llama3.2:3b`, build `a80c4f17acd5`, the build ECHO's prompt was tested with. The Space variable `ECHO_LLM_MODE` chooses where it runs. `configure_space.py` applies a variant, and only prints its plan unless given `--apply`.

- `embedded` (variant a, one Space): this Space downloads the pinned Ollama and model at startup and runs them beside the voices. Use paid GPU hardware such as `t4-small` with a sleep time. The whole site sleeps and restarts together, and each wake-up downloads Ollama and the model again.
- `remote` (variant b, split): this Space stays on ZeroGPU, and `../huggingface-llm` runs as a private Docker Space on paid hardware with a short sleep time. Set the variable `ECHO_OLLAMA_URL` to its address and the secret `ECHO_OLLAMA_TOKEN` to a token that can only read it. The website wakes it when someone opens Explore.
- `off` (default): no conversation replies; Listening and Test work normally.

Build the upload folder with `python package_space.py --refs-from <an earlier backend.zip>` after `pnpm build`.
