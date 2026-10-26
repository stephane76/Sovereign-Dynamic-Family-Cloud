#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PROJECT_DIR="${PROJECT_DIR:-/opt/sovereign-family-cloud}"
SECRETS_FILE=/etc/dfc/restic.env
[[ $(id -u) -eq 0 ]] || { echo 'Run as root' >&2; exit 1; }
[[ -r "$SECRETS_FILE" ]] || { echo "Missing $SECRETS_FILE" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; source "$SECRETS_FILE"; set +a
: "${RESTIC_REPOSITORY:?}" "${RESTIC_PASSWORD_FILE:?}"
command -v restic >/dev/null; command -v sqlite3 >/dev/null
[[ -s /var/lib/dfc-headscale/db.sqlite ]] || { echo 'No headscale DB' >&2; exit 1; }
[[ -s /var/lib/dfc-headscale/noise_private.key ]] || { echo 'No Noise key' >&2; exit 1; }
[[ -s /var/lib/dfc-headscale/derp_server_private.key ]] || { echo 'No DERP key' >&2; exit 1; }
TMP=$(mktemp -d /var/tmp/dfc-backup.XXXXXXXX)
cleanup(){ rm -rf -- "$TMP"; }
trap cleanup EXIT
install -d -m 0700 "$TMP/data" "$TMP/configs"
sqlite3 /var/lib/dfc-headscale/db.sqlite ".backup '$TMP/data/db.sqlite'"
[[ "$(sqlite3 "$TMP/data/db.sqlite" 'PRAGMA quick_check;')" == ok ]]
cp -a /var/lib/dfc-headscale/*.key "$TMP/data/"
cp -a "$PROJECT_DIR/configs/headscale/" "$TMP/configs/headscale"
cp -a "$PROJECT_DIR/configs/traefik/" "$TMP/configs/traefik"
cp -a "$PROJECT_DIR/docker-compose.yml" "$TMP/configs/docker-compose.yml"
# restic encrypts and authenticates content; staging remains root-only and
# is erased by the trap even if backup fails.
restic backup "$TMP" --tag dfc-headscale
restic forget --tag dfc-headscale --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
