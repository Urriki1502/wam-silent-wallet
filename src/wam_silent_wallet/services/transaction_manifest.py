"""Immutable transaction approval commitment for WAM Silent Wallet.

A SigningManifest freezes the exact coordinator-approved WSP proposal before
private-key signing occurs.

The manifest deliberately commits to every proposal field that can influence
transaction construction or signing:

- selected input ownership and derivation metadata;
- recipient intents and amounts;
- exact fee;
- change epoch;
- reservation token.

The digest is domain-separated and deterministic. A proposal that changes
after user review must fail closed before signing.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import re


_DOMAIN = b"WAM-SILENT-WALLET/SIGNING-MANIFEST/V1\x00"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_MONEY = 22_000_000 * 100_000_000


@dataclass(frozen=True)
class ManifestInput:
    txid: str
    vout: int
    account: str
    epoch: int
    atoms: int
    public_key: str
    tweak: str
    label: int | None
    k: int

    @classmethod
    def from_coin(
        cls,
        coin,
    ) -> "ManifestInput":
        if not isinstance(
            coin,
            dict,
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        required = {
            "txid",
            "vout",
            "account",
            "epoch",
            "atoms",
            "public_key",
            "tweak",
            "label",
            "k",
        }

        if not required <= coin.keys():
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        txid = coin["txid"]
        public_key = coin["public_key"]
        tweak = coin["tweak"]
        account = coin["account"]
        vout = coin["vout"]
        epoch = coin["epoch"]
        atoms = coin["atoms"]
        label = coin["label"]
        k = coin["k"]

        if (
            not isinstance(txid, str)
            or _HEX64.fullmatch(txid) is None
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            type(vout) is not int
            or not 0 <= vout < 2**32
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            not isinstance(account, str)
            or not account
            or len(account) > 128
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            type(epoch) is not int
            or epoch < 0
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            type(atoms) is not int
            or not 1 <= atoms <= _MAX_MONEY
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            not isinstance(public_key, str)
            or _HEX64.fullmatch(
                public_key
            ) is None
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            not isinstance(tweak, str)
            or _HEX64.fullmatch(
                tweak
            ) is None
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            label is not None
            and (
                type(label) is not int
                or not 0 <= label < 2**32
            )
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            type(k) is not int
            or not 0 <= k < 2323
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        return cls(
            txid=txid,
            vout=vout,
            account=account,
            epoch=epoch,
            atoms=atoms,
            public_key=public_key,
            tweak=tweak,
            label=label,
            k=k,
        )


@dataclass(frozen=True)
class ManifestIntent:
    code: str
    atoms: int

    @classmethod
    def from_intent(
        cls,
        intent,
    ) -> "ManifestIntent":
        code = getattr(
            intent,
            "code",
            None,
        )

        atoms = getattr(
            intent,
            "atoms",
            None,
        )

        if (
            not isinstance(code, str)
            or not code
            or len(code) > 256
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INTENT"
            )

        if (
            type(atoms) is not int
            or not 330 <= atoms <= _MAX_MONEY
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INTENT"
            )

        return cls(
            code=code,
            atoms=atoms,
        )


@dataclass(frozen=True)
class SigningManifest:
    version: int
    inputs: tuple[ManifestInput, ...]
    intents: tuple[ManifestIntent, ...]
    fee: int
    change_epoch: int
    reservation_token: str
    digest: str

    @staticmethod
    def _canonical_payload(
        *,
        inputs,
        intents,
        fee,
        change_epoch,
        reservation_token,
    ) -> bytes:
        data = {
            "version": 1,
            "inputs": [
                {
                    "txid": item.txid,
                    "vout": item.vout,
                    "account": item.account,
                    "epoch": item.epoch,
                    "atoms": item.atoms,
                    "public_key": item.public_key,
                    "tweak": item.tweak,
                    "label": item.label,
                    "k": item.k,
                }
                for item in inputs
            ],
            "intents": [
                {
                    "code": item.code,
                    "atoms": item.atoms,
                }
                for item in intents
            ],
            "fee": fee,
            "change_epoch": change_epoch,
            "reservation_token": (
                reservation_token
            ),
        }

        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @classmethod
    def from_proposal(
        cls,
        proposal,
    ) -> "SigningManifest":
        if proposal is None:
            raise ValueError(
                "SIGNING_MANIFEST_PROPOSAL"
            )

        coins = getattr(
            proposal,
            "coins",
            None,
        )

        intents_raw = getattr(
            proposal,
            "intents",
            None,
        )

        fee = getattr(
            proposal,
            "fee",
            None,
        )

        change_epoch = getattr(
            proposal,
            "change_epoch",
            None,
        )

        token = getattr(
            proposal,
            "token",
            None,
        )

        if (
            not isinstance(
                coins,
                tuple,
            )
            or not coins
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INPUT"
            )

        if (
            not isinstance(
                intents_raw,
                tuple,
            )
            or not intents_raw
        ):
            raise ValueError(
                "SIGNING_MANIFEST_INTENT"
            )

        if (
            type(fee) is not int
            or not 1 <= fee <= 1_000_000
        ):
            raise ValueError(
                "SIGNING_MANIFEST_FEE"
            )

        if (
            type(change_epoch) is not int
            or change_epoch < 0
        ):
            raise ValueError(
                "SIGNING_MANIFEST_CHANGE"
            )

        if (
            not isinstance(token, str)
            or not token
            or len(token) > 128
        ):
            raise ValueError(
                "SIGNING_MANIFEST_TOKEN"
            )

        inputs = tuple(
            ManifestInput.from_coin(
                coin
            )
            for coin in coins
        )

        intents = tuple(
            ManifestIntent.from_intent(
                intent
            )
            for intent in intents_raw
        )

        canonical = cls._canonical_payload(
            inputs=inputs,
            intents=intents,
            fee=fee,
            change_epoch=change_epoch,
            reservation_token=token,
        )

        digest = sha256(
            _DOMAIN + canonical
        ).hexdigest()

        return cls(
            version=1,
            inputs=inputs,
            intents=intents,
            fee=fee,
            change_epoch=change_epoch,
            reservation_token=token,
            digest=digest,
        )

    def assert_matches(
        self,
        proposal,
    ) -> None:
        current = type(self).from_proposal(
            proposal
        )

        if (
            self.version != current.version
            or not hmac.compare_digest(
                self.digest,
                current.digest,
            )
        ):
            raise ValueError(
                "SIGNING_MANIFEST_MISMATCH"
            )
