import requests
from requests.adapters import HTTPAdapter


class GenericHttpSigningClient:
    def __init__(self, url, file, retries, request_timeout):
        self.url = url
        self.file = file
        self.retries = retries
        self.request_timeout = request_timeout

    def upload(self, params):
        retries = 1
        session = requests.Session()
        session.mount(self.url, HTTPAdapter(max_retries=retries))
        response = session.get(self.url)
        if response.history:
            self.url = response.url
        try:
            with open(self.file, 'rb') as file_handle:
                r = session.post(
                    self.url,
                    params=params,
                    files={'file': file_handle},
                    timeout=self.request_timeout)
            return r.status_code
        except Exception:
            return None
