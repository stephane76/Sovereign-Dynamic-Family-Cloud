#!/usr/bin/env bash
set -Eeuo pipefail
cd /opt/sovereign-family-cloud
sudo docker compose config --quiet
sudo docker compose run --rm --no-deps headscale configtest
sudo docker compose ps
sudo docker compose logs --tail=30 headscale traefik
curl -fsSIL https://headscale.yourfamily.eu/ | head -n 12 || true
sudo tailscale status || true
sudo ss -lntup | grep -E ':(22|80|443|3478)\b' || true
