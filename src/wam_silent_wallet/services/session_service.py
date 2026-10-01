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

    def passphrase(self) -> str:
        if self._passphrase is None:
            raise ValueError(
                "SESSION_LOCKED"
            )

        # A short-lived Python str is still created here.
        # Do not retain the returned value anywhere.
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
