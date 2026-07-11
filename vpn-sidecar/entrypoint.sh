#!/bin/bash
# VPN sidecar entrypoint.
#
# Starts OpenVPN using credentials from environment variables, waits for the
# tunnel interface (tun0) to appear, then starts an HTTP CONNECT proxy (tinyproxy)
# on port 1080 whose traffic exits via the VPN tunnel.
#
# Required env (base64-encoded — Docker CLI truncates values at embedded newlines):
#   AIST_VPN_OVPN_CONTENT  — full .ovpn file (inline <ca>/<cert>/<key> supported)
#
# Optional env (base64-encoded, appended only if block not already present):
#   AIST_VPN_CA_CERT        — PEM CA certificate
#   AIST_VPN_CLIENT_CERT    — PEM client certificate
#   AIST_VPN_CLIENT_KEY     — PEM client private key
#   AIST_VPN_TLS_AUTH_KEY   — tls-auth / tls-crypt / tls-crypt-v2 key
#   AIST_VPN_USERNAME       — auth-user-pass username (plain string)
#   AIST_VPN_PASSWORD       — auth-user-pass password (plain string)
#
# Non-secret metadata (plain strings):
#   AIST_VPN_TLS_KEY_TYPE        — "tls-auth", "tls-crypt", or "tls-crypt-v2"
#   AIST_VPN_TLS_KEY_DIRECTION   — "0" or "1" (parsed from .ovpn by Python caller)
#   AIST_ALLOWED_IP              — celeryworker's eth0 IP; tinyproxy Allow is
#                                  restricted to this IP + 127.0.0.1 only
set -e

if [ -z "${AIST_VPN_OVPN_CONTENT:-}" ]; then
  echo "[VPN][ERROR] AIST_VPN_OVPN_CONTENT is not set." >&2
  exit 1
fi

VPN_DIR=$(mktemp -d /tmp/aist-vpn-XXXXXX)
chmod 700 "$VPN_DIR"

# Multi-line fields (certs, .ovpn config) are passed as base64 by the Python
# caller (_assemble_env in aist/utils/vpn.py) to avoid Docker CLI truncating
# values at embedded newlines.  Decode them here before use.
_decode_b64() { printf '%s' "$1" | base64 -d; }

# Write base .ovpn content (base64-decoded)
_decode_b64 "$AIST_VPN_OVPN_CONTENT" > "$VPN_DIR/client.ovpn"
chmod 600 "$VPN_DIR/client.ovpn"

# Append cert/key blocks only if not already present in the .ovpn file.
# This supports both: a complete .ovpn with inline certs (use as-is) and
# a base config + separate PEM fields (assembled here).
_append_block() {
  local tag="$1" b64_value="$2"
  [ -z "$b64_value" ] && return 0
  grep -q "<${tag}>" "$VPN_DIR/client.ovpn" && return 0  # already inline
  local value
  value=$(_decode_b64 "$b64_value")
  printf '\n<%s>\n%s\n</%s>\n' "$tag" "$value" "$tag" >> "$VPN_DIR/client.ovpn"
}

_append_block "ca"   "${AIST_VPN_CA_CERT:-}"
_append_block "cert" "${AIST_VPN_CLIENT_CERT:-}"
_append_block "key"  "${AIST_VPN_CLIENT_KEY:-}"

if [ -n "${AIST_VPN_TLS_AUTH_KEY:-}" ]; then
  # Determine which block tag the original .ovpn used:
  #   tls-auth     — legacy HMAC-only (OpenVPN < 2.4 default)
  #   tls-crypt    — modern HMAC+encryption (OpenVPN 2.4+)
  #   tls-crypt-v2 — per-client wrapped keys (OpenVPN 2.5+)
  # They are NOT interchangeable — the server will silently drop packets if the
  # wrong one is used.  AIST_VPN_TLS_KEY_TYPE is set by the Python caller after
  # parsing the uploaded .ovpn file.
  _TLS_TAG="${AIST_VPN_TLS_KEY_TYPE:-tls-auth}"
  if ! grep -q "<${_TLS_TAG}>" "$VPN_DIR/client.ovpn"; then
    if [ "$_TLS_TAG" = "tls-auth" ]; then
      # tls-auth requires key-direction to be set.
      # AIST_VPN_TLS_KEY_DIRECTION is parsed from the .ovpn body by the Python
      # caller (_extract_key_direction); default is "1" (OpenVPN client convention).
      _KEY_DIR="${AIST_VPN_TLS_KEY_DIRECTION:-1}"
      # Append key-direction only if not already present in the config body.
      # key-direction must precede the <tls-auth> inline block per OpenVPN spec.
      if ! grep -q "^key-direction" "$VPN_DIR/client.ovpn"; then
        printf '\nkey-direction %s\n' "$_KEY_DIR" >> "$VPN_DIR/client.ovpn"
      fi
    else
      # tls-crypt and tls-crypt-v2 do not use key-direction; remove it to avoid
      # OpenVPN warnings if it was present in the original config body.
      sed -i '/^key-direction/d' "$VPN_DIR/client.ovpn"
    fi
    printf '<%s>\n%s\n</%s>\n' \
      "$_TLS_TAG" "$(_decode_b64 "$AIST_VPN_TLS_AUTH_KEY")" "$_TLS_TAG" \
      >> "$VPN_DIR/client.ovpn"
  fi
fi

