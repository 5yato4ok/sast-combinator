# VPN Sidecar

Starts a temporary Docker container running OpenVPN and an HTTP proxy so that
other parts of the platform can reach resources inside a corporate VPN —
without installing VPN software on the host machine.

---

## Why this exists

Clients may host Jira, GitLab, or other systems on an internal network that is
not reachable from the internet. Instead of maintaining a permanent VPN connection
on the server, the platform uses a **one-execution-one-container** approach: the
container is started, performs the operation, and is removed. If no VPN is needed,
no container is created at all.

---

## Traffic map

### Scenario 1 — Celery task (validate, work-item sync)

```
┌──────────────────────────────────────────────────────────────────┐
│ Docker network: aist_default                                     │
│                                                                  │
│  ┌─────────────────┐  http://aist-vpn-<id>:1080  ┌────────────────────┐
│  │  celeryworker   │ ────────────────────────────▶│  aist-vpn-<id>     │
│  │  (Python/Django)│                              │  (VPN sidecar)     │
│  │                 │◀── CONNECT tunnel established│                    │
│  │  requests       │                              │  tinyproxy :1080   │
│  │  .get("https:// │                              │  openvpn (tun0)    │
│  │  gitlab...")    │                              └────────────────────┘
│  └─────────────────┘                                       │
│                                                            │ encrypted
│                                                            │ VPN tunnel (UDP)
└──────────────────────────────────────────────────────────────────┘
                                                             │
                                               ┌─────────────────────┐
                                               │  Corporate VPN       │
                                               │  server              │
                                               └─────────────────────┘
                                                             │
                                               ┌─────────────────────┐
                                               │  Internal resource   │
                                               │  (GitLab, Jira, ...) │
                                               └─────────────────────┘
```

**Step by step:**

1. `celeryworker` wants to make an HTTPS request to `gitlab.internal:443`
2. `requests` sees `proxies={"https": "http://aist-vpn-<id>:1080"}`
3. `requests` connects to the proxy (tinyproxy) and sends:
   `CONNECT gitlab.internal:443 HTTP/1.1`
4. `tinyproxy` inside the sidecar resolves `gitlab.internal` using the DNS
   server pushed by the VPN server, opens a TCP connection to it
5. `tinyproxy` replies: `200 Connection Established`
6. From this point `requests` and `gitlab.internal` communicate directly over
   the TCP tunnel — **TLS handshake and all HTTPS traffic is encrypted end-to-end**;
   `tinyproxy` sees only the hostname and port, never the content
7. Inside the sidecar all outgoing traffic exits via `tun0` (VPN interface)
   because OpenVPN sets the default route to `0.0.0.0/0 via tun0`

---

### Scenario 2 — SAST pipeline (builder container)

```
┌──────────────────────────────────────────────────────────────┐
│ Network namespace of aist-vpn-<pipeline_id>                  │
│                                                              │
│  ┌──────────────────────────────┐                            │
│  │  project-builder (analyzer)  │                            │
│  │  --network container:aist-vpn│                            │
│  │                              │                            │
│  │  git clone / API calls       │──── tun0 ──▶ VPN server   │
│  └──────────────────────────────┘                            │
└──────────────────────────────────────────────────────────────┘
```

The SAST pipeline starts `project-builder` with
`--network container:aist-vpn-<id>`. This means the builder **gets exactly the
same network stack** as the sidecar — `eth0` (internet via VPN), `tun0`, and the
same DNS servers. The builder has no knowledge of the proxy; VPN is transparent
at the OS level.

---

## Container lifecycle

```
vpn_sidecar_context() called
        │
        ▼
Is VPN needed?
(vpn_secret.ovpn_content set?)
        │
  No ──▶ yield (None, None)  ←── caller works without VPN
        │
  Yes
        │
        ▼
docker build aist-vpn-sidecar:latest
(skipped if image already present)
        │
        ▼
docker run -d aist-vpn-<execution_id>
  --cap-add NET_ADMIN
  --device /dev/net/tun
  --network aist_default   (or -p port:1080 in fallback mode)
  -e AIST_VPN_OVPN_CONTENT=<base64>
  -e AIST_VPN_CA_CERT=<base64>
  ... other env vars
        │
        ▼
entrypoint.sh:
  1. Assemble client.ovpn from env vars
  2. openvpn --daemon
  3. Wait for tun0 (up to 30 seconds)
  4. Write /etc/resolv.conf from VPN-pushed DNS
  5. Shred auth.txt from disk
  6. Start tinyproxy on :1080
        │
        ▼
Sidecar ready → yield (container_name, proxy_url)
        │
   [ caller uses VPN ]
        │
        ▼
finally: docker stop && docker rm
```

Container name is `aist-vpn-<execution_id>`, so `cleanup_pipeline_containers()`
automatically catches it if the Celery worker is killed before the `finally`
block runs.

---

## Credential storage and transport

Model `OrgIntegrationVPNSecret` (`vpn_secret` on a VPN-type `OrgIntegration`):

| Field          | Encrypted | Description                                         |
|----------------|-----------|-----------------------------------------------------|
| `ovpn_content` | AES (DB)  | Base `.ovpn` config without cert blocks             |
| `ca_cert`      | AES (DB)  | PEM CA certificate                                  |
| `client_cert`  | AES (DB)  | PEM client certificate                              |
| `client_key`   | AES (DB)  | PEM client private key                              |
| `tls_auth_key` | AES (DB)  | `tls-auth` or `tls-crypt` key                       |
| `tls_key_type` | no        | Which key type: `"tls-auth"` or `"tls-crypt"` (not secret) |
| `vpn_username` | AES (DB)  | Username (when VPN requires auth)                   |
| `vpn_password` | AES (DB)  | Password (when VPN requires auth)                   |

