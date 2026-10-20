"""Minimal NetBird management API client (standard library only)."""

import json
import urllib.error
import urllib.request


class ApiError(Exception):
    pass


class NetBirdApi:
    """Reads go to the API; writes are counted, logged and skipped in dry-run mode."""

    def __init__(self, url, token, dry_run=False, log=print, timeout=30):
        self.url = url.rstrip("/")
        self.token = token
        self.dry_run = dry_run
        self.log = log
        self.timeout = timeout
        self.changes = 0

    def _request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.url}/api{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Token {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise ApiError(f"{method} {path}: HTTP {exc.code} {detail}") from None
        except urllib.error.URLError as exc:
            raise ApiError(f"{method} {path}: {exc.reason}") from None
        return json.loads(raw) if raw else None

    def get(self, path):
        return self._request("GET", path)

    def write(self, method, path, body, summary):
        """Apply a change (or only describe it in dry-run mode)."""
        self.changes += 1
        if self.dry_run:
            self.log(f"[plan] {summary}")
            return None
        self.log(summary)
        return self._request(method, path, body)
