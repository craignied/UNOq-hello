#!/usr/bin/env bash
# Run this Arduino app on the UNO Q as your OWN user — no `arduino` user, no App Lab,
# no copying files around.
#
#   ./run.sh          import this repo and start it (build -> flash MCU -> run)
#   ./run.sh stop     stop the running app
#
# It drives the arduino-app-cli daemon on 127.0.0.1:8800, which owns the app copy and
# the build directory, so none of the file-permission problems of the (arduino-only)
# `arduino-app-cli app start <path>` command apply. The app keeps running after this
# script exits — it's a docker container managed by the daemon.
set -euo pipefail

DAEMON="${DAEMON:-http://127.0.0.1:8800}"
NS="${NS:-user}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The daemon derives the app slug from the zip's filename, so we control it here.
SLUG="${SLUG:-$(basename "$APP_DIR")}"                 # app id is  <NS>:<SLUG>
ID="$(printf '%s:%s' "$NS" "$SLUG" | base64 | tr -d '=')"

status() { curl -s "$DAEMON/v1/apps/$ID" \
             | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status","?"))' 2>/dev/null; }

case "${1:-start}" in
  start)
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    ( cd "$APP_DIR" && zip -qr "$tmp/$SLUG.zip" app.yaml python sketch )
    echo "Importing '$SLUG'..."
    curl -sf -X POST "$DAEMON/v1/apps/import?namespace=$NS&overwrite=true" \
         -F "file=@$tmp/$SLUG.zip" >/dev/null
    echo "Starting (build -> flash MCU -> run). First run takes a few minutes:"
    curl -sN -X POST "$DAEMON/v1/apps/$ID/start" | sed -u -n 's/^data: //p'
    echo "--- app status: $(status) (keeps running; './run.sh stop' to stop) ---"
    ;;
  stop)
    echo "Stopping '$SLUG'..."
    curl -sN -X POST "$DAEMON/v1/apps/$ID/stop" | sed -u -n 's/^data: //p'
    echo "--- app status: $(status) ---"
    ;;
  *)
    echo "usage: $0 [start|stop]" >&2; exit 2 ;;
esac
