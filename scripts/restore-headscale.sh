#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ $(id -u) -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
[[ $# -eq 1 ]] || { echo "Usage: $0 RESTIC_SNAPSHOT_ID" >&2; exit 1; }
source /etc/dfc/restic.env
TMP=$(mktemp -d /var/tmp/dfc-restore.XXXXXXXX)
trap 'rm -rf -- "$TMP"' EXIT
restic restore "$1" --target "$TMP"
ROOT=$(find "$TMP" -type f -path '*/data/db.sqlite' -print -quit)
[[ -n "$ROOT" ]] || { echo 'DB absent' >&2; exit 1; }
ROOT=${ROOT%/data/db.sqlite}
[[ -s "$ROOT/data/noise_private.key" && -s "$ROOT/data/derp_server_private.key" ]] || exit 1
[[ "$(sqlite3 "$ROOT/data/db.sqlite" 'PRAGMA quick_check;')" == ok ]]
cd /opt/sovereign-family-cloud
docker compose stop headscale
install -d -m 0700 /var/lib/dfc-headscale
cp -a "$ROOT/data/db.sqlite" "$ROOT/data/"*.key /var/lib/dfc-headscale/
chmod 0600 /var/lib/dfc-headscale/db.sqlite /var/lib/dfc-headscale/*.key
# Configs are deliberately NOT overwritten automatically; inspect and
# restore separately to avoid replacing live DNS, domain and credentials.
docker compose up -d headscale
