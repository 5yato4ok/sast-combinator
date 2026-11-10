import ipaddress
import pytest
from pipeline.dast.endpoint_policy import DastEndpointPolicy, DastEndpointPolicyError


def test_accepts_default_https_port():
    policy = DastEndpointPolicy(trusted_vpn=False, resolver=lambda _host, _port: ("93.184.216.34",))

    endpoint = policy.validate("https://gateway.example/")

    assert endpoint.port == 443


def test_accepts_alternate_https_port_8443():
    policy = DastEndpointPolicy(trusted_vpn=False, resolver=lambda _host, _port: ("93.184.216.34",))

    endpoint = policy.validate("https://gateway.example:8443")

    assert endpoint.port == 8443


def test_rejects_port_outside_the_allowlist():
    policy = DastEndpointPolicy(trusted_vpn=False, resolver=lambda _host, _port: ("93.184.216.34",))

    with pytest.raises(DastEndpointPolicyError):
        policy.validate("https://gateway.example:8080")


@pytest.mark.parametrize("address", ["10.23.4.5", "172.16.4.8", "192.168.20.9", "fd00::10", "::ffff:a00:7"])
def test_private_gateway_is_reachable_directly(address):
    policy = DastEndpointPolicy(
        trusted_vpn=False, resolver=lambda _host, _port: (str(ipaddress.ip_address(address)),),
        allowed_private_networks=("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fd00::/64"),
    )

    assert policy.validate("https://gateway.internal:8443").addresses == (str(ipaddress.ip_address(address)),)
    url = f"https://[{address}]:8443" if ":" in address else f"https://{address}:8443"
    assert policy.validate(url).addresses == (str(ipaddress.ip_address(address)),)


def test_a_transient_resolution_failure_does_not_fail_a_vpn_routed_gateway():
    """A name resolvable only inside the tunnel has no local answer while VPN-pushed DNS settles.

    Treating that as a policy violation killed the attempt in the connector's constructor, before
    the HTTP layer's retries could help, and bought no enforcement under a trusted route.
    """
    def failing_resolver(_hostname, _port):
        raise OSError("Name or service not known")

    policy = DastEndpointPolicy(trusted_vpn=True, resolver=failing_resolver)

    endpoint = policy.validate("https://sc-vm-security001.nxlocal:8443")

    assert endpoint.hostname == "sc-vm-security001.nxlocal"
    assert endpoint.port == 8443
    # Not verifiable here, so nothing is claimed as verified -- the tunnel and the port allowlist
    # remain the boundary.
    assert endpoint.addresses == ()


def test_a_resolution_failure_still_fails_a_directly_reachable_gateway():
    def failing_resolver(_hostname, _port):
        raise OSError("Name or service not known")

    policy = DastEndpointPolicy(trusted_vpn=False, resolver=failing_resolver)

    with pytest.raises(DastEndpointPolicyError, match="could not be resolved safely"):
        policy.validate("https://gateway.example")


def test_a_vpn_routed_name_resolving_to_loopback_is_still_refused():
    """A local answer can never authorize a routed destination, but it can still deny one."""
    policy = DastEndpointPolicy(trusted_vpn=True, resolver=lambda _host, _port: ("127.0.0.1",))

    with pytest.raises(DastEndpointPolicyError, match="special-purpose"):
        policy.validate("https://gateway.internal.example:8443")


def test_a_padded_vpn_routed_answer_set_fails_closed():
    policy = DastEndpointPolicy(
        trusted_vpn=True,
        resolver=lambda _host, _port: tuple(f"10.0.0.{octet}" for octet in range(40)),
    )

    with pytest.raises(DastEndpointPolicyError, match="safety limit"):
        policy.validate("https://gateway.internal.example:8443")


def test_a_loopback_literal_is_refused_under_every_trust_boundary():
    for trusted_vpn in (False, True):
        policy = DastEndpointPolicy(trusted_vpn=trusted_vpn)

        with pytest.raises(DastEndpointPolicyError, match="special-purpose"):
            policy.validate("https://127.0.0.1:8443")


@pytest.mark.parametrize("networks", [(), ("10.24.0.0/16",)])
def test_unconfigured_private_gateway_is_refused(networks):
    with pytest.raises(DastEndpointPolicyError, match="AIST_DAST_ALLOWED_PRIVATE_NETWORKS"):
        DastEndpointPolicy(trusted_vpn=False, allowed_private_networks=networks).validate("https://10.23.4.5")


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "::1", "fe80::1", "240.0.0.1"])
def test_broad_configuration_cannot_allow_special_purpose_addresses(address):
    policy = DastEndpointPolicy(trusted_vpn=False, allowed_private_networks=("0.0.0.0/0", "::/0"))
    with pytest.raises(DastEndpointPolicyError, match="special-purpose"):
        policy.validate(f"https://[{address}]" if ":" in address else f"https://{address}")
