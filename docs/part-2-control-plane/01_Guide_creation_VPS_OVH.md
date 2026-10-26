# Dynamic Family Cloud — Guide 1/3
## Creating an OVHcloud VPS: from ordering to secure SSH access

**Edition: October 21, 2026 · Language: English · Audience: readers of Part 2**

> **Scope.** This guide covers a **standard OVHcloud VPS**, not an OVHcloud Public Cloud/OpenStack instance. The VPS hosts the public **control plane** (Headscale, Zero-Touch admission, relay components), never the family file store. The exact commercial VPS size and datacenter used during the reference deployment were not recorded. Select a suitable Debian VPS without presenting an unverified commercial SKU as tested.

## 1. Prepare your account and domain

You need an OVHcloud account, a valid payment method, a domain whose **DNS zone is managed in OVHcloud**, and an SSH key for administration. Replace `YOUR_DOMAIN` and `YOUR_VPS_IP` in all examples with your own values; do not reuse addresses from the reference deployment.

Store the VPS identifier, public IP, initial user name, SSH host-key fingerprint and OVHcloud Manager credentials securely. Do not commit passwords, private keys or personal email addresses.

## 2. Order the VPS

1. Open the [OVHcloud Manager](https://www.ovh.com/manager/), select **VPS**, and order a standard VPS.
2. Select an EU location consistent with your data-residency requirements. Confirm the actual datacenter location and service terms at purchase time.
3. **Tested on Debian 12. Debian 13 is the current stable Debian release but has not been tested in this project.** Choose Debian 12 where available, or revalidate the procedures on another release.
4. Provision enough memory and disk for three lightweight containers, logs, SQLite databases and updates; resource needs depend on real load.
5. Provide your **public SSH key** during provisioning when the Manager supports it. Never upload the private key.
6. Wait for the VPS to be shown as provisioned/active and record its IPv4 address.

Manager labels can change. The reference installation did not establish a minimum validated VPS plan.

## 3. First SSH connection

From your computer:

```bash
ssh debian@YOUR_VPS_IP
```

The administrative user may be different depending on the image. **Do not disable passwords before a key-only SSH login succeeds in a second, independent session.**

On the VPS:

```bash
cat /etc/os-release
id
hostnamectl
ip -br address
ip route
sudo ss -lntup
```

Confirm the expected distribution, IP address, working `sudo`, and SSH connectivity. Keep OVHcloud's recovery/console option available.

## 4. Initial system preparation

For a **newly provisioned** VPS, an initial package maintenance step may be appropriate:

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl git openssl dnsutils
```

Plan a controlled reboot if a kernel update requires one. This is a setup recommendation, **not a claim that a Debian-wide upgrade was performed in the October 21 reference session**; that session intentionally upgraded only application components.

## 5. Configure OVHcloud DNS

In the Manager, open your domain's DNS zone and create these records:

| Type | Host | Target | Purpose |
|---|---|---|---|
| A | `headscale` | VPS public IPv4 | Mesh control plane |
| A | `enroll` | VPS public IPv4 | Zero-Touch admission |
| A | `cloud` | VPS public IPv4 | Reserved future application ingress; **not active yet** |

Example FQDNs: `headscale.YOUR_DOMAIN`, `enroll.YOUR_DOMAIN`, `cloud.YOUR_DOMAIN`. Do not publish an AAAA record until IPv6 connectivity and IPv6 firewall protections have been tested. Do not activate TLS passthrough for `cloud` without a deployed family gateway and routing test.

```bash
dig +short A headscale.YOUR_DOMAIN
dig +short A enroll.YOUR_DOMAIN
dig +short A cloud.YOUR_DOMAIN
```

## 6. Network exposure and SSH hardening

| Port | Protocol | Function | Policy |
|---|---|---|---|
| 22 | TCP | SSH administration | Restrict to trusted admin IPs where practical |
| 80 | TCP | Traefik / Actalis ACME HTTP-01 | Public |
| 443 | TCP | Traefik HTTPS | Public |
| 3478 | UDP | Headscale STUN | Public |

Do **not** expose Headscale's internal port 8080, Admission's internal port 8000, gRPC port 50443 or the Docker API. Docker-published ports may bypass simplistic UFW rules: host firewall and OVHcloud network firewall rules require their own verification.

### 6.1 Enforce SSH public-key authentication

**Safety first:** keep the current SSH session open, independently verify login with your public key, and know how to reach the OVHcloud recovery console before changing the daemon. On Windows PowerShell, using an existing private key:

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_ovh" -o IdentitiesOnly=yes -o PasswordAuthentication=no debian@YOUR_VPS_IP
```

For Linux or macOS, use the equivalent command:

```bash
ssh -i ~/.ssh/YOUR_ADMIN_KEY -o IdentitiesOnly=yes -o PasswordAuthentication=no debian@YOUR_VPS_IP
```

Replace the key name and username with your own. A passphrase prompt protecting the private key is normal. Once that login works, on the VPS:

```bash
sudo tee /etc/ssh/sshd_config.d/01-dfc-hardening.conf >/dev/null <<'CONF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
CONF
sudo sshd -t && sudo systemctl reload ssh
sudo sshd -T | grep -Ei '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication) '
```

The `01-` prefix is intentional. On the reference VPS, `/etc/ssh/sshd_config.d/50-cloud-init.conf` contained `PasswordAuthentication yes`, and OpenSSH honored that earlier setting over a later `99-dfc-hardening.conf` entry. Inspect effective settings with `sshd -T`; account for any `Match` rules as applicable.

Expected effective values:

```text
permitrootlogin no
passwordauthentication no
kbdinteractiveauthentication no
pubkeyauthentication yes
```

Test **from a second external connection**: key login must succeed. Also explicitly test that a password-only connection fails:

```bash
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password debian@YOUR_VPS_IP
```

A rejection is expected; never enter or disclose your password in the guide. Verify that root SSH login is also denied. Keep the original session open until all checks pass. If `sshd -t` fails, do not reload SSH.

**Reference status, October 21:** Windows-to-VPS Ed25519 key login succeeded; the final `sshd -T` output **after fixing the priority conflict was not provided**. Therefore the final effective `PasswordAuthentication no` setting is **not yet evidenced**, even though the hardening configuration was applied and SSH reloaded.

### 6.2 OVHcloud network firewall — not yet applied to the reference VPS

If Edge Network Firewall is available for your VPS/IP, configure it under the OVHcloud Manager's public-IP/network area. **Do not enable a catch-all deny with only the service ports permitted.** OVHcloud's Edge Network Firewall is **stateless**, applies to **IPv4 only**, and filters incoming traffic; responses to the VPS's outgoing TCP and UDP connections may also be filtered. OVHcloud documents up to **20 rules per protected IP**. See [OVHcloud's official Edge Network Firewall documentation](https://docs.ovhcloud.com/en/guides/bare-metal-cloud/dedicated-servers/firewall-network).

Suggested **IPv4** rule order for the reference architecture (adapt to your actual services and the rule fields the Manager offers):

| Priority | Allow rule / action | Rationale |
|---|---|---|
| 0 | **TCP established** | Replies to outgoing TCP connections (OVHcloud example) |
| 1 | **UDP source port 53** | DNS replies (OVHcloud example) |
| 2 | **ICMP** | Network diagnostics (OVHcloud example) |
| 3 | **TCP destination port 22**, source = **your trusted admin IPv4** | SSH; plan access if your address changes |
| 4 | **TCP destination port 80** | Actalis HTTP-01 challenge and HTTP routing |
| 5 | **TCP destination port 443** | Headscale and Admission HTTPS |
| 6 | **UDP destination port 3478** | Headscale STUN |
| 7 | **UDP destination port 41641** | Optional Tailscale WireGuard direct path **if the host is actually listening there**; verify with `sudo ss -lunp` and `tailscale netcheck` |
| 19 | **Deny IPv4** | Required final catch-all rule |

**Additional network checks:** If the VPS uses external NTP, permit relevant incoming **UDP source port 123** replies (or account for OVH's internal time service), and verify any additional UDP protocols the deployment actually uses. For Tailscale, `41641/UDP` is a common default but the actual peer listening port may differ. With a stateful host firewall, allow return traffic separately using connection tracking; Edge Network Firewall does not provide that automatically.

**IPv6 is not protected by the Edge Network Firewall.** If IPv6 is enabled, use and test an appropriate **host firewall** for IPv6 and review AAAA records. Edge rules may also not filter traffic from OVHcloud's internal network. SSH hardening and host-level filtering are therefore still necessary; Docker-published ports deserve explicit testing.

Apply rules incrementally while keeping an existing SSH connection and the OVHcloud console/recovery path available. After enabling the firewall, check from **outside OVHcloud**: key-based SSH, Headscale/Admission HTTPS, Actalis HTTP-01 reachability, DNS resolution, outbound HTTPS/image pulls, STUN and NTP if used. Do **not** mark the firewall complete until these checks pass.

**Reference status (October 21): NOT CONFIGURED / NOT TESTED.** UFW was absent and the OVHcloud firewall had not yet been enabled.

## 7. Guide 1 completion criteria

- Standard OVHcloud VPS is active with a verified OS, user and recovery method.
- Independent key-only SSH access and `sudo` work.
- OVHcloud DNS records point to the intended public IP.
- Effective SSH password/root restrictions are verified; network/host firewall and port-22 restrictions are tested from outside the VPS.
- Only required public-facing ports have been explicitly documented and reviewed.

These are **criteria to achieve**, not an assertion that every security check already passed on the reference VPS.

**Next:** [Guide 2 — VPS Configuration, GitHub and Deployment](02_Guide_configuration_VPS_GitHub.md).
