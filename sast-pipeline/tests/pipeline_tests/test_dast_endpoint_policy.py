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


def test_private_addresses_require_trusted_vpn():
    policy = DastEndpointPolicy(trusted_vpn=False, resolver=lambda _host, _port: ("10.2.42.7",))

    with pytest.raises(DastEndpointPolicyError):
        policy.validate("https://gateway.internal.example:8443")

    trusted_policy = DastEndpointPolicy(trusted_vpn=True, resolver=lambda _host, _port: ("10.2.42.7",))
    endpoint = trusted_policy.validate("https://gateway.internal.example:8443")

    assert endpoint.addresses == ("10.2.42.7",)
