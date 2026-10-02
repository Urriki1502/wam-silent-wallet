from pathlib import Path

from wam_sdk import Config, CookieAuth, Network, WamClient
from wam_sp.adapters.sdk import SDKChain

from .config_service import RuntimeConfig


class NodeService:
    def __init__(
        self,
        rpc_url: str = "http://127.0.0.1:18443",
        cookie_path: Path | None = None,
    ):
        if cookie_path is None:
            cookie_path = (
                Path.home()
                / "wam"
                / "regtest-silent-wallet"
                / "regtest"
                / ".cookie"
            )

        self.rpc_url = rpc_url
        self.cookie_path = cookie_path

        self._build_clients()

    def _build_clients(self):
        config = Config(
            url=self.rpc_url,
            network=Network.REGTEST,
            auth=CookieAuth(
                self.cookie_path
            ),
        )

        self.client = WamClient(
            config
        )

        self._scanner_chain = SDKChain(
            self.client,
            allow_broadcast=False,
        )

        self._broadcast_chain = SDKChain(
            self.client,
            allow_broadcast=True,
        )

    def reconnect(self):
        """Discard stale SDK/RPC objects for the next operation."""
        self._build_clients()

    @staticmethod
    def _node_error_code(
        exc: Exception,
    ) -> str:
        text = str(exc)

        if text in {
            "NODE_NOT_READY",
            "SDK_CHAIN_NOT_READY",
        }:
            return "NODE_NOT_READY"

        return "NODE_UNAVAILABLE"

    def _raise_node_failure(
        self,
        exc: Exception,
    ):
        code = self._node_error_code(
            exc
        )

        # Rebuild only for a future operation.  Never retry the
        # current RPC implicitly; this is especially important
        # at the transaction broadcast boundary.
        try:
            self.reconnect()
        except Exception:
            pass

        raise RuntimeError(
            code
        ) from exc

    @classmethod
    def from_runtime_config(
        cls,
        runtime_config: RuntimeConfig,
    ):
        if runtime_config.network != "regtest":
            raise ValueError(
                "CONFIG_NETWORK"
            )

        return cls(
            rpc_url=runtime_config.rpc_url,
            cookie_path=Path(
                runtime_config.cookie_path
            ),
        )

    def snapshot(self) -> dict:
        try:
            status = self.client.status()

        except Exception as exc:
            self._raise_node_failure(
                exc
            )

        return {
            "network": status.network.value,
            "blocks": status.blocks,
            "headers": status.headers,
            "ibd": status.initial_download,
            "ready": status.ready,
            "tip": status.tip,
        }

    def details(self) -> dict:
        status = self.snapshot()

        base = {
            **status,
            "mempool_transactions": None,
            "tip_time": None,
            "tip_tx_count": None,
            "rpc_url": self.rpc_url,
            "cookie_exists": (
                self.cookie_path.is_file()
            ),
        }

        # A connected-but-unsynchronized node is not a transport
        # failure.  Do not ask SDKChain to attest until coherent.
        if not status["ready"]:
            return base

        try:
            chain = self.scanner_chain()

            mempool = chain.call(
                "getrawmempool"
            )

            tip_block = chain.call(
                "getblock",
                [
                    status["tip"],
                    1,
                ],
            )

        except RuntimeError:
            raise

        except Exception as exc:
            self._raise_node_failure(
                exc
            )

        return {
            **base,
            "mempool_transactions": len(
                mempool
            ),
            "tip_time": tip_block.get(
                "time"
            ),
            "tip_tx_count": len(
                tip_block.get(
                    "tx",
                    [],
                )
            ),
        }

    def network_info(self) -> dict:
        """
        Read WAM Core P2P network state.

        WAM SDK 0.1 does not currently expose getnetworkinfo on its public
        typed client or WSP SDKChain allowlist.  Keep this bridge explicit,
        read-only and node-local until the SDK grows a typed equivalent.
        """
        status = self.snapshot()

        if not status["ready"]:
            raise ValueError(
                "NODE_NOT_READY"
            )

        try:
            result = (
                self.client
                ._transport
                .call(
                    "getnetworkinfo",
                    [],
                )
            )

        except Exception as exc:
            self._raise_node_failure(
                exc
            )

        if not isinstance(
            result,
            dict,
        ):
            raise ValueError(
                "NETWORK_INFO_FORMAT"
            )

        return result

    def scanner_chain(self):
        try:
            self._scanner_chain.attest()

        except Exception as exc:
            self._raise_node_failure(
                exc
            )

        return self._scanner_chain

    def broadcast_chain(self):
        try:
            self._broadcast_chain.attest()

        except Exception as exc:
            self._raise_node_failure(
                exc
            )

        return self._broadcast_chain
