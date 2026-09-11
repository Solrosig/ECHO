#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ ! -f data/researcher.json ]; then node scripts/setup.mjs || exit 1; fi
exec node server/start.mjs
