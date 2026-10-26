# Dynamic Family Cloud — Guide 2/3
## Configuring the VPS, retrieving the GitHub repository and deploying services

**Edition: October 21, 2026 · Based on the actual OVHcloud deployment**

> **Key separation:** templates and scripts are tracked on GitHub; `.env`, private keys, generated active configuration and persistent Docker data stay on the VPS. The repository is `stephane76/Sovereign-Dynamic-Family-Cloud`, while the local directory is intentionally named `$HOME/sovereign-cloud`.

## 1. Deployed architecture

```text
Internet
  │ HTTPS 443 / HTTP 80
  ▼
OVHcloud VPS — Debian 12
  ├─ Traefik 3.7.16      Actalis ACME TLS (~90-day certificates) — tested
  ├─ Headscale 0.29.5   Mesh control plane + embedded DERP / STUN UDP 3478
  ├─ FastAPI Admission  Ed25519 identity verification → Headscale auth key
  └─ Host Tailscale     tag:vps node

Homes in BE / ES / other sites: gateways and storage — later stages.
```

Example hostnames are `headscale.YOUR_DOMAIN` and `enroll.YOUR_DOMAIN`. `cloud.YOUR_DOMAIN` is reserved for future **TCP SNI passthrough with TLS termination at home**, not on the public VPS. Do not enable passthrough until a real home gateway is available and tested.

## 2. Install prerequisites

