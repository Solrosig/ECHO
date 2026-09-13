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

Independent installation of ECHO with 45-clip Listening, Test and Explore. Mount a PRIVATE bucket at /data and use one replica. Before the first launch, add the Space secret `ECHO_ADMIN_PASSWORD` (16–256 characters); only its salted hash is stored. Kokoro runs on the listener device; other speech uses the Python service, which loads the four server voices the website offers (Chatterbox, StyleTTS2, CosyVoice2 and Parler-TTS; `ECHO_ENGINES` overrides this). Explore replies need the conversation model set up as described below. Local SQLite is checkpointed to verified private snapshots before successful research-write acknowledgement. Conversation-reply metrics (`dialogue-metrics.jsonl`: each reply's time, latency and any failure) are kept beside them in `metrics/` as append-only pieces, so they survive restarts and sleep; researchers download them from `/api/research/dialogue-metrics.jsonl`. Preserve licences in backend.zip. Set your retention and backup-erasure policy before recruitment. See the parent distribution deployment guide for setup and limitations.

## Conversation model

Explore replies come from Ollama with `llama3.2:3b`, build `a80c4f17acd5`, the build ECHO's prompt was tested with. The Space variable `ECHO_LLM_MODE` chooses where it runs. `configure_space.py` applies a variant, and only prints its plan unless given `--apply`.

- `embedded` (variant a, one Space): this Space downloads the pinned Ollama and model at startup and runs them beside the voices.
  - **On ZeroGPU (the default):** the model runs on the Space's CPU and costs nothing. Ollama cannot use a ZeroGPU GPU, which exists only inside `@spaces.GPU` calls.
  - **On paid GPU hardware** such as `t4-small`: the model uses the GPU. Set a sleep time.
  - **Threads:** the model uses one CPU thread per CPU the container may use, because llama.cpp otherwise starts one per core of the whole host (96 on the ZeroGPU host). The count is set through `llama3.2:3b-t<threads>`, a copy of the verified build that adds only the `num_thread` parameter. `ECHO_OLLAMA_THREADS` sets the count. Extra weight buffers are off (`LLAMA_ARG_REPACK=0`), because on the ZeroGPU host the model's first computation never finished with its weights in AMX buffers.
  - **Sleep and wake:** the whole site sleeps and restarts together, and each wake-up downloads Ollama and the model again. Until the model answers, Explore tells participants it is starting and keeps trying.
  - **GPU memory:** Ollama leaves 2 GiB of GPU memory to the voices (`ECHO_OLLAMA_GPU_OVERHEAD`, in bytes) and runs some layers on the CPU when the GPU is too small.
- `remote` (variant b, split): this Space stays on ZeroGPU, and `../huggingface-llm` runs as a private Docker Space on paid hardware with a short sleep time. Set the variable `ECHO_OLLAMA_URL` to its address and the secret `ECHO_OLLAMA_TOKEN` to a token that can only read it. The website wakes it when someone opens Explore.
- `off` (default): no conversation replies; Listening and Test work normally.

## Server voices and ZeroGPU quota

ZeroGPU counts GPU time against whoever calls the Space, and a visitor without a Hugging Face account gets about 3 voices a day.

Add the Space secret `ECHO_ZEROGPU_TOKEN`: a fine-grained token of the Space owner with no permissions. With it:

- The website's server relays every voice request to `/api/tts-gpu` through the Space's public address, carrying that token, so ZeroGPU counts the voice against the owner's quota (PRO: 40 minutes a day, then credits).
- A random key chosen at each start lets only those relayed requests reach Gradio, which stays at `/api/tts`.
- The token never reaches the browser.
- Voice requests are limited per network (`ECHO_TTS_REQUESTS_PER_10_MIN`, default 120) and, with the token, per day for everyone (`ECHO_TTS_REQUESTS_PER_DAY`, default 600).
- Each voice reserves 25–60 s of GPU time, depending on its text length.

Built with Llama. Llama 3.2 is licensed under the Llama 3.2 Community License, Copyright © Meta Platforms, Inc. All Rights Reserved. Licence: https://www.llama.com/llama3_2/license/. The Explore page shows "Built with Llama" with a link to the licence.

## Deploying

Build the upload folder with `python package_space.py --refs-from <an earlier backend.zip>` after `pnpm build`.

The Space builds and serves only `main`. Its other branches and tags are never run.

- `staging`: upload the package here first and check its files. The site does not change.
- `main`: then upload the same package here, titled `Deploy ECHO dev <commit> (<GitHub tag>)`. The Space rebuilds and restarts with it.
- Tags: each deployment on `main` carries the name of the GitHub tag it was built from. To return to that version, upload the files at its tag to `main` again.
