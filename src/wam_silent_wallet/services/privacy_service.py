"""Network privacy readiness checks for WAM Silent Wallet.

The wallet talks only to a local WAM Core RPC endpoint.  Internet privacy is
therefore determined by the node's own outbound network configuration, not by
proxying the wallet-to-node RPC connection.

This module inspects WAM Core network state and reports whether:
- RPC stays local;
- cookie authentication is present;
- onion networking is reachable through a configured proxy;
- clearnet networks appear to be direct or proxy-routed.

It does not rewrite wam.conf and does not claim that a generic proxy is Tor
unless the Core onion network itself reports a proxy.
"""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class NetworkPrivacySnapshot:
    mode: str
    rpc_loopback: bool
    cookie_available: bool
    network_active: bool
    onion_reachable: bool
    onion_proxy: str | None
    ipv4_reachable: bool
    ipv4_proxy: str | None
    ipv6_reachable: bool
    ipv6_proxy: str | None
    clearnet_proxy_routed: bool
    warnings: tuple[str, ...]


class NetworkPrivacyService:
    """Inspect WAM Core network privacy state without mutating node config."""

    NETWORK_NAMES = {
        "ipv4",
        "ipv6",
        "onion",
        "i2p",
        "cjdns",
    }

    def __init__(
        self,
        node_service,
    ):
        self.node_service = node_service

    @staticmethod
    def _loopback_rpc(
        rpc_url: str,
    ) -> bool:
        try:
            parsed = urlparse(
                rpc_url
            )
        except Exception:
            return False

        return (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.username is None
            and parsed.password is None
            and parsed.query == ""
            and parsed.fragment == ""
        )

    @staticmethod
    def _network_map(
        network_info: dict,
    ) -> dict[str, dict]:
        if not isinstance(
            network_info,
            dict,
        ):
            raise ValueError(
                "PRIVACY_NETWORK_INFO"
            )

        raw = network_info.get(
            "networks",
            []
        )

        if not isinstance(
            raw,
            list,
        ):
            raise ValueError(
                "PRIVACY_NETWORKS"
            )

        result = {}

        for item in raw:
            if not isinstance(
                item,
                dict,
            ):
                continue

            name = item.get(
                "name"
            )

            if name not in (
                NetworkPrivacyService
                .NETWORK_NAMES
            ):
                continue

            result[name] = item

        return result

    @staticmethod
    def _proxy_value(
        entry: dict | None,
    ) -> str | None:
        if not isinstance(
            entry,
            dict,
        ):
            return None

        value = entry.get(
            "proxy"
        )

        if not isinstance(
            value,
            str,
        ):
            return None

        value = value.strip()

        if not value:
            return None

        return value

    @staticmethod
    def _reachable(
        entry: dict | None,
    ) -> bool:
        if not isinstance(
            entry,
            dict,
        ):
            return False

        return bool(
            entry.get(
                "reachable",
                False,
            )
        )

    @classmethod
    def analyze(
        cls,
        *,
        rpc_url: str,
        cookie_available: bool,
        network_info: dict,
    ) -> NetworkPrivacySnapshot:
        networks = cls._network_map(
            network_info
        )

        onion = networks.get(
            "onion"
        )

        ipv4 = networks.get(
            "ipv4"
        )

        ipv6 = networks.get(
            "ipv6"
        )

        onion_reachable = (
            cls._reachable(
                onion
            )
        )

        onion_proxy = (
            cls._proxy_value(
                onion
            )
        )

        ipv4_reachable = (
            cls._reachable(
                ipv4
            )
        )

        ipv4_proxy = (
            cls._proxy_value(
                ipv4
            )
        )

        ipv6_reachable = (
            cls._reachable(
                ipv6
            )
        )

        ipv6_proxy = (
            cls._proxy_value(
                ipv6
            )
        )

        clearnet_routes = []

        if ipv4_reachable:
            clearnet_routes.append(
                ipv4_proxy is not None
            )

        if ipv6_reachable:
            clearnet_routes.append(
                ipv6_proxy is not None
            )

        clearnet_proxy_routed = (
            bool(clearnet_routes)
            and all(
                clearnet_routes
            )
        )

        rpc_loopback = (
            cls._loopback_rpc(
                rpc_url
            )
        )

        warnings = []

        if not rpc_loopback:
            warnings.append(
                "RPC_NOT_LOOPBACK"
            )

        if not cookie_available:
            warnings.append(
                "RPC_COOKIE_MISSING"
            )

        if not onion_reachable:
            warnings.append(
                "ONION_NOT_REACHABLE"
            )

        if onion_reachable and not onion_proxy:
            warnings.append(
                "ONION_PROXY_MISSING"
            )

        direct_clearnet = (
            (
                ipv4_reachable
                and ipv4_proxy is None
            )
            or (
                ipv6_reachable
                and ipv6_proxy is None
            )
        )

        if direct_clearnet:
            warnings.append(
                "CLEARNET_DIRECT"
            )

        if (
            onion_reachable
            and onion_proxy
            and not direct_clearnet
        ):
            mode = "tor_ready"

        elif onion_reachable and onion_proxy:
            mode = "tor_available_mixed"

        elif (
            ipv4_proxy
            or ipv6_proxy
        ):
            mode = "proxy_partial"

        else:
            mode = "direct"

        return NetworkPrivacySnapshot(
            mode=mode,
            rpc_loopback=rpc_loopback,
            cookie_available=bool(
                cookie_available
            ),
            network_active=bool(
                network_info.get(
                    "networkactive",
                    True,
                )
            ),
            onion_reachable=(
                onion_reachable
            ),
            onion_proxy=onion_proxy,
            ipv4_reachable=(
                ipv4_reachable
            ),
            ipv4_proxy=ipv4_proxy,
            ipv6_reachable=(
                ipv6_reachable
            ),
            ipv6_proxy=ipv6_proxy,
            clearnet_proxy_routed=(
                clearnet_proxy_routed
            ),
            warnings=tuple(
                warnings
            ),
        )

    def snapshot(
        self,
    ) -> NetworkPrivacySnapshot:
        network_info = (
            self.node_service
            .network_info()
        )

        return self.analyze(
            rpc_url=(
                self.node_service
                .rpc_url
            ),
            cookie_available=(
                self.node_service
                .cookie_path
                .is_file()
            ),
            network_info=network_info,
        )
