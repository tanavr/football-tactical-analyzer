"""Download and cache public JSON. This module performs no normalization."""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from app.data.provider import DataCacheError, DataFormatError, DataNetworkError, DataNotFoundError
from app.models.football import Provenance

DEFAULT_CACHE = Path(__file__).resolve().parents[4] / "data" / "cache" / "statsbomb"


class CachedJSONSource:
    def __init__(self, cache_dir: Optional[Path] = DEFAULT_CACHE, *,
                 revision: str = "master", refresh: bool = False,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        # Accept a branch or commit hash, never arbitrary path components.
        if not revision or not all(c.isalnum() or c in "-_" for c in revision):
            raise ValueError("revision must be a branch name or commit hash without slashes")
        self.base_url = f"https://raw.githubusercontent.com/statsbomb/open-data/{revision}/data"
        self.revision = revision
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.refresh = refresh
        self.transport = transport

    def read(self, path: str) -> tuple[list[dict[str, Any]], Provenance]:
        if not re.fullmatch(r"competitions\.json|matches/[1-9][0-9]*/[1-9][0-9]*\.json|events/[1-9][0-9]*\.json", path):
            raise ValueError("Unsupported open-data resource path")
        url = f"{self.base_url}/{path}"
        key = hashlib.sha256(url.encode()).hexdigest()
        cache = self.cache_dir / f"{key}.json" if self.cache_dir is not None else None
        if cache is not None and cache.exists() and not self.refresh:
            try:
                envelope = json.loads(cache.read_text(encoding="utf-8"))
                text = envelope["body"]
                if not isinstance(text, str):
                    raise ValueError("Cache body must be text")
                provenance = Provenance.model_validate(envelope["provenance"])
                if (provenance.url != url or provenance.source != "statsbomb"
                        or provenance.data_kind != "real" or provenance.revision != self.revision
                        or provenance.sha256 != hashlib.sha256(text.encode()).hexdigest()):
                    raise ValueError("Cache metadata or content hash mismatch")
                return self._decode(text), provenance
            except OSError as exc:
                raise DataCacheError(f"Cannot read cache {cache}") from exc
            except (ValueError, KeyError, TypeError) as exc:
                raise DataFormatError(f"Invalid cache {cache}; retry with refresh=True") from exc

        try:
            with httpx.Client(timeout=30, follow_redirects=True, transport=self.transport) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise DataNotFoundError(f"No public data at {url}") from exc
            raise DataNetworkError(f"Source returned HTTP {exc.response.status_code} for {url}") from exc
        except httpx.RequestError as exc:
            raise DataNetworkError(f"Could not retrieve {url}") from exc
        text = response.text
        rows = self._decode(text)
        provenance = Provenance(source="statsbomb", data_kind="real", url=url,
                                retrieved_at=datetime.now(timezone.utc), revision=self.revision,
                                sha256=hashlib.sha256(text.encode()).hexdigest())
        if cache is not None:
            temporary = None
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache.parent,
                                                 delete=False) as handle:
                    temporary = handle.name
                    json.dump({"body": text, "provenance": provenance.model_dump(mode="json")}, handle)
                os.replace(temporary, cache)
            except OSError as exc:
                raise DataCacheError(f"Cannot write cache {cache}") from exc
            finally:
                if temporary is not None and os.path.exists(temporary):
                    os.unlink(temporary)
        return rows, provenance

    @staticmethod
    def _decode(text: str) -> list[dict[str, Any]]:
        try:
            rows = json.loads(text)
        except ValueError as exc:
            raise DataFormatError("Source did not return valid JSON") from exc
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise DataFormatError("Expected a JSON array of objects")
        return rows
