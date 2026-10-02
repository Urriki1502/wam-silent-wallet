"""Crash-safe reconciliation for signed payment journals."""

from wam_sp.psbt import PSBT


class PaymentReconciliationService:
    def __init__(
        self,
        journal,
    ):
        self.journal = journal

    @staticmethod
    def _decode_entry(
        entry,
    ):
        try:
            psbt = PSBT.decode(
                entry["signed_psbt"]
            )

            txid = psbt.txid()

        except Exception as exc:
            raise RuntimeError(
                "PAYMENT_RECONCILE_PSBT_INVALID"
            ) from exc

        return (
            psbt,
            txid,
        )

    @staticmethod
    def _reservation_rows(
        wallet,
        token,
    ):
        return (
            wallet
            .scanner
            .store
            .db
            .execute(
                """
                SELECT txid, vout, state
                FROM reservations
                WHERE token=?
                ORDER BY txid, vout
                """,
                (token,),
            )
            .fetchall()
        )

    def reconcile(
        self,
        wallet,
        chain,
    ):
        entries = (
            self.journal
            .unresolved()
        )

        if not entries:
            return {
                "checked": 0,
                "broadcast": 0,
                "uncertain": 0,
                "signed": 0,
                "unresolved": 0,
            }

        mempool = chain.call(
            "getrawmempool"
        )

        if (
            not isinstance(
                mempool,
                list,
            )
            or any(
                not isinstance(
                    txid,
                    str,
                )
                or len(txid) != 64
                for txid in mempool
            )
        ):
            raise RuntimeError(
                "PAYMENT_RECONCILE_MEMPOOL_INVALID"
            )

        mempool = set(
            mempool
        )

        store = (
            wallet
            .scanner
            .store
        )

        db = store.db

        result = {
            "checked": 0,
            "broadcast": 0,
            "uncertain": 0,
            "signed": 0,
            "unresolved": 0,
        }

        for entry in entries:
            result["checked"] += 1

            token = entry[
                "token"
            ]

            state = entry[
                "state"
            ]

            psbt, txid = (
                self._decode_entry(
                    entry
                )
            )

            expected_inputs = set(
                psbt.tx.inputs
            )

            rows = (
                self._reservation_rows(
                    wallet,
                    token,
                )
            )

            if not rows:
                raise RuntimeError(
                    "PAYMENT_RECONCILE_RESERVATION_MISSING"
                )

            reserved_inputs = {
                (
                    row["txid"],
                    row["vout"],
                )
                for row in rows
            }

            if (
                reserved_inputs
                != expected_inputs
            ):
                raise RuntimeError(
                    "PAYMENT_RECONCILE_RESERVATION_MISMATCH"
                )

            states = {
                row["state"]
                for row in rows
            }

            # --------------------------------------------------
            # Crash window:
            # journal fsync completed but mark_signed() did not
            # yet complete.
            # --------------------------------------------------
            if state == "signed_material":
                if not states <= {
                    "draft",
                    "signed",
                }:
                    raise RuntimeError(
                        "PAYMENT_RECONCILE_STATE_MISMATCH"
                    )

                with store.transaction():
                    db.execute(
                        """
                        UPDATE reservations
                        SET state='signed'
                        WHERE token=?
                          AND state='draft'
                        """,
                        (token,),
                    )

                self.journal.transition(
                    token,
                    "signed",
                )

                state = "signed"
                states = {
                    "signed"
                }

            # Any later journal state with a draft reservation
            # violates the irreversible signing ordering.
            elif "draft" in states:
                raise RuntimeError(
                    "PAYMENT_RECONCILE_STATE_MISMATCH"
                )

            # SDK reservation='broadcast' is itself strong
            # evidence: SDK only sets it after sendrawtransaction
            # returned the exact PSBT txid.
            reservation_broadcast = (
                states == {
                    "broadcast"
                }
            )

            confirmed = (
                db.execute(
                    """
                    SELECT 1
                    FROM history
                    WHERE txid=?
                      AND debit>0
                    LIMIT 1
                    """,
                    (txid,),
                )
                .fetchone()
                is not None
            )

            mempool_seen = (
                txid in mempool
                or (
                    db.execute(
                        """
                        SELECT 1
                        FROM mempool_spends
                        WHERE spending=?
                        LIMIT 1
                        """,
                        (txid,),
                    )
                    .fetchone()
                    is not None
                )
            )

            if (
                reservation_broadcast
                or confirmed
                or mempool_seen
            ):
                with store.transaction():
                    db.execute(
                        """
                        UPDATE reservations
                        SET state='broadcast'
                        WHERE token=?
                          AND state IN (
                              'signed',
                              'uncertain',
                              'broadcast'
                          )
                        """,
                        (token,),
                    )

                self.journal.transition(
                    token,
                    "broadcast",
                    txid=txid,
                )

                result[
                    "broadcast"
                ] += 1

                continue

            # --------------------------------------------------
            # broadcast was entered but no definitive result
            # survives.  Preserve the lock as uncertain.
            # --------------------------------------------------
            if state in {
                "broadcasting",
                "uncertain",
            }:
                with store.transaction():
                    db.execute(
                        """
                        UPDATE reservations
                        SET state='uncertain'
                        WHERE token=?
                          AND state IN (
                              'signed',
                              'uncertain'
                          )
                        """,
                        (token,),
                    )

                self.journal.transition(
                    token,
                    "uncertain",
                )

                result[
                    "uncertain"
                ] += 1

                result[
                    "unresolved"
                ] += 1

                continue

            # signed but never observed at broadcast boundary:
            # retain signed lock.  Never silently release it.
            if state == "signed":
                result[
                    "signed"
                ] += 1

                result[
                    "unresolved"
                ] += 1

                continue

            raise RuntimeError(
                "PAYMENT_RECONCILE_STATE_MISMATCH"
            )

        return result
