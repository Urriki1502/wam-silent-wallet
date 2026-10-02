"""Persistent runtime configuration for WAM Silent Wallet.

The current desktop build is regtest-only.  This module centralizes mutable
runtime settings without storing wallet passphrases, private keys or RPC
credentials.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse


CONFIG_VERSION = 1
DEFAULT_RPC_URL = "http://127.0.0.1:18443"
DEFAULT_SYNC_INTERVAL_SECONDS = 15.0
DEFAULT_FEE_TIER = "Normal"


@dataclass(frozen=True)
class RuntimeConfig:
    version: int
    network: str
    rpc_url: str
    cookie_path: str
    sync_interval_seconds: float
    fee_tier: str


class ConfigService:
    """Load, validate and atomically persist non-secret runtime settings."""

    ALLOWED_FEE_TIERS = {
        "Economy",
        "Normal",
        "Priority",
    }

    MIN_SYNC_INTERVAL_SECONDS = 2.0
    MAX_SYNC_INTERVAL_SECONDS = 300.0

    def __init__(
        self,
        path: Path | None = None,
    ):
        if path is None:
            path = (
                Path.home()
                / "Library"
                / "Application Support"
                / "WAM Silent Wallet Demo"
                / "config.json"
            )

        self.path = Path(path)

    @staticmethod
    def default_cookie_path() -> str:
        return str(
            Path.home()
            / "wam"
            / "regtest-silent-wallet"
            / "regtest"
            / ".cookie"
        )

    @classmethod
    def defaults(cls) -> RuntimeConfig:
        return RuntimeConfig(
            version=CONFIG_VERSION,
            network="regtest",
            rpc_url=DEFAULT_RPC_URL,
            cookie_path=cls.default_cookie_path(),
            sync_interval_seconds=DEFAULT_SYNC_INTERVAL_SECONDS,
            fee_tier=DEFAULT_FEE_TIER,
        )

    @classmethod
    def validate(
        cls,
        value: RuntimeConfig | dict,
    ) -> RuntimeConfig:
        if isinstance(value, RuntimeConfig):
            data = asdict(value)
        elif isinstance(value, dict):
            data = dict(value)
        else:
            raise ValueError("CONFIG_FORMAT")

        expected = {
            "version",
            "network",
            "rpc_url",
            "cookie_path",
            "sync_interval_seconds",
            "fee_tier",
        }

        if set(data) != expected:
            raise ValueError("CONFIG_FIELDS")

        if data["version"] != CONFIG_VERSION:
            raise ValueError("CONFIG_VERSION")

        if data["network"] != "regtest":
            raise ValueError("CONFIG_NETWORK")

        rpc_url = data["rpc_url"]

        if not isinstance(rpc_url, str):
            raise ValueError("CONFIG_RPC_URL")

        parsed = urlparse(
            rpc_url
        )

        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {
                "",
                "/",
            }
        ):
            raise ValueError("CONFIG_RPC_URL")

        try:
            port = parsed.port
        except ValueError:
            raise ValueError(
                "CONFIG_RPC_URL"
            ) from None

        if (
            port is None
            or not 1 <= port <= 65535
        ):
            raise ValueError("CONFIG_RPC_URL")

        cookie_path = data[
            "cookie_path"
        ]

        if (
            not isinstance(
                cookie_path,
                str,
            )
            or not cookie_path.strip()
        ):
            raise ValueError(
                "CONFIG_COOKIE_PATH"
            )

        cookie = Path(
            cookie_path
        ).expanduser()

        if not cookie.is_absolute():
            raise ValueError(
                "CONFIG_COOKIE_PATH"
            )

        interval = data[
            "sync_interval_seconds"
        ]

        if (
            isinstance(interval, bool)
            or not isinstance(
                interval,
                (int, float),
            )
        ):
            raise ValueError(
                "CONFIG_SYNC_INTERVAL"
            )

        interval = float(
            interval
        )

        if not (
            cls.MIN_SYNC_INTERVAL_SECONDS
            <= interval
            <= cls.MAX_SYNC_INTERVAL_SECONDS
        ):
            raise ValueError(
                "CONFIG_SYNC_INTERVAL"
            )

        fee_tier = data[
            "fee_tier"
        ]

        if fee_tier not in cls.ALLOWED_FEE_TIERS:
            raise ValueError(
                "CONFIG_FEE_TIER"
            )

        return RuntimeConfig(
            version=CONFIG_VERSION,
            network="regtest",
            rpc_url=rpc_url,
            cookie_path=str(cookie),
            sync_interval_seconds=interval,
            fee_tier=fee_tier,
        )

    def load(self) -> RuntimeConfig:
        if not self.path.exists():
            return self.defaults()

        try:
            raw = self.path.read_text(
                encoding="utf-8"
            )
            data = json.loads(raw)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            raise ValueError(
                "CONFIG_READ"
            ) from None

        return self.validate(
            data
        )

    def load_or_create(self) -> RuntimeConfig:
        """
        Load the validated runtime configuration, creating a private default
        file on first run.  Existing invalid files are never overwritten.
        """
        if self.path.exists():
            return self.load()

        return self.save(
            self.defaults()
        )

    def save(
        self,
        config: RuntimeConfig | dict,
    ) -> RuntimeConfig:
        validated = self.validate(
            config
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            os.chmod(
                self.path.parent,
                0o700,
            )
        except OSError:
            pass

        payload = (
            json.dumps(
                asdict(validated),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        descriptor = None
        temporary_path = None

        try:
            descriptor, temporary_name = (
                tempfile.mkstemp(
                    prefix=".config.",
                    suffix=".json.tmp",
                    dir=self.path.parent,
                    text=True,
                )
            )

            temporary_path = Path(
                temporary_name
            )

            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                descriptor = None
                handle.write(
                    payload
                )
                handle.flush()
                os.fsync(
                    handle.fileno()
                )

            try:
                os.chmod(
                    temporary_path,
                    0o600,
                )
            except OSError:
                pass

            os.replace(
                temporary_path,
                self.path,
            )

            temporary_path = None

            try:
                os.chmod(
                    self.path,
                    0o600,
                )
            except OSError:
                pass

            return validated

        finally:
            if descriptor is not None:
                os.close(
                    descriptor
                )

            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink(
                    missing_ok=True
                )

    def update(
        self,
        **changes,
    ) -> RuntimeConfig:
        current = asdict(
            self.load()
        )

        current.update(
            changes
        )

        return self.save(
            current
        )
