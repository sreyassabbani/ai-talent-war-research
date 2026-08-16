from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import httpx


@dataclass(frozen=True)
class CachedResponse:
    url: str
    content: bytes
    content_type: str
    from_cache: bool


class SecClient:
    """Small, cache-first EDGAR client with a process-wide conservative rate limit."""

    def __init__(self, user_agent: str, cache_dir: Path, rate_per_second: float = 5.0) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.interval = 1.0 / rate_per_second
        self._next_request_at = 0.0
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def _paths(self, url: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.body", self.cache_dir / f"{digest}.json"

    def _wait(self) -> None:
        now = time.monotonic()
        if now < self._next_request_at:
            time.sleep(self._next_request_at - now)
        self._next_request_at = time.monotonic() + self.interval

    def get(self, url: str, refresh: bool = False) -> CachedResponse:
        body_path, metadata_path = self._paths(url)
        if body_path.exists() and metadata_path.exists() and not refresh:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            return CachedResponse(
                url=url,
                content=body_path.read_bytes(),
                content_type=metadata.get("content_type", ""),
                from_cache=True,
            )

        last_error: Exception | None = None
        for attempt in range(4):
            self._wait()
            try:
                response = self.client.get(url)
                if response.status_code in {403, 429} or response.status_code >= 500:
                    retry_after = response.headers.get("Retry-After")
                    delay = (
                        float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                    )
                    time.sleep(delay + random.uniform(0, 0.25))
                    last_error = httpx.HTTPStatusError(
                        f"SEC returned {response.status_code} for {url}",
                        request=response.request,
                        response=response,
                    )
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                body_path.write_bytes(response.content)
                metadata_path.write_text(
                    json.dumps(
                        {
                            "url": url,
                            "retrieved_at": time.time(),
                            "status_code": response.status_code,
                            "content_type": content_type,
                            "sha256": hashlib.sha256(response.content).hexdigest(),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return CachedResponse(
                    url=url, content=response.content, content_type=content_type, from_cache=False
                )
            except httpx.HTTPError as error:
                last_error = error
                time.sleep((2**attempt) + random.uniform(0, 0.25))
        raise RuntimeError(f"Could not retrieve {url} after retries: {last_error}")

    def get_json(self, url: str, refresh: bool = False) -> dict[str, object]:
        response = self.get(url, refresh=refresh)
        value = json.loads(response.content)
        if not isinstance(value, dict):
            raise TypeError(f"Expected a JSON object at {url}.")
        return value
