from contextlib import contextmanager


class SessionService:
    """
    In-memory unlock session for the experimental desktop wallet.

    The passphrase is held as a mutable bytearray so lock() can
    overwrite the stored bytes on a best-effort basis.

    Python cannot guarantee complete process-memory zeroization.
    A production/mainnet wallet should use hardened native secret
    memory and/or an OS credential facility.
    """

    def __init__(
        self,
        wallet_service,
    ):
        self.wallet_service = wallet_service

        self._passphrase = None
        self._public_identity = None

    @property
    def unlocked(self) -> bool:
        return self._passphrase is not None

    @property
    def public_identity(self):
        return self._public_identity

    def unlock(
        self,
        passphrase: str,
    ) -> dict:
        if not isinstance(passphrase, str):
            raise ValueError(
                "PASSPHRASE_REQUIRED"
            )

        if not passphrase:
            raise ValueError(
                "PASSPHRASE_REQUIRED"
            )

        # Validate before creating the session.
        identity = (
            self.wallet_service
            .verify_passphrase(passphrase)
        )

        # If an old session exists, destroy it first.
        self.lock()

        encoded = passphrase.encode(
            "utf-8"
        )

        self._passphrase = bytearray(
            encoded
        )

        self._public_identity = identity

        return identity

    @contextmanager
    def secret_lease(self):
        """
        Yield a short-lived mutable copy of the in-memory passphrase.

        The lease is overwritten on exit.  The session's master bytearray
        remains intact until lock().  This avoids creating a Python str for
        callers that can operate on bytes-like secret material.

        Python still cannot guarantee full process-memory zeroization.
        """
        if self._passphrase is None:
            raise ValueError(
                "SESSION_LOCKED"
            )

        lease = bytearray(
            self._passphrase
        )

        try:
            yield lease

        finally:
            for index in range(
                len(lease)
            ):
                lease[index] = 0

    def passphrase(self) -> str:
        if self._passphrase is None:
            raise ValueError(
                "SESSION_LOCKED"
            )

        # Compatibility path for callers not yet migrated to secret_lease().
        # This creates a short-lived immutable Python str and will be removed
        # once all wallet operations consume bytes-like secret material.
        return self._passphrase.decode(
            "utf-8"
        )

    def lock(self):
        if self._passphrase is not None:
            for index in range(
                len(self._passphrase)
            ):
                self._passphrase[index] = 0

        self._passphrase = None
        self._public_identity = None
