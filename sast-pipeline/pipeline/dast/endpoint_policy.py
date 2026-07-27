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
    addresses: tuple[str, ...]


class DastEndpointPolicy:
    """Allow public HTTPS endpoints directly and RFC1918/ULA only through trusted VPN."""

    HTTPS_PORT: ClassVar[int] = 443
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
        if port != self.HTTPS_PORT:
            raise DastEndpointPolicyError("DAST gateway must use HTTPS port 443")

        hostname = parsed.hostname.rstrip(".").lower()
        if not hostname or "*" in hostname or "%" in hostname:
            raise DastEndpointPolicyError("DAST gateway hostname is invalid")
        addresses = self._resolve_addresses(hostname, port)
        for address in addresses:
            self._validate_address(address)
        return ValidatedDastEndpoint(
            url=gateway_url,
            hostname=hostname,
            port=port,
            addresses=addresses,
        )

    def _resolve_addresses(self, hostname: str, port: int) -> tuple[str, ...]:
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            try:
                raw_addresses = tuple(self._resolver(hostname, port))
            except (OSError, socket.gaierror) as exc:
                raise DastEndpointPolicyError("DAST gateway hostname could not be resolved safely") from exc
        else:
            raw_addresses = (str(literal),)

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
        address = ipaddress.ip_address(raw_address)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if address.is_unspecified or address.is_loopback or address.is_link_local or address.is_multicast:
            raise DastEndpointPolicyError(
                "DAST gateway resolves to a forbidden local or special-purpose address",
            )
        if address.is_global:
            return
        trusted_networks = self._TRUSTED_VPN_IPV4 if address.version == 4 else self._TRUSTED_VPN_IPV6
        if self._trusted_vpn and any(address in network for network in trusted_networks):
            return
        raise DastEndpointPolicyError("Non-public DAST gateway addresses require a trusted VPN route")

    @staticmethod
    def _resolve_with_system_dns(hostname: str, port: int) -> tuple[str, ...]:
        return tuple(
            item[4][0]
            for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        )
