FROM alpine:3.20

# openvpn    — VPN tunnel
# iproute2   — ip link show tun0 (readiness probe)
# bash       — entrypoint script
# tinyproxy  — HTTP/HTTPS CONNECT proxy; replaces microsocks which crashes on
#              Alpine/musl libc when resolving hostnames via VPN-pushed DNS.
RUN apk add --no-cache openvpn iproute2 bash tinyproxy

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# HTTP proxy port — accessible by container name on shared Docker network
EXPOSE 1080

ENTRYPOINT ["/entrypoint.sh"]
