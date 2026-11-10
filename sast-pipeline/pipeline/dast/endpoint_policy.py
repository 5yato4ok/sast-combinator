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

    def matches_origin(self, request_url: str) -> bool:
        """Both HTTP clients must keep requests on the approved HTTPS origin."""
        origin = urlsplit(request_url)
        return (
            origin.scheme,
            (origin.hostname or "").rstrip(".").lower(),
            origin.port or 443,
        ) == ("https", self.hostname, self.port)


class DastEndpointPolicy:
    """Allow public and configured private HTTPS endpoints with optional VPN transport.

    URL shape and port are always enforced; how far the *address* can be is in
    :meth:`_authorized_addresses`.
    """

    HTTPS_PORT: ClassVar[int] = 443
    # Deliberately a short enumerated allowlist, not an open range: DAST gateway deployments
    # commonly front their service on 8443 to avoid binding a privileged port, but each addition
    # here is still a reviewed exception to the SSRF policy, not a general "any port" escape hatch.
    ALLOWED_PORTS: ClassVar[frozenset[int]] = frozenset({HTTPS_PORT, 8443})
    MAX_DNS_ANSWERS: ClassVar[int] = 32
    def __init__(
        self,
        *,
        trusted_vpn: bool,
        allowed_private_networks: Iterable[str] = (),
        resolver: AddressResolver | None = None,
    ):
        self._trusted_vpn = trusted_vpn
        self._resolver = resolver or self._resolve_with_system_dns
        try:
            self._private_networks = tuple(ipaddress.ip_network(value.strip()) for value in allowed_private_networks)
        except (ValueError, AttributeError, TypeError) as exc:
            raise DastEndpointPolicyError("AIST_DAST_ALLOWED_PRIVATE_NETWORKS must contain valid CIDRs") from exc

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
        direct connection must resolve to permitted unicast addresses: the socket uses that answer.

        A VPN-routed name is only ever denied by a local lookup: the proxy owns the actual
        resolution. The operator-provisioned route and port allowlist remain the boundary;
        the configured private CIDRs cannot authorize an address that is not observable here.

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

    @staticmethod
    def reject_redirect(status_code: int) -> None:
        if 300 <= status_code < 400:
            raise DastEndpointPolicyError("DAST gateway redirects are not allowed")

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
        if any(address in network for network in self._private_networks):
            return
        raise DastEndpointPolicyError("DAST gateway private address is not permitted by AIST_DAST_ALLOWED_PRIVATE_NETWORKS")

    @staticmethod
    def _normalized_address(raw_address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        address = ipaddress.ip_address(raw_address)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            return address.ipv4_mapped
        return address

    @staticmethod
    def _reject_special_purpose(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if address.is_unspecified or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved:
            raise DastEndpointPolicyError(
                "DAST gateway resolves to a forbidden local or special-purpose address",
            )

    @staticmethod
    def _resolve_with_system_dns(hostname: str, port: int) -> tuple[str, ...]:
        return tuple(
            item[4][0]
            for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        )
