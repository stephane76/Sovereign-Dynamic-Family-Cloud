# Dynamic Family Cloud — Guide 3/3
## Reproducible tests: Actalis TLS, Headscale and Zero-Touch admission

**Edition: October 21, 2026 · Based on reference tests from October 20–21, 2026**

> **Purpose:** distinguish a service that merely starts from a protocol that actually works. The reference tests used an OVHcloud Debian 12 VPS, Headscale 0.29.5, initially Traefik 3.6 and later **Traefik 3.7.16**, a FastAPI Admission service and a simulated Docker Box with Tailscale 1.104.2. Unattended provisioning of a new physical Raspberry Pi has **not** been tested.

## 1. Test safety rules

- Run application commands from `$HOME/sovereign-cloud` with appropriate `sudo` access.
- Never disclose `.env`, Actalis EAB credentials, `/etc/dfc/headscale-api-key`, ACME account files, Ed25519 private keys or `hskey-auth` values.
- Successful admission tests **create real Headscale preauth keys**. Do not repeat them unnecessarily.
- Never revoke the **`tag:vps`** node. Look up the intended target before expiring or deleting any node.
- Python client tests use the isolated environment at `$HOME/dfc-box-test/.venv`, not system Python.
- `YOUR_DOMAIN` and `BOX_NODE_ID` are reader-specific placeholders.

## T01 — Docker Compose configuration and service state

```bash
cd "$HOME/sovereign-cloud"
sudo docker compose config --quiet
sudo docker compose ps
```

**Observed on the reference VPS with Traefik 3.6 and again with 3.7.16:** `dfc-traefik`, `dfc-headscale`, and `dfc-admission` running. Public application ports: 80/TCP, 443/TCP and 3478/UDP. Admission's port 8000 was not published directly.

**PASS:** Compose validation succeeds and all intended containers are running. This alone does not prove HTTPS works.

## T02 — Headscale configuration and ACL policy

```bash
sudo docker compose run --rm --no-deps headscale configtest
sudo docker compose exec headscale \
  headscale policy check --file /etc/headscale/policy.hujson
```

**Observed:** config test passed and policy checker returned `Policy is valid`. Use `exec` for the policy check because that operation requires the running server.

## T03 — HTTPS endpoints and Actalis certificates

```bash
curl -fsS https://headscale.YOUR_DOMAIN/health; echo
curl -fsS https://enroll.YOUR_DOMAIN/healthz; echo
for HOST in headscale.YOUR_DOMAIN enroll.YOUR_DOMAIN; do
  echo "=== $HOST ==="
  echo | openssl s_client -connect "${HOST}:443" -servername "$HOST" 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates
done
```

**Observed:** `{"status":"pass"}` for Headscale; `{"status":"ok"}` for Admission; both certificates issued by **Actalis S.p.A. / Actalis Domain Validated TLS Server RSA CA 2025**, valid through **January 20, 2027** at the time of testing.

During the initial setup, Traefik served `TRAEFIK DEFAULT CERT` because Actalis returned `Not enough quota`. An existing ACME account without certificates was discovered in `actalis.json`; after the account/plan issue was addressed, Actalis issued both certificates. **`Register with external account binding` in a log is not proof that certificate issuance succeeded.**

**PASS:** both requests validate TLS without `-k`, use an Actalis-issued certificate and return the expected response. **Not tested:** actual automatic ACME renewal.

## T04 — VPS mesh membership

```bash
sudo tailscale status
sudo docker compose exec headscale headscale nodes list
```

**Observed before simulated Box enrollment:** the `tag:vps` node was `online`, `Expired=no`, with `100.64.0.1`. Hostnames and numerical IDs vary between installations.

## T05 — Register a simulated Box

A physical Box must create and keep its Ed25519 private key **locally**. The following VPS-side key is strictly a lab simulation:

```bash
mkdir -p "$HOME/dfc-box-test"
chmod 700 "$HOME/dfc-box-test"
openssl genpkey -algorithm Ed25519 \
  -out "$HOME/dfc-box-test/private.pem"
chmod 600 "$HOME/dfc-box-test/private.pem"
openssl pkey -in "$HOME/dfc-box-test/private.pem" -pubout -outform DER \
  | tail -c 32 | od -An -v -tx1 | tr -d ' \n'
echo
```

If an existing Box ID is already linked to a previous key, **do not generate a new key and silently reuse that ID**. Keep the original private key or choose a new test identity.

Register the 32-byte public key represented as hexadecimal:

```bash
sudo docker compose exec admission python manage.py register \
  --id box-test-01 --site be --role gateway --pubkey YOUR_PUBLIC_KEY_HEX
sudo docker compose exec admission python manage.py list
```

**Observed:** `box-test-01 be gateway allowed`.

A Docker build issue was fixed when `manage.py` was missing from `/srv`. The tracked Dockerfile now contains `COPY manage.py ./`; the historical fix was committed as `93a2e50`.

