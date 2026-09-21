from __future__ import annotations

from typing import Any


class AnkiConnectClient:
    def __init__(self, url: str = "http://127.0.0.1:8765"):
        self.url = url

    def invoke(self, action: str, params: dict | None = None, timeout: int = 30) -> Any:
        import requests
        payload = {"action": action, "version": 6, "params": params or {}}
        resp = requests.post(self.url, json=payload, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()
        if result.get("error"):
            raise RuntimeError(f"AnkiConnect error on {action!r}: {result['error']}")
        return result["result"]
