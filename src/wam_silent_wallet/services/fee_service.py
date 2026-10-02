"""Node-derived fee policy for the WAM Silent Wallet regtest client."""

from decimal import Decimal, InvalidOperation, ROUND_CEILING


ATOMS_PER_WAM = 100_000_000


class FeePolicyService:
    """
    Read fee policy from the connected WAM Core node.

    WAM Core exposes fee rates in WAM/kvB.  The wallet converts those
    values to integer atoms/vB and always applies a relay/mempool floor.

    Regtest frequently has insufficient estimator history.  In that case
    the policy falls back to the node's relay/mempool floor and applies a
    small tier multiplier.  The fallback is explicit in the returned
    metadata; it is never presented as an estimator result.
    """

    TIERS = {
        "Economy": {
            "target_blocks": 12,
            "mode": "ECONOMICAL",
            "fallback_multiplier": 1,
        },
        "Normal": {
            "target_blocks": 6,
            "mode": "CONSERVATIVE",
            "fallback_multiplier": 2,
        },
        "Priority": {
            "target_blocks": 2,
            "mode": "CONSERVATIVE",
            "fallback_multiplier": 4,
        },
    }

    def __init__(self, node_service):
        self.node_service = node_service

    @staticmethod
    def _rate_from_wam_kvb(value) -> int:
        """
        Convert WAM/kvB to atoms/vB, rounding upward.

        Example:
            0.00001000 WAM/kvB
            = 1,000 atoms/kvB
            = 1 atom/vB
        """
        try:
            rate = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("FEE_RATE_FORMAT") from None

        if not rate.is_finite() or rate <= 0:
            raise ValueError("FEE_RATE_RANGE")

        atoms_per_vb = (
            rate
            * Decimal(ATOMS_PER_WAM)
            / Decimal(1000)
        )

        return max(
            1,
            int(
                atoms_per_vb.to_integral_value(
                    rounding=ROUND_CEILING
                )
            ),
        )

    @staticmethod
    def estimate_vsize(
        input_count: int,
        output_count: int,
    ) -> int:
        """
        Conservative P2TR key-path virtual-size estimate.

        The current WSP wallet spends P2TR key-path coins and creates
        P2TR-style 34-byte scriptPubKeys.  We intentionally round each
        input upward rather than claim an exact serialized vsize here.
        """
        if (
            type(input_count) is not int
            or type(output_count) is not int
            or not 1 <= input_count <= 512
            or not 1 <= output_count <= 256
        ):
            raise ValueError("TX_SIZE_INPUT")

        return (
            11
            + 58 * input_count
            + 43 * output_count
        )

    @classmethod
    def fee_for(
        cls,
        atoms_per_vb: int,
        input_count: int,
        output_count: int,
    ) -> tuple[int, int]:
        if (
            type(atoms_per_vb) is not int
            or not 1 <= atoms_per_vb <= 100_000
        ):
            raise ValueError("FEE_RATE_POLICY")

        vsize = cls.estimate_vsize(
            input_count,
            output_count,
        )

        fee = atoms_per_vb * vsize

        # WSP wallet policy currently caps an absolute fee at 0.01 WAM.
        if not 1 <= fee <= 1_000_000:
            raise ValueError("FEE_POLICY")

        return fee, vsize

    def _rpc(self, method: str, params=None):
        return self.node_service.client._transport.call(
            method,
            [] if params is None else params,
        )

    def quote(self, tier: str) -> dict:
        if tier not in self.TIERS:
            raise ValueError("UNKNOWN_FEE_TIER")

        status = self.node_service.client.status()

        if not status.ready:
            raise ValueError("NODE_NOT_READY")

        policy = self.TIERS[tier]

        floor_rates = []

        try:
            network = self._rpc(
                "getnetworkinfo"
            )

            if isinstance(network, dict):
                for field in (
                    "relayfee",
                    "incrementalfee",
                ):
                    value = network.get(field)

                    if value is not None:
                        try:
                            floor_rates.append(
                                self._rate_from_wam_kvb(
                                    value
                                )
                            )
                        except ValueError:
                            pass
        except Exception:
            pass

        try:
            mempool = self._rpc(
                "getmempoolinfo"
            )

            if isinstance(mempool, dict):
                for field in (
                    "mempoolminfee",
                    "minrelaytxfee",
                    "incrementalrelayfee",
                ):
                    value = mempool.get(field)

                    if value is not None:
                        try:
                            floor_rates.append(
                                self._rate_from_wam_kvb(
                                    value
                                )
                            )
                        except ValueError:
                            pass
        except Exception:
            pass

        # Bitcoin-family default relay floor is commonly 0.00001000/kvB.
        # This is a last-resort floor only when the node exposes none.
        floor_atoms_per_vb = max(
            floor_rates,
            default=1,
        )

        estimated_atoms_per_vb = None

        try:
            estimate = self._rpc(
                "estimatesmartfee",
                [
                    policy["target_blocks"],
                    policy["mode"],
                ],
            )

            if (
                isinstance(estimate, dict)
                and estimate.get("feerate") is not None
            ):
                estimated_atoms_per_vb = (
                    self._rate_from_wam_kvb(
                        estimate["feerate"]
                    )
                )
        except Exception:
            estimated_atoms_per_vb = None

        if estimated_atoms_per_vb is not None:
            atoms_per_vb = max(
                floor_atoms_per_vb,
                estimated_atoms_per_vb,
            )

            source = "estimatesmartfee"

        else:
            atoms_per_vb = (
                floor_atoms_per_vb
                * policy["fallback_multiplier"]
            )

            source = "relay/mempool floor fallback"

        return {
            "tier": tier,
            "target_blocks": policy["target_blocks"],
            "mode": policy["mode"],
            "atoms_per_vb": atoms_per_vb,
            "floor_atoms_per_vb": floor_atoms_per_vb,
            "source": source,
        }