## T06 — Valid Ed25519 admission

Create an isolated test environment if it does not exist:

```bash
sudo apt-get install -y python3-venv
python3 -m venv "$HOME/dfc-box-test/.venv"
"$HOME/dfc-box-test/.venv/bin/python" -m pip install httpx cryptography
```

Then run the existing project client:

```bash
cd "$HOME/sovereign-cloud"
"$HOME/dfc-box-test/.venv/bin/python" admission/test_client.py \
  --endpoint https://enroll.YOUR_DOMAIN \
  --id box-test-01 \
  --private-key "$HOME/dfc-box-test/private.pem"
```

**Observed:**

```text
Admission accepted. Use auth_key privately on the Box; DO NOT print key in logs.
```

The client calls `/v1/challenge`, signs the exact UTF-8 payload `dfc-admission-v1\n<device_id>\n<nonce>\n`, then sends `device_id`, `nonce` and Base64 signature to `/v1/admit`. An accepted admission alone does **not** prove a Tailscale node joined the mesh.

## T07 — Unknown device rejected

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  -X POST https://enroll.YOUR_DOMAIN/v1/challenge \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"unknown-box-999"}'
```

**Observed:** `HTTP 403` — historical **PASS**, also repeated after the FastAPI/Starlette upgrade.

## T08 — Invalid Ed25519 signature rejected

The companion test scripts are included at `tests/` :

```bash
"$HOME/dfc-box-test/.venv/bin/python" docs/part-2-control-plane/tests/test_admission_scenarios.py \
  --endpoint https://enroll.YOUR_DOMAIN --id box-test-01 \
  --private-key "$HOME/dfc-box-test/private.pem" \
  --scenario bad-signature
```

**Actual historical observation:** the original client received `httpx.HTTPStatusError: 403 Forbidden` from `/v1/admit` after signing with an incorrect key — **historical PASS**. Its Python traceback is a client behavior, not a server failure.

**New companion script:** expected successful test-runner exit code `0` and `bad-signature: 403 PASS`. **This new script has not yet been executed on the VPS**; the historical 403 must not be misrepresented as its output.

## T09 — Replay protection

From that same directory:

```bash
"$HOME/dfc-box-test/.venv/bin/python" docs/part-2-control-plane/tests/test_admission_scenarios.py \
  --endpoint https://enroll.YOUR_DOMAIN --id box-test-01 \
  --private-key "$HOME/dfc-box-test/private.pem" \
  --scenario replay
```

**Actual historical observation:** first submission **200**, second submission of the **same signed nonce** **403**; replay rejected — **historical PASS**.

**New script expectation:** `replay: 200 403 PASS` and process exit code `0`. The new script **has not yet run on the reference VPS**. The first request issues a fresh single-use Headscale key; the test must not print it.

The companion test runner also has `--scenario ok` and `--scenario unknown`. It is **not the same as** the original `admission/test_client.py`, which did not support `--scenario`.

## T10 — Headscale preauthorization keys

```bash
sudo docker compose exec headscale headscale preauthkeys list
```

Headscale 0.29.5 **does not support** `preauthkeys list --tags`. Redact key values before sharing output; retain only metadata.

**Observed:** two `tag:gateway` keys, each non-reusable and valid for **five minutes**, initially unused; the VPS `tag:vps` enrollment key had already been consumed.

## T11 — Actual simulated Box enrollment

Start an isolated Tailscale userspace-mode Docker container:

```bash
sudo docker pull tailscale/tailscale:stable
sudo docker run -d --name dfc-box-test --network bridge \
  --entrypoint tailscaled tailscale/tailscale:stable \
  --tun=userspace-networking
sudo docker exec dfc-box-test tailscale version
```

**Observed:** Tailscale 1.104.2. An earlier failed attempt was due to an improperly pasted shell command; the Docker container did not exist. After correcting that, enrollment worked.

The historical one-off test called `/v1/challenge` and `/v1/admit`, then passed the returned `auth_key` to `tailscale up` **in memory over standard input**, using `--auth-key=file:/dev/stdin`, without printing the key.

The repository also provides `docs/part-2-control-plane/tests/test_box_enrollment.py`. It has not yet been executed on the VPS. Run `sudo -v` first, then run it from the root of your clone with a registered, non-revoked test identity and a running test container. The Admission server allows 4 successful admissions per Box per hour (`MAX_ISSUES_HOUR`); beyond that, every `/v1/admit` request returns HTTP 429.

```bash
"$HOME/dfc-box-test/.venv/bin/python" docs/part-2-control-plane/tests/test_box_enrollment.py \
  --endpoint https://enroll.YOUR_DOMAIN \
  --login-server https://headscale.YOUR_DOMAIN \
  --id box-test-01 \
  --private-key "$HOME/dfc-box-test/private.pem" \
  --container dfc-box-test