Observed host versions were Docker Engine 29.9.1, Docker Compose v5.6.0 and Tailscale 1.104.1; these are **observations, not minimum requirements**. Follow the official [Docker Engine on Debian](https://docs.docker.com/engine/installation/debian/) and [Tailscale on Debian Bookworm](https://tailscale.com/docs/install/debian/debian-bookworm) instructions.

```bash
git --version
sudo docker --version
sudo docker compose version
tailscale version
```

Do not run `tailscale up` against an unrelated login server if this host is already enrolled in Headscale.

## 3. Clone the public repository over HTTPS

A genuinely **public** GitHub repository is readable without an SSH private key or write access. Verify the repository is public and its history contains no secrets before publishing it. If it is private, readers cannot follow this public-clone step.

```bash
cd "$HOME"
git clone https://github.com/stephane76/Sovereign-Dynamic-Family-Cloud.git sovereign-cloud
cd sovereign-cloud
git status --short
```

To update a clean checkout:

```bash
git pull --ff-only origin main
```

## 4. Repository layout

```text
sovereign-cloud/
├── docker-compose.yml
├── .env.example                 public template
├── .env                         private, Git-ignored
├── admission/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── server.py
│   ├── manage.py
│   ├── test_client.py
│   └── .env.example / .env
├── configs/
│   ├── headscale/  config.yaml.example, derp.yaml.example, policy.hujson.example
│   └── traefik/    traefik.yml.example, dynamic templates
├── scripts/
│   ├── prepare-config.sh
│   ├── check.sh
│   ├── backup-headscale.sh
│   └── restore-headscale.sh
└── docs/
    └── part-2-control-plane/
        ├── README.md
        ├── 01_Guide_creation_VPS_OVH.md
        ├── 02_Guide_configuration_VPS_GitHub.md
        ├── 03_Guide_tests_validation.md
        └── tests/
            ├── test_admission_scenarios.py
            └── test_box_enrollment.py
```

The Admission Docker image must include **both** `server.py` and `manage.py`. Check for `COPY manage.py ./` in `admission/Dockerfile`.

## 5. Prepare private environment settings

Use the actual repository's `.env.example`; it defines the variables expected by `scripts/prepare-config.sh`.

```bash
cd "$HOME/sovereign-cloud"
cp -n .env.example .env
chmod 600 .env
nano .env
```

The reference configuration required values equivalent to:

```dotenv
DOMAIN=YOUR_DOMAIN
PUBLIC_IP=YOUR_VPS_IP
ACME_EMAIL=CONTACT_EMAIL
ACME_CA_SERVER=https://acme-api.actalis.com/acme/directory
ACME_EAB_KID=YOUR_ACTALIS_EAB_KID
ACME_EAB_HMAC=YOUR_ACTALIS_EAB_HMAC
```

The EAB HMAC must be encoded as **unpadded Base64URL**. If Actalis supplies standard Base64, **convert its representation** rather than Base64-encoding the encoded text again. Use credentials for an active **Actalis ACME plan**. An ACME `Not enough quota` response from `/acme/neworders` is an **account/quota-side rejection**; do not blindly alter DNS or keys.

Never disclose `.env`, EAB values, `/etc/dfc/headscale-api-key` or `/var/lib/dfc-acme/actalis.json`. Traefik may reuse an existing ACME account stored in the latter file even after changing EAB credentials; diagnose and preserve a secure backup before attempting account re-registration.

**Why Actalis?** The project deliberately uses an EU-based Italian CA for certificate issuance as part of its European service-provider strategy, instead of Let's Encrypt. That is an architectural supply-chain choice, **not** a guarantee that all dependencies or Internet paths are European.

## 6. Generate and validate active configuration

For a **fresh installation**, do **not** use `--force`:

```bash
cd "$HOME/sovereign-cloud"
bash scripts/prepare-config.sh
sudo docker compose config --quiet
```

Generated, untracked configuration includes:

```text
configs/headscale/config.yaml
configs/headscale/policy.hujson
configs/traefik/traefik.yml
configs/traefik/dynamic/headscale.yml
configs/traefik/dynamic/admission.yml
admission/.env
```

The generated Traefik YAML contains EAB secrets: keep its permissions restrictive (`0600`) and ensure it remains Git-ignored. Never overwrite a previously deployed active configuration with a template unintentionally. Use `--force` only for an intentional regeneration **after reviewing the consequences for all generated services**.

## 7. Prepare persistent volumes and Headscale API access

The reference deployment used UID/GID `11001` for Admission and persisted its SQLite state:

```bash
sudo install -d -m 0700 /etc/dfc
sudo install -d -m 0750 -o 11001 -g 11001 /var/lib/dfc-admission
sudo install -m 0640 -o root -g 11001 /dev/null /etc/dfc/headscale-api-key
```

**Validate Headscale config before starting it**, then check its policy on the running server:

```bash
sudo docker compose run --rm --no-deps headscale configtest
sudo docker compose up -d headscale
sudo docker compose exec headscale \
  headscale policy check --file /etc/headscale/policy.hujson
```

Create the Headscale API key **once** and store it without printing it:

```bash
sudo docker compose exec -T headscale headscale apikeys create --expiration 365d \
  | sudo tee /etc/dfc/headscale-api-key >/dev/null
```

`apikeys create` creates another secret. Do not repeat it at every deployment or overwrite an active secret. Use `docker compose exec`, not `run`, for `policy check`, which requires the running server.

## 8. Traefik 3.7 and HTTP header hardening — verified

The reference VPS migrated from `traefik:v3.6` to `traefik:v3.7`; the binary reported **3.7.16** on October 21, 2026. Existing Actalis certificates remained valid and both HTTPS routes worked. This does **not** yet establish that automatic certificate renewal works.

The tracked template `configs/traefik/traefik.yml.example` configures both `web` and `websecure` entry points with:

```yaml
http:
  aliasHeadersStrategy: reject
```

After regeneration and restart, a request carrying `X.Auth.User: test` returned **HTTP 400** at the Admission endpoint, while legitimate health requests still passed. Modify the template, **not** the generated YAML containing EAB credentials. Review changes before running `bash scripts/prepare-config.sh --force` on an existing deployment: it also regenerates Headscale and Admission configuration.

Use Traefik 3.7 directly on a new VPS. Preserve `/var/lib/dfc-acme/actalis.json` during upgrades; do not delete it.

### Headscale client-IP headers — optional, only if `trusted_proxies` includes Traefik

Not required with the published configuration: Headscale reads these headers only from proxies listed in `trusted_proxies`, which is empty by default ([Headscale v0.29.5 config-example.yaml](https://github.com/juanfont/headscale/blob/v0.29.5/config-example.yaml)) and not set in `configs/headscale/config.yaml.example`. Apply the middleware below only if you add Traefik's network to `trusted_proxies`.

Headscale documents that it trusts `True-Client-IP` **before** `X-Real-IP` and `X-Forwarded-For` when the TCP peer is a trusted proxy. The `aliasHeadersStrategy: reject` hardening above **does not remove a normal client-supplied `True-Client-IP` header**. See the [Headscale reverse-proxy instructions](https://headscale.net/stable/ref/integration/reverse-proxy/) and [Traefik 3.7 Headers middleware reference](https://doc.traefik.io/traefik/v3.7/reference/routing-configuration/http/middlewares/headers/)).

First, inspect `configs/traefik/dynamic.example/headscale.yml.example` and its active file for an existing header sanitation middleware. If absent, add the following to the **Headscale route's dynamic configuration template**, merging with any existing `http:` tree and preserving other middlewares and services:

```yaml
http:
  middlewares:
    remove-untrusted-client-ip:
      headers:
        customRequestHeaders:
          True-Client-IP: ""
  routers:
    headscale:
      # Retain the existing rule, service, entryPoints and TLS settings.
      middlewares:
        - remove-untrusted-client-ip
```

**Illustrative fragment, not a complete replacement file.** Use the *actual Headscale router name* from your template instead of assuming `headscale`; preserve any pre-existing middlewares. An empty `customRequestHeaders` value removes that header before forwarding. Also ensure Traefik's forwarded-header trust settings and Headscale's `trusted_proxies` match the real Docker network topology. If a trusted upstream proxy is introduced later, establish which component is responsible for setting a sanitized client IP.

After updating the template and intentionally regenerating active configuration, confirm Traefik loads it, that normal `/health` still passes, and **observe through a backend-side request/log test** that a forged `True-Client-IP` does not reach Headscale. A health-check HTTP 200 alone does **not** prove the header was stripped. **If you apply this change, do not mark it complete until this test passes.**

## 9. Start Traefik and Admission

```bash
sudo docker compose up -d --build traefik admission
sudo docker compose ps
sudo docker compose logs --tail=80 traefik
sudo docker compose logs --tail=80 admission
```

Actalis ACME directory: `https://acme-api.actalis.com/acme/directory`. The observed issuer was **Actalis Domain Validated TLS Server RSA CA 2025**. Both reference certificates were valid through January 20, 2027. Keep port 80 reachable for the configured HTTP-01 challenge. Do not add Let's Encrypt as an automatic fallback.

### Admission dependencies validated on October 21

The deployed image uses **FastAPI 0.142.2** and **Starlette 0.52.1**. `python -m pip check` found no broken requirements. The persistent registry survived the container replacement, `/healthz` passed, a valid Ed25519 admission succeeded and an unknown Box returned HTTP 403. The invalid-signature and replay tests were **not rerun after** the dependency upgrade; see Guide 3.

## 10. Check HTTPS services and certificates

```bash
curl -fsS https://headscale.YOUR_DOMAIN/health
curl -fsS https://enroll.YOUR_DOMAIN/healthz
for HOST in headscale.YOUR_DOMAIN enroll.YOUR_DOMAIN; do
  echo "=== $HOST ==="
  echo | openssl s_client -connect "${HOST}:443" -servername "$HOST" 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates
done
```

Expected service bodies from the reference environment:

```json
{"status":"pass"}
{"status":"ok"}
```

Startup logs showing an ACME provider are **not** proof of certificate issuance. Confirm the actual served issuer, TLS verification (without `curl -k`) and both responses.

## 11. Enroll the VPS host in Headscale

Once the Actalis certificates work and ACLs permit `tag:vps`, create a **single-use preauth key valid for ten minutes**. Keep the temporary file in RAM and clean it even on failure:

```bash
cd "$HOME/sovereign-cloud"
findmnt /dev/shm  # confirm filesystem type: tmpfs
# Run as a single script, NOT line-by-line in an interactive shell:
(
  set -e
  umask 077
  KEYFILE=$(mktemp -p /dev/shm dfc-auth.XXXXXXXX)
  trap 'rm -f -- "$KEYFILE"' EXIT
  sudo docker compose exec -T headscale \
    headscale preauthkeys create --tags tag:vps --expiration 10m > "$KEYFILE"
  sudo tailscale up \
    --login-server="https://headscale.YOUR_DOMAIN" \
    --auth-key="file:$KEYFILE"
)
sudo tailscale status
sudo docker compose exec headscale headscale nodes list
```

**Evidence limit:** the commands were tested individually but this exact sequence was **not executed end-to-end on a fresh VPS**. Verify `findmnt /dev/shm` reports `tmpfs`; otherwise choose a safe alternative. Do not re-enroll a previously enrolled host merely to repeat this example.

## 12. Pull future GitHub updates

```bash
cd "$HOME/sovereign-cloud"
git pull --ff-only origin main
sudo docker compose config --quiet
sudo docker compose up -d --build
```

When templates change, review differences before regenerating active configuration. Do not rerun `prepare-config.sh --force` automatically, rotate API keys, reset Headscale identities or erase ACME state as part of a routine update.

## 13. Work not yet validated

Full VPS reboot/recovery, isolated backup/restore, Actalis auto-renewal, measured cross-network DERP/STUN, TCP SNI passthrough to a home gateway and unattended provisioning on a physical Raspberry Pi **have not yet been demonstrated**. Existing `backup-headscale.sh` and `restore-headscale.sh` must **not** be considered restore-ready. Review Restic environment export, SQLite WAL handling, retention and the Admission registry; apply and test the revised scripts in isolation before relying on them.

**As of October 21, 2026:** Traefik 3.7.16, Actalis HTTPS, ambiguous-header rejection and updated Admission dependencies were tested. Windows SSH public-key login worked, but a final effective `PasswordAuthentication no` result was not captured. The OVHcloud network firewall was not yet enabled, and backups/restores were not operational.

**Next:** [Guide 3 — Reproducible Tests and Evidence](03_Guide_tests_validation.md).
