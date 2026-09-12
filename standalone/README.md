# ECHO standalone final

This release accompanies the thesis **A Conversational System for Generating Emotionally Coherent Responses in Text and Speech Modalities**. It preserves the latest Hugging Face interface and 45-clip study while providing an independent installation.

## Start locally

1. Extract the whole archive, preserving the folder structure. Keep at least 4 GB free for extraction and temporary files.
2. Install Node.js 24 LTS from https://nodejs.org/en/download and use current desktop Chrome or Edge.
3. Open a terminal in the `standalone` folder (`ECHO_STANDALONE_FINAL` in the release archive) and run:

```sh
node scripts/verify.mjs
node scripts/setup.mjs
node server/start.mjs
```

`verify.mjs` checks an extracted 1.5.0 archive. In a checkout of the ECHO repository it stops at the first file changed since that release; skip it there.

Save the newly generated researcher password privately. Setup is required only once per installation. Open **http://127.0.0.1:8787/**. Keep the terminal open; stop with Ctrl+C. Later starts need only the final command. Windows, macOS and Linux launchers are also included. Opening an HTML file directly does not start the application.

Listening and browser Kokoro use bundled files. Explore needs Ollama on the same computer with `llama3.2:3b` pulled (`ollama pull llama3.2:3b`); the server reaches it at `ECHO_OLLAMA_URL` (default `http://127.0.0.1:11434`). The coherence gate stays off unless `ECHO_COHERENCE_GATE=on` is set and `python gate_service.py` runs from the ECHO repository root. The prebuilt `dist/client` predates this change: rebuild it with `pnpm build`. The larger Python voices require the setup under Python voices below. No GPT/OpenAI account, author's login or original computer is required.

## What each mode does

- Listening gives every new participant all 45 unique frozen clips. It records valence, arousal, naturalness and target match, with breaks after 15 and 30. Confirm 45/45 database receipt. Older 27-clip sessions retain a separate version.
- Test offers five engines. The required application procedure covers all four targets and one neutral per engine: 25 messages. Kokoro works in the browser; the other four require Python.
- Explore offers three engines, one per conversation and up to ten successful exchanges. The required study block is 12 fresh conversations: three engines by four targets, one reply per cell.

Read the in-app listener instructions. The external text/relevance/agreement sheet complements the four voice scales; its extra answers are not website database fields.

## Python voices

Chatterbox, StyleTTS2, CosyVoice2, Parler-TTS and ZipVoice run in the Python service in `tts-service`; Kokoro does not use it. Use Python 3.10 or 3.11 in its own virtual environment. On Linux, first install `ffmpeg`, `libsndfile1`, `espeak-ng`, `git` and a C/C++ build toolchain; on Windows, use WSL2. The first start downloads several gigabytes of pinned model weights (allow 20 GB free), and an NVIDIA GPU is recommended.

```sh
python3 -m venv .tts-venv
source .tts-venv/bin/activate
python -m pip install -r tts-service/requirements.txt
ECHO_TTS_ROOT_PATH=/api/tts python tts-service/app.py
```

Keep it running and start the website as usual. The website forwards `/api/tts` to `http://127.0.0.1:7860`; set `ECHO_TTS_URL` for another service address, without `/api/tts`. `ECHO_ENGINES=chatterbox,zipvoice` loads a subset of engines. Model revisions are pinned in `tts-service/models.lock.json`.

## Researcher access

The latest frontend hides the research page. Collection and authenticated exports remain implemented. To restore the researcher interface in your own installation, set SHOW_RESEARCH_PAGE to true in frontend-visibility.js, rebuild as below and restart. Open /research and enter the locally generated password. SHOW_ENGINE_CONTROLS_SECTION separately controls the explanatory voice-mechanism section.

```sh
npm install --global pnpm@10.32.1
pnpm install --frozen-lockfile
pnpm build
node server/start.mjs
```

Rebuilding deliberately changes release hashes. Run the shipped integrity check before edits; create a new manifest only after reviewing your changes. Keep the original archive as the reference release.

Use /listen?test=1 for technical rehearsals. Such records are labelled technical_test and excluded from the primary human analysis. Do not use invented ratings as human findings. Export raw human CSVs privately and keep study versions separate.

## Database and backup

The local installation creates data/study.sqlite and data/audio on first use. Nothing in data is shipped. Researcher credentials are generated locally and stored as a salted hash.

```sh
node scripts/backup.mjs
```

Keep the resulting SQLite file, .manifest.json and any .audio companion together. Restore with the server stopped: place the database at data/study.sqlite and the companion contents at data/audio. Remove stale SQLite WAL/SHM files only as part of a controlled restore with the server stopped. Do not overwrite researcher credentials unless intentionally restoring them. Test a backup in a separate installation before relying on it.

Deleting an active participant session does not automatically erase historical backups. Define retention and backup erasure before recruitment.

## Listener export

`scripts/export-listeners.mjs` turns a database copy into one folder per listener, for analysis outside the app:

- `<listener code>/listener.json`: the listener's nicknames and sessions in time order.
- `<listener code>/listening-test/`, `test-mode/` and `explore-mode/`: one folder per session, named by its first save time and session ID, for example `2026-09-12T10-27-10Z_X-…`.
- Each session folder holds `metadata.json`:
  - times, listener code and nickname;
  - the clips or messages in order, with their ratings;
  - every play, pause, finish and seek of each voice, in the order it happened;
  - a summary of listening order and replays.
- Test and Explore session folders also hold their archived recordings as `01_<engine>_<emotion>.wav`, checked against their stored checksums.

The listener code is a random `L-…` code the browser keeps beside the nickname. It links one browser's Listening, Test and Explore sessions. A session without a code still gets a listener ID, and its metadata records how (`listener_id_source`):

- `nickname_match`: its nickname belongs to exactly one browser code, so it joins that listener.
- `nickname`: an internal `I-…` ID derived from the nickname, which listeners are asked to keep throughout their participation.
- `session`: the nickname is blank, or several listeners used it (more than one browser code, or more than one Listening session). The session gets an internal ID of its own.

Internal IDs are repeatable: exporting the same data again gives the same IDs. Technical test records are left out unless `--include-technical` is given.

From a local installation, export a copy made with `node scripts/backup.mjs`:

```
node scripts/export-listeners.mjs --database backups/<backup>.sqlite --audio backups/<backup>.sqlite.audio --out <new folder>
```

From the Hugging Face research bucket, after downloading it with `hf buckets sync`:

```
node scripts/export-listeners.mjs --bucket <download>/echo --out <new folder>
```

The export contains personal data: nicknames, typed messages, voices and listening behaviour. Keep it private and out of this repository.

## Hosting limits

Behind a reverse proxy (Caddy in `compose.production.yaml`, or the Hugging Face host), set `ECHO_TRUST_PROXY=1` so that login attempts and these limits count each visitor rather than the proxy. Per network address, the server accepts 120 voice-synthesis requests and 120 conversation replies per 10 minutes (`ECHO_TTS_REQUESTS_PER_10_MIN`, `ECHO_DIALOGUE_REPLIES_PER_10_MIN`) and 300 new sessions or conversations per hour (`ECHO_SESSIONS_PER_HOUR`); resuming a session does not count. Archived conversation recordings are capped at 2048 MB in total (`ECHO_AUDIO_QUOTA_MB`). Raise these for a lab where many participants share one address. The Hugging Face host serves the voices directly, so its Gradio queue limits apply there instead.

A remote Ollama, such as a private Hugging Face Space that sleeps when unused, is set with `ECHO_OLLAMA_URL` and `ECHO_OLLAMA_TOKEN` (sent as a Bearer header). While it wakes up, Explore says the conversation model is starting and keeps trying for up to four minutes. `deployment/huggingface/README.md` describes the two hosted variants.

## Run with Docker

`compose.yaml` builds the website inside the image and keeps the database in a Docker volume. Create the researcher password once, then start:

```sh
docker compose build
docker compose run --rm echo node scripts/setup.mjs
docker compose up -d
```

Open **http://127.0.0.1:8787/**. Ollama and the Python voices run outside the container, which reaches them at `host.docker.internal` on ports 11434 and 7860. Ollama must therefore listen beyond loopback (`OLLAMA_HOST=0.0.0.0`, with port 11434 firewalled), or set `ECHO_OLLAMA_URL` and `ECHO_TTS_URL` to other addresses. The image serves the files in `public` at build time, and the Kokoro model weights are not in the repository: restore `public/models` from the release archive before building. For HTTPS, `compose.production.yaml` adds Caddy; run the same commands with `--env-file .env.hosting -f compose.production.yaml`, where `.env.hosting` sets `ECHO_DOMAIN`.

## Source and research materials

In the ECHO repository, `thesis`, `docs`, `research-bundle/full-acoustic` and `research-bundle/analyse_ratings.py` are not included yet; they are in the release archive.

- thesis/ECHO_Thesis_EN.docx is the current English master manuscript; Markdown and figures accompany it.
- research-bundle/current-phase contains the amended full-coverage protocol and exact-WAV evidence.
- research-bundle/full-acoustic contains physical measurements, SER/UTMOS outputs, diagnostic transformations, scripts and interpretation notes.
- research-bundle/analyse_ratings.py validates the 45-clip cohort and computes participant-level H1/H2.
- deployment/huggingface contains the current hosting code and a packaging script for a recipient's own Space.
- docs/archive preserves older documents as history. Use these current instructions for installation; archived statements about 27 clips, Sites/D1 or earlier modes are superseded.

The main application serves only public and dist/client. Never publish thesis, research-bundle, data, backups or the private analysis key as a public static folder. The professor can inspect these files privately; the study participant should not see the configuration key before Listening.

Human findings and institutional information in the thesis remain marked for completion. Final in the archive name identifies the software handover, not completed human evaluation.
