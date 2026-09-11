# ECHO standalone final

This release accompanies the thesis **A Conversational System for Generating Emotionally Coherent Responses in Text and Speech Modalities**. It preserves the latest Hugging Face interface and 45-clip study while providing an independent installation.

## Start locally

1. Extract the whole archive, preserving the folder structure. Keep at least 4 GB free for extraction and temporary files.
2. Install Node.js 24 LTS from https://nodejs.org/en/download and use current desktop Chrome or Edge.
3. Open a terminal in ECHO_STANDALONE_FINAL and run:

```sh
node scripts/verify.mjs
node scripts/setup.mjs
node server/start.mjs
```

Save the newly generated researcher password privately. Setup is required only once per installation. Open **http://127.0.0.1:8787/**. Keep the terminal open; stop with Ctrl+C. Later starts need only the final command. Windows, macOS and Linux launchers are also included. Opening an HTML file directly does not start the application.

Listening and browser Kokoro use bundled files. Explore needs Ollama on the same computer with `llama3.2:3b` pulled (`ollama pull llama3.2:3b`); the server reaches it at `ECHO_OLLAMA_URL` (default `http://127.0.0.1:11434`). The coherence gate stays off unless `ECHO_COHERENCE_GATE=on` is set and `python gate_service.py` runs from the ECHO repository root. The prebuilt `dist/client` predates this change: rebuild it with `pnpm build`. The larger Python voices require the separate setup below. No GPT/OpenAI account, author's login or original computer is required.

## What each mode does

- Listening gives every new participant all 45 unique frozen clips. It records valence, arousal, naturalness and target match, with breaks after 15 and 30. Confirm 45/45 database receipt. Older 27-clip sessions retain a separate version.
- Test offers five engines. The required application procedure covers all four targets and one neutral per engine: 25 messages. Kokoro works in the browser; the other four require Python.
- Explore offers three engines, one per conversation and up to ten successful exchanges. The required study block is 12 fresh conversations: three engines by four targets, one reply per cell.

Read the in-app listener instructions. The external text/relevance/agreement sheet complements the four voice scales; its extra answers are not website database fields.

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

## Source and research materials

- thesis/ECHO_Thesis_EN.docx is the current English master manuscript; Markdown and figures accompany it.
- research-bundle/current-phase contains the amended full-coverage protocol and exact-WAV evidence.
- research-bundle/full-acoustic contains physical measurements, SER/UTMOS outputs, diagnostic transformations, scripts and interpretation notes.
- research-bundle/analyse_ratings.py validates the 45-clip cohort and computes participant-level H1/H2.
- deployment/huggingface contains the current hosting code and a packaging script for a recipient's own Space.
- docs/archive preserves older documents as history. Use these current instructions for installation; archived statements about 27 clips, Sites/D1 or earlier modes are superseded.

The main application serves only public and dist/client. Never publish thesis, research-bundle, data, backups or the private analysis key as a public static folder. The professor can inspect these files privately; the study participant should not see the configuration key before Listening.

Human findings and institutional information in the thesis remain marked for completion. Final in the archive name identifies the software handover, not completed human evaluation.