```

**Actual historical output:**

```text
Ed25519 admission: PASS
Tailscale enrollment: PASS
Code de sortie : 0
```

Check the registered mesh node:

```bash
sudo docker exec dfc-box-test tailscale status
sudo docker compose exec headscale headscale nodes list
```

**Observed:**

| Node | Tag | Address | State |
|---|---|---|---|
| VPS node | `tag:vps` | `100.64.0.1` | online |
| `box-test-01` | `tag:gateway` | `100.64.0.2` | online |

This is **end-to-end proof with a simulated Box**, not proof of application-level mesh connectivity or unattended Raspberry Pi provisioning.

### Regression checks after the October 21 upgrades

- **Traefik 3.7.16 — observed PASS.** Headscale `/health` returned `{"status":"pass"}`, Admission `/healthz` returned `{"status":"ok"}`, both served Actalis certificates, and an ambiguous `X.Auth.User: test` header was rejected with **HTTP 400**.
- **Admission FastAPI 0.142.2 / Starlette 0.52.1 — partially observed PASS.** `pip check` succeeded, `/healthz` worked, the registry persisted, the original Ed25519 test client was accepted and an unknown Box was rejected with **HTTP 403**.
- **Not rerun after upgrading Admission:** T08 (invalid signature), T09 (replay), T11 (full enrollment). Their historical observations were obtained against the earlier Admission image; the included companion scripts can be used for new regression tests.

## T12 — Revoke the test Box

Identify the correct **`tag:gateway`** node in the live output. Never copy a numerical ID from an example; never revoke the **`tag:vps`** control node.

```bash
sudo docker compose exec headscale headscale nodes list
sudo docker compose exec headscale \
  headscale nodes expire --identifier BOX_NODE_ID --force
sudo docker compose exec headscale headscale nodes list
sudo docker exec dfc-box-test tailscale status
```

**Actual historical observation:** `Node expired`; Box became `offline` with `Expired=yes`, and its Tailscale client printed `Logged out.` The `tag:vps` node remained online and unexpired — **PASS**.

`expire` retains the node's database record and requires reauthentication; `nodes delete` is a different, destructive operation.

## T13 — Verify Git checkout integrity

```bash
cd "$HOME/sovereign-cloud"
git status --short
git log -1 --oneline
```

**Observed after the October 21 updates:** working tree clean and latest reference commit:

```text
c2963de (HEAD -> main, origin/main, origin/HEAD) fix(security): update Admission FastAPI and Starlette
```

The earlier Dockerfile correction was committed as `93a2e50`; Traefik 3.7 and header hardening as `079ddac`. Commit IDs are historical **maintainer evidence**, not values that a reader must reproduce. `.env` and private keys were not included in the examined commits.

## 2. Remaining validation before resilient production claims

| Missing test | What it must demonstrate | Status on Oct 21, 2026 |
|---|---|---|
| Full VPS reboot | Headscale, Admission, ACME and host Tailscale survive restart | Not performed |
| Isolated backup and recovery | SQLite including WAL, Admission registry, keys, ACLs and retention are restorable without touching live data | Not performed; existing scripts require corrections |
| Actalis ACME renewal | Automatic certificate renewal before expiry | Not observed |
| Cross-network DERP/STUN | Actual relay use and security | Not measured |
| Mesh ACL traffic test | Permitted/denied paths between role tags | Not performed |
| TCP SNI passthrough | Reach a home gateway, TLS terminates at home | Not enabled |
| Physical Raspberry Pi bootstrap | Local key generation, first boot, admission and automated recovery | Not performed |
| OVHcloud network firewall | Stateless IPv4 rules include TCP established, DNS responses, intended inbound service ports and final deny; separate IPv6 host filtering | Not configured |
| Headscale trusted-client-IP sanitation | Remove untrusted `True-Client-IP` at Traefik and verify at the backend | Not verified |

The project has passed a **functional VPS Zero-Touch admission test**, **not** a full security certification, resilience qualification or regulatory sovereignty audit.

## 3. Lab cleanup

Only after the Box has been revoked, and only if no subsequent tests need it:

```bash
sudo docker rm -f dfc-box-test
```

Retain or securely dispose of simulated Ed25519 test keys according to a deliberate lab policy. Do **not** delete the VPS's Tailscale identity or the persistent Headscale, Admission and Actalis volumes as part of simulated Box cleanup.

## Overall result

**Historically demonstrated:** Actalis TLS endpoints, Headscale configuration, Box identity registration, Ed25519 challenge, unknown-device rejection, invalid-signature rejection, replay rejection, Headscale key issuance, simulated Box enrollment and revocation. **Reconfirmed after the upgrades:** Traefik 3.7 HTTPS and header protection, Admission dependency compatibility, registry persistence, valid admission and unknown-device rejection.

**Still unvalidated:** OVHcloud firewall, automatic ACME renewal, post-reboot persistence, reliable backup/restore, detailed mesh traffic/security behavior, real DERP relay performance, TLS passthrough and hands-off physical Raspberry Pi onboarding.
