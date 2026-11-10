import httpx

from pipeline.dast.endpoint_policy import ValidatedDastEndpoint


class PinnedGatewayTransport(httpx.HTTPTransport):
    """Keep DNS approval, TLS server name and HTTP authority bound for every connection."""

    def __init__(self, endpoint: ValidatedDastEndpoint, **kwargs):
        if not endpoint.addresses:
            raise httpx.InvalidURL("A direct DAST transport requires approved addresses")
        self.endpoint = endpoint
        super().__init__(**kwargs)

    def handle_request(self, request):
        if not self.endpoint.matches_origin(str(request.url)):
            raise httpx.InvalidURL('Request does not belong to the configured DAST gateway')
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=self.endpoint.addresses[0]),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, 'sni_hostname': self.endpoint.hostname},
        )
        return super().handle_request(pinned)
