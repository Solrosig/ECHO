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

Independent installation of ECHO with 45-clip Listening, Test and Explore. Mount a PRIVATE bucket at /data and use one replica. Before the first launch, add the Space secret `ECHO_ADMIN_PASSWORD` (16–256 characters); only its salted hash is stored. Kokoro runs on the listener device; other speech uses the Python service. Explore replies need an Ollama server with `llama3.2:3b` reachable at `ECHO_OLLAMA_URL`; a Space has none by default. Local SQLite is checkpointed to verified private snapshots before successful research-write acknowledgement. Preserve licences in backend.zip. Set your retention and backup-erasure policy before recruitment. See the parent distribution deployment guide for setup and limitations.
