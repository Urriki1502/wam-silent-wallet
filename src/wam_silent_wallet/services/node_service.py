from pathlib import Path

from wam_sdk import Config, CookieAuth, Network, WamClient
from wam_sp.adapters.sdk import SDKChain


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

        config = Config(
            url=rpc_url,
            network=Network.REGTEST,
            auth=CookieAuth(cookie_path),
        )

        self.client = WamClient(config)

        self._scanner_chain = SDKChain(
            self.client,
            allow_broadcast=False,
        )

        self._broadcast_chain = SDKChain(
            self.client,
            allow_broadcast=True,
        )

    def snapshot(self) -> dict:
        status = self.client.status()

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

        return {
            **status,
            "mempool_transactions": len(mempool),
            "tip_time": tip_block.get("time"),
            "tip_tx_count": len(
                tip_block.get("tx", [])
            ),
            "rpc_url": self.rpc_url,
            "cookie_exists": self.cookie_path.is_file(),
        }

    def scanner_chain(self):
        self._scanner_chain.attest()
        return self._scanner_chain

    def broadcast_chain(self):
        self._broadcast_chain.attest()
        return self._broadcast_chain
