"""Fail-closed destination policy evaluated inside the connector network namespace."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlsplit


class DastEndpointPolicyError(ValueError):
    """The configured gateway cannot be contacted through the selected trust boundary."""


AddressResolver = Callable[[str, int], Iterable[str]]


@dataclass(frozen=True, slots=True)
class ValidatedDastEndpoint:
    url: str
    hostname: str
    port: int
    # Verified addresses. Empty means "not verifiable here", not "no addresses" -- see
    # DastEndpointPolicy._authorized_addresses.
    addresses: tuple[str, ...]


class DastEndpointPolicy:
    """Allow public HTTPS endpoints directly and RFC1918/ULA only through trusted VPN.

    URL shape and port are always enforced; how far the *address* can be is in
    :meth:`_authorized_addresses`.
    """

    HTTPS_PORT: ClassVar[int] = 443
    # Deliberately a short enumerated allowlist, not an open range: DAST gateway deployments
    # commonly front their service on 8443 to avoid binding a privileged port, but each addition
    # here is still a reviewed exception to the SSRF policy, not a general "any port" escape hatch.
    # Kept in sync with aist/integrations/dast_endpoint_policy.py, the onboarding-time policy that
    # this connector-side policy re-evaluates inside the network namespace at scan-launch time.
    ALLOWED_PORTS: ClassVar[frozenset[int]] = frozenset({HTTPS_PORT, 8443})
    MAX_DNS_ANSWERS: ClassVar[int] = 32
    _TRUSTED_VPN_IPV4: ClassVar[tuple[ipaddress.IPv4Network, ...]] = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )
    _TRUSTED_VPN_IPV6: ClassVar[tuple[ipaddress.IPv6Network, ...]] = (
        ipaddress.ip_network("fc00::/7"),
    )

    def __init__(self, *, trusted_vpn: bool, resolver: AddressResolver | None = None):
        self._trusted_vpn = trusted_vpn
        self._resolver = resolver or self._resolve_with_system_dns

    def validate(self, gateway_url: str) -> ValidatedDastEndpoint:
        parsed = urlsplit(gateway_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise DastEndpointPolicyError(
                "DAST gateway must be an absolute HTTPS URL without credentials, query, or fragment",
            )
        try:
            port = parsed.port or self.HTTPS_PORT
        except ValueError as exc:
            raise DastEndpointPolicyError("DAST gateway port is invalid") from exc
        if port not in self.ALLOWED_PORTS:
            raise DastEndpointPolicyError("DAST gateway must use HTTPS on port 443 or 8443")

        hostname = parsed.hostname.rstrip(".").lower()
        if not hostname or "*" in hostname or "%" in hostname:
            raise DastEndpointPolicyError("DAST gateway hostname is invalid")
        return ValidatedDastEndpoint(
            url=gateway_url,
            hostname=hostname,
            port=port,
            addresses=self._authorized_addresses(hostname, port),
        )

    def _authorized_addresses(self, hostname: str, port: int) -> tuple[str, ...]:
        """Return the destination addresses this policy was able to verify.

        A literal needs no lookup, so what is checked is what will be connected to. A name on a
        direct connection must resolve and must be public: that answer is the one the socket uses.

        A VPN-routed name is only ever *denied* by a lookup -- the address rules already admit both
        public and RFC1918/ULA under a trusted route -- so requiring the lookup to succeed buys no
        enforcement while costing the attempt whenever VPN-pushed DNS lags the tunnel. The route and
        the port allowlist remain the boundary; the HTTP layer retries the connection.

        An empty result means "not verifiable here", not "no addresses".
        """
        literal = self._as_address_literal(hostname)
        if literal is not None:
            self._validate_address(literal)
            return (literal,)
        if self._trusted_vpn:
            self._deny_locally_resolvable_special_purpose(hostname, port)
            return ()
        addresses = self._resolve_addresses(hostname, port)
        for address in addresses:
            self._validate_address(address)
        return addresses

    @staticmethod
    def _as_address_literal(hostname: str) -> str | None:
        try:
            return str(ipaddress.ip_address(hostname))
        except ValueError:
            return None

    def _deny_locally_resolvable_special_purpose(self, hostname: str, port: int) -> None:
        """Refuse a VPN-routed name this process can already see is not a gateway.

        A special-purpose answer is never a DAST gateway. No answer -- the normal case for a
        VPN-internal zone -- is left to the attached route.
        """
        try:
            raw_addresses = tuple(self._resolver(hostname, port))
        except (OSError, socket.gaierror):
            return
        if len(raw_addresses) > self.MAX_DNS_ANSWERS:
            # Fail closed: a padded answer set could otherwise push a forbidden address out of view.
            raise DastEndpointPolicyError(
                "DAST gateway DNS answer set exceeds the safety limit",
            )
        for raw_address in raw_addresses:
            try:
                address = self._normalized_address(raw_address)
            except ValueError:
                # Each answer is judged on its own, so an unparseable one hides nothing.
                continue
            self._reject_special_purpose(address)

    def _resolve_addresses(self, hostname: str, port: int) -> tuple[str, ...]:
        try:
            raw_addresses = tuple(self._resolver(hostname, port))
        except (OSError, socket.gaierror) as exc:
            raise DastEndpointPolicyError("DAST gateway hostname could not be resolved safely") from exc

        if not raw_addresses or len(raw_addresses) > self.MAX_DNS_ANSWERS:
            raise DastEndpointPolicyError(
                "DAST gateway DNS answer set is empty or exceeds the safety limit",
            )
        normalized: list[str] = []
        for raw_address in raw_addresses:
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError as exc:
                raise DastEndpointPolicyError("DAST gateway DNS returned an invalid address") from exc
            value = str(address)
            if value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    def _validate_address(self, raw_address: str) -> None:
        address = self._normalized_address(raw_address)
        self._reject_special_purpose(address)
        if address.is_global:
            return
        trusted_networks = self._TRUSTED_VPN_IPV4 if address.version == 4 else self._TRUSTED_VPN_IPV6
        if self._trusted_vpn and any(address in network for network in trusted_networks):
            return
        raise DastEndpointPolicyError("Non-public DAST gateway addresses require a trusted VPN route")

    @staticmethod
    def _normalized_address(raw_address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        address = ipaddress.ip_address(raw_address)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            return address.ipv4_mapped
        return address

    @staticmethod
    def _reject_special_purpose(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if address.is_unspecified or address.is_loopback or address.is_link_local or address.is_multicast:
            raise DastEndpointPolicyError(
                "DAST gateway resolves to a forbidden local or special-purpose address",
            )

    @staticmethod
    def _resolve_with_system_dns(hostname: str, port: int) -> tuple[str, ...]:
        return tuple(
            item[4][0]
            for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        )
