"""Background synchronization core for WAM Silent Wallet.

This module deliberately contains no Qt/UI code.  It coordinates one bounded
sync cycle at a time, applies retry/backoff policy, sanitizes failures and
returns immutable outcomes that the UI layer can consume later.
"""

from dataclasses import dataclass
import re
import threading
import time


_SAFE_ERROR = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


@dataclass(frozen=True)
class SyncOutcome:
    status: str
    node: dict | None
    wallet: dict | None
    error_code: str | None
    consecutive_failures: int
    next_delay_seconds: float
    changed: bool
    started_at_monotonic: float
    finished_at_monotonic: float


class BackgroundSyncService:
    """Run serialized wallet sync cycles without retaining the passphrase."""

    SUCCESS_INTERVAL_SECONDS = 15.0
    BUSY_INTERVAL_SECONDS = 2.0
    RETRY_MIN_SECONDS = 2.0
    RETRY_MAX_SECONDS = 60.0

    def __init__(
        self,
        wallet_service,
        node_service,
        *,
        success_interval_seconds: float = 15.0,
        clock=time.monotonic,
    ):
        if (
            isinstance(
                success_interval_seconds,
                bool,
            )
            or not isinstance(
                success_interval_seconds,
                (int, float),
            )
            or not 2.0
            <= float(success_interval_seconds)
            <= 300.0
        ):
            raise ValueError(
                "CONFIG_SYNC_INTERVAL"
            )

        self.wallet_service = wallet_service
        self.node_service = node_service
        self.success_interval_seconds = float(
            success_interval_seconds
        )
        self._clock = clock

        self._cycle_lock = threading.Lock()
        self._consecutive_failures = 0
        self._last_marker = None
        self._last_success_monotonic = None

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def last_success_monotonic(self):
        return self._last_success_monotonic

    def reset(self):
        self._consecutive_failures = 0
        self._last_marker = None
        self._last_success_monotonic = None

    @staticmethod
    def _error_code(exc: Exception) -> str:
        code = getattr(exc, "code", None)

        if code is not None:
            value = getattr(code, "value", None)

            if isinstance(value, str) and _SAFE_ERROR.fullmatch(value):
                return value

            text = str(code)

            if _SAFE_ERROR.fullmatch(text):
                return text

        text = str(exc)

        if _SAFE_ERROR.fullmatch(text):
            return text

        return type(exc).__name__

    def _retry_delay(self) -> float:
        exponent = max(
            0,
            self._consecutive_failures - 1,
        )

        return min(
            self.RETRY_MAX_SECONDS,
            self.RETRY_MIN_SECONDS
            * (2 ** exponent),
        )

    def _finish(
        self,
        *,
        started: float,
        status: str,
        node=None,
        wallet=None,
        error_code=None,
        next_delay_seconds: float,
        changed: bool = False,
    ) -> SyncOutcome:
        return SyncOutcome(
            status=status,
            node=node,
            wallet=wallet,
            error_code=error_code,
            consecutive_failures=self._consecutive_failures,
            next_delay_seconds=next_delay_seconds,
            changed=changed,
            started_at_monotonic=started,
            finished_at_monotonic=self._clock(),
        )

    def cycle(
        self,
        passphrase,
    ) -> SyncOutcome:
        """
        Execute one background sync cycle.

        The passphrase is consumed only for this call and is never assigned to
        an instance attribute.  The caller remains responsible for the session
        secret lifecycle.
        """
        started = self._clock()

        valid_secret = (
            isinstance(
                passphrase,
                (str, bytes, bytearray, memoryview),
            )
            and len(passphrase) > 0
        )

        if not valid_secret:
            return self._finish(
                started=started,
                status="locked",
                error_code="SESSION_LOCKED",
                next_delay_seconds=self.BUSY_INTERVAL_SECONDS,
            )

        if not self._cycle_lock.acquire(
            blocking=False
        ):
            return self._finish(
                started=started,
                status="cycle_busy",
                error_code="SYNC_CYCLE_BUSY",
                next_delay_seconds=self.BUSY_INTERVAL_SECONDS,
            )

        try:
            try:
                node = (
                    self.node_service
                    .details()
                )
            except Exception as exc:
                self._consecutive_failures += 1

                return self._finish(
                    started=started,
                    status="node_error",
                    error_code=self._error_code(exc),
                    next_delay_seconds=self._retry_delay(),
                )

            if not node.get("ready"):
                self._consecutive_failures += 1

                return self._finish(
                    started=started,
                    status="node_not_ready",
                    node=node,
                    error_code="NODE_NOT_READY",
                    next_delay_seconds=self._retry_delay(),
                )

            try:
                wallet = (
                    self.wallet_service
                    .background_sync_snapshot(
                        passphrase,
                        self.node_service
                        .scanner_chain(),
                    )
                )

                reconcile = getattr(
                    self.wallet_service,
                    "reconcile_payment_journal",
                    None,
                )

                if callable(
                    reconcile
                ):
                    reconciliation = (
                        reconcile(
                            passphrase,
                            self.node_service
                            .scanner_chain(),
                        )
                    )

                    wallet = dict(
                        wallet
                    )

                    wallet[
                        "payment_reconciliation"
                    ] = reconciliation
            except Exception as exc:
                error_code = self._error_code(
                    exc
                )

                if error_code == "SCANNER_BUSY":
                    return self._finish(
                        started=started,
                        status="scanner_busy",
                        node=node,
                        error_code=error_code,
                        next_delay_seconds=self.BUSY_INTERVAL_SECONDS,
                    )

                self._consecutive_failures += 1

                return self._finish(
                    started=started,
                    status="wallet_error",
                    node=node,
                    error_code=error_code,
                    next_delay_seconds=self._retry_delay(),
                )

            marker = (
                node.get("tip"),
                wallet.get("confirmed_atoms"),
                wallet.get("available_atoms"),
                wallet.get("unconfirmed_atoms"),
                wallet.get("pending_spent_atoms"),
                wallet.get("payments_count"),
                wallet.get("history_count"),
                wallet.get(
                    "snapshot_fingerprint"
                ),
            )

            changed = marker != self._last_marker

            self._last_marker = marker
            self._consecutive_failures = 0
            self._last_success_monotonic = (
                self._clock()
            )

            return self._finish(
                started=started,
                status="synced",
                node=node,
                wallet=wallet,
                error_code=None,
                next_delay_seconds=(
                    self.success_interval_seconds
                ),
                changed=changed,
            )

        finally:
            self._cycle_lock.release()