**How credentials travel from DB to container:**

```
DB (encrypted) → Celery worker (decrypted in memory)
    → base64-encode → docker run -e KEY=value
        → entrypoint.sh: base64 -d → write to /tmp/aist-vpn-XXXXXX/ (chmod 600)
            → openvpn reads files → auth.txt shredded immediately after
```

Base64 encoding is not a security measure — it is needed because the Docker CLI
truncates env-var values at the first embedded newline, and PEM certificates are
multi-line.

---

## Why HTTP CONNECT proxy instead of SOCKS5

The original implementation used **microsocks** (SOCKS5). It crashed with a
segfault on Alpine Linux / musl libc when resolving hostnames through VPN-pushed
DNS (`getaddrinfo` behaviour differs between musl and glibc in certain conditions).

Replaced with **tinyproxy** — an HTTP CONNECT proxy. Key point:

| Term | Meaning |
|------|---------|
| `http://proxy:1080` in `proxies=` | Control protocol (how to open the tunnel) |
| HTTPS traffic through the proxy | TLS-encrypted end-to-end; proxy sees only hostname:port |

The `CONNECT` method creates a TCP tunnel:
- Proxy sees: `CONNECT gitlab.internal:443`
- Proxy does NOT see: headers, body, tokens, request content

This is the same mechanism used by every corporate proxy (Squid, nginx,
Zscaler, etc.).

---

## Networking inside Docker

**Why not `-p 127.0.0.1:PORT:1080`:**

On Linux Docker Engine, a port bound to `127.0.0.1` is only accessible on the
host loopback. From inside another container, `host.docker.internal` resolves to
the Docker bridge gateway IP (e.g. `172.19.0.1`), not `127.0.0.1`. The
connection fails with `ECONNREFUSED`. Docker Desktop on macOS hides this through
a VM shim, which is why it worked locally but not on Linux production.

**Solution used:**

The sidecar is started with `--network aist_default` at `docker run` time — the
same network as the celeryworker. Docker DNS resolves `aist-vpn-<id>` to the
sidecar's IP. The proxy is reachable by container name with no ports exposed to
the host.

**Critical:** `--network` must be set at `docker run`, NOT added later via
`docker network connect`. Adding a second network after startup creates a second
interface (`eth1`) and corrupts the routing table: OpenVPN stops receiving
replies from the VPN server and `tun0` never comes up.

---

## Fallback modes

| Situation | Behaviour |
|-----------|-----------|
| Inside Docker, own network detected | `--network <network>`, proxy via container name |
| Inside Docker, network not detected | `-p <random_port>:1080`, proxy via `host.docker.internal` |
| Running on host (local dev) | `-p 127.0.0.1:<random_port>:1080`, proxy via `127.0.0.1` |
| No VPN configured for the project | Container not started; `(None, None)` returned |

---

## Side effects to be aware of

**Startup latency.** The sidecar waits up to 35 seconds for the VPN tunnel to
come up. If the VPN server is unreachable or the config is wrong, the task fails
with a timeout. This is expected behaviour.

**Orphaned containers.** If the Celery worker is killed (`SIGKILL` or OOM) before
the `finally` block, the sidecar stays running. The `cleanup_orphaned_vpn_containers`
scheduled task removes all `aist-vpn-*` containers older than 4 hours.

**Host routes unaffected.** OpenVPN inside the sidecar changes the default route
**only within the container's network namespace**. Host machine routes and other
containers are not affected.

**DNS inheritance.** If the VPN server pushes DNS servers, the sidecar's
`/etc/resolv.conf` is overwritten. Containers joined via
`--network container:aist-vpn-<id>` inherit that `resolv.conf`.

**Parallel executions.** Each run (pipeline, validate, work-item sync) gets a
unique `execution_id` → unique container name. Multiple VPN sidecars can run
concurrently with no naming conflicts.

**NET_ADMIN capability.** The container requires `--cap-add NET_ADMIN` to create
the TUN interface. This is the minimum necessary for OpenVPN; `privileged: true`
is not used.

---

## Component files

```
sast-combinator/vpn-sidecar/
├── Dockerfile        — Alpine image with openvpn + tinyproxy
├── entrypoint.sh     — assembles .ovpn, starts OpenVPN, starts tinyproxy
└── README.md         — this file

aist/utils/vpn.py              — Python: sidecar lifecycle (vpn_sidecar_context)
aist/models.py                 — OrgIntegrationVPNSecret (credential storage)
aist/api/org_integrations.py   — API: save, parse .ovpn, validate endpoint
docs/integrations/vpn.md       — how AIST uses this sidecar (architecture, config)
```

---

## Troubleshooting

**Sidecar did not start (tun0 timeout):**
```bash
docker logs aist-vpn-<execution_id>
# Look for [VPN][ERROR] and the openvpn.log dump
```

**Proxy not responding (Connection refused):**
```bash
docker exec aist-vpn-<id> ip link show tun0     # tun0 must be UP
docker exec aist-vpn-<id> ss -tlnp | grep 1080  # tinyproxy must be listening
```

**Wrong `tls_key_type` in DB** — symptom: `TLS Error` in OpenVPN logs.
The field must match the block tag used in the original `.ovpn` file:
`<tls-auth>` → `tls-auth`, `<tls-crypt>` → `tls-crypt`.
