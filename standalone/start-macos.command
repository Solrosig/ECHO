#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v node >/dev/null 2>&1; then
  echo "Install Node.js 24 LTS, reopen Terminal, and try again."
  read -r _echo_wait
  exit 1
fi
if [ ! -f data/researcher.json ]; then node scripts/setup.mjs || exit 1; fi
node server/start.mjs
read -r _echo_wait
