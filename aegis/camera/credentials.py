"""Credential storage boundary for camera stream URLs.

The current file provider is intentionally a development-only compatibility
provider.  It keeps credentials out of ``cameras.json`` but is not encrypted;
production deployments must replace it with a secret manager provider.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, Optional, Protocol

logger = logging.getLogger(__name__)


class CredentialStorage(Protocol):
    mode: str

    def save(self, credential_ref: str, secret: str) -> None: ...
    def get(self, credential_ref: str) -> Optional[str]: ...
    def delete(self, credential_ref: str) -> None: ...
    def production_ready(self) -> bool: ...


def production_mode() -> bool:
    return (
        os.getenv("AEGIS_ENV", "").strip().lower() in {"prod", "production"}
        or os.getenv("AEGIS_PRODUCTION", "").strip().lower() == "true"
    )


class DevelopmentFileCredentialStorage:
    """Plaintext development provider, separated from public camera config."""

    mode = "development_file"

    def __init__(self, storage_path: Path | str = "data/cameras/credentials.json"):
        self._storage_path = Path(storage_path)
        self._lock = threading.RLock()
        self._credentials: Dict[str, str] = {}
        self._load()

    def production_ready(self) -> bool:
        return False

    def _guard_production(self) -> None:
        if production_mode() and os.getenv(
            "AEGIS_ALLOW_PLAINTEXT_CAMERA_CREDENTIALS", ""
        ).strip().lower() != "true":
            raise RuntimeError(
                "Plaintext camera credential storage is disabled in production. "
                "Configure a secure CredentialStorage provider."
            )
        if production_mode():
            logger.critical(
                "Plaintext development camera credential storage is enabled in production by explicit override"
            )

    def save(self, credential_ref: str, secret: str) -> None:
        self._guard_production()
        with self._lock:
            self._credentials[credential_ref] = secret
            self._persist()

    def get(self, credential_ref: str) -> Optional[str]:
        with self._lock:
            return self._credentials.get(credential_ref)

    def delete(self, credential_ref: str) -> None:
        with self._lock:
            if credential_ref in self._credentials:
                del self._credentials[credential_ref]
                self._persist()

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
            self._credentials = {
                str(key): str(value)
                for key, value in (payload.get("credentials") or {}).items()
                if isinstance(key, str) and isinstance(value, str)
            }
        except Exception as exc:
            logger.error("Failed to load camera credential storage: %s", exc)
            self._credentials = {}

    def _persist(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._storage_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps({"credentials": self._credentials}, indent=2), encoding="utf-8"
        )
        temporary_path.replace(self._storage_path)
        try:
            os.chmod(self._storage_path, 0o600)
        except OSError:
            # Windows may not support POSIX permissions.  The production guard
            # still prevents this provider from being used by default there.
            pass


def default_credential_storage() -> CredentialStorage:
    storage = DevelopmentFileCredentialStorage()
    if not storage.production_ready():
        if production_mode():
            logger.critical(
                "Camera credential storage is not production-ready. New credential-bearing camera registrations will be rejected."
            )
        else:
            logger.warning(
                "Camera credentials use development_file storage. Configure a secure CredentialStorage provider before production."
            )
    return storage