# Write auth-user-pass file if credentials are provided (plain strings, no b64)
if [ -n "${AIST_VPN_USERNAME:-}" ]; then
  printf '%s\n%s\n' "$AIST_VPN_USERNAME" "${AIST_VPN_PASSWORD:-}" > "$VPN_DIR/auth.txt"
  chmod 600 "$VPN_DIR/auth.txt"
  # Remove any existing auth-user-pass directive, then add ours
  sed -i '/^auth-user-pass/d' "$VPN_DIR/client.ovpn"
  echo "auth-user-pass $VPN_DIR/auth.txt" >> "$VPN_DIR/client.ovpn"
fi

# Ensure tun device exists (container has NET_ADMIN via --cap-add NET_ADMIN)
mkdir -p /dev/net
[ -e /dev/net/tun ] || { mknod /dev/net/tun c 10 200 && chmod 600 /dev/net/tun; }

echo "[VPN] Starting OpenVPN..."
openvpn \
  --config "$VPN_DIR/client.ovpn" \
  --daemon \
  --log "$VPN_DIR/openvpn.log"

# Wait up to 30 s for tun0 to appear
echo "[VPN] Waiting for tunnel interface (tun0)..."
_VPN_TRIES=0
until ip link show tun0 >/dev/null 2>&1 || [ "$_VPN_TRIES" -ge 30 ]; do
  sleep 1
  _VPN_TRIES=$((_VPN_TRIES + 1))
done

if ! ip link show tun0 >/dev/null 2>&1; then
  echo "[VPN][ERROR] tun0 did not appear after 30 s. OpenVPN log:" >&2
  cat "$VPN_DIR/openvpn.log" >&2
  exit 1
fi

echo "[VPN] Tunnel is UP."

# Configure DNS from VPN-pushed options so containers joining this network
# namespace via --network container:<name> resolve VPN-internal hostnames.
# OpenVPN logs the PUSH_REPLY line (at verb 3+) containing dhcp-option DNS/DOMAIN.
# We write /etc/resolv.conf here; joined containers inherit it automatically.
#
# NOTE: dhcp-option DNS and dhcp-option DOMAIN appear on SEPARATE log lines.
# Up to 3 DNS servers are captured for primary/fallback resilience.
_dns_servers="$(grep -o 'dhcp-option DNS [0-9.]*' "$VPN_DIR/openvpn.log" 2>/dev/null \
  | awk '{print "nameserver " $3}' | head -3)"
_dns_domain="$(grep -o 'dhcp-option DOMAIN [^ ,]*' "$VPN_DIR/openvpn.log" 2>/dev/null \
  | head -1 | awk '{print $3}')"

if [ -n "$_dns_servers" ]; then
  {
    printf '%s\n' "$_dns_servers"
    [ -n "$_dns_domain" ] && printf 'search %s\n' "$_dns_domain"
  } > /etc/resolv.conf
  echo "[VPN] DNS configured from VPN push."
fi

# Wipe auth credentials from disk immediately after OpenVPN has loaded them.
if [ -f "$VPN_DIR/auth.txt" ]; then
  shred -u "$VPN_DIR/auth.txt" 2>/dev/null || rm -f "$VPN_DIR/auth.txt"
fi

# Start the HTTP CONNECT proxy (tinyproxy).  All its traffic exits via tun0
# because OpenVPN has changed the default route in this network namespace.
#
# Security: tinyproxy listens on this container's eth0 IP only (not on tun0,
# so the corporate-VPN side cannot reach the proxy).  Allow is restricted to
# AIST_ALLOWED_IP (the celeryworker's eth0 IP passed by the Python caller) and
# 127.0.0.1.  Other containers on the Docker network are blocked.
#
# Note: builder containers that join via --network container:<sidecar> share the
# network namespace and use tun0 directly — they never connect to tinyproxy.
echo "[VPN] Starting HTTP CONNECT proxy (tinyproxy) on :1080..."

# Get this container's own eth0 IP to bind Listen there only (not on tun0).
_OWN_IP="$(ip -4 addr show eth0 2>/dev/null | awk '/inet /{split($2,a,"/"); print a[1]; exit}')"
_LISTEN_IP="${_OWN_IP:-0.0.0.0}"

# AIST_ALLOWED_IP is a comma/space separated list of client IPs allowed to use
# the proxy.  Ephemeral pipeline sidecar passes one IP (the celeryworker); the
# warm egress passes several (web + worker).  Injected by the Python caller.
_ALLOWED_IP="${AIST_ALLOWED_IP:-}"

{
  echo "Port 1080"
  echo "Listen ${_LISTEN_IP}"
  echo "Timeout 600"
  echo "Allow 127.0.0.1"
  # One Allow line per IP in the list (split on comma/space).
  for _ip in $(printf '%s' "$_ALLOWED_IP" | tr ',' ' '); do
    [ -n "$_ip" ] && echo "Allow ${_ip}"
  done
  echo "DisableViaHeader Yes"
  # Connect-level log to a FILE (not stdout, so `docker logs` stays clean and
  # leaks no internal hostnames).  The warm-egress idle reaper reads only this
  # file's mtime — never its content — to detect last use.  Ephemeral sidecars
  # simply never have their reaper look at it.
  echo "LogFile \"/tmp/tinyproxy-access.log\""
  echo "LogLevel Connect"
} > /tmp/tinyproxy.conf

tinyproxy -c /tmp/tinyproxy.conf &

echo "[VPN] Ready. HTTP CONNECT proxy (tinyproxy) on port 1080."

# Stay alive so the container keeps running while the builder uses the tunnel.
# Both openvpn (daemon) and tinyproxy continue in the background.
exec tail -f /dev/null
