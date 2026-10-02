import ast
from pathlib import Path
import unittest


RUNTIME_CALLERS = (
    "src/wam_silent_wallet/main_window.py",
    "src/wam_silent_wallet/pages/receive_page.py",
    "src/wam_silent_wallet/pages/backup_page.py",
    "src/wam_silent_wallet/pages/payments_page.py",
    "src/wam_silent_wallet/pages/send_page.py",
    "src/wam_silent_wallet/services/sync_worker.py",
)


class SecretLeaseCallerMigrationTests(unittest.TestCase):
    def test_runtime_callers_do_not_call_passphrase_method(self):
        root = Path(__file__).resolve().parents[1]

        offenders = []

        for relative in RUNTIME_CALLERS:
            path = root / relative
            tree = ast.parse(
                path.read_text(
                    encoding="utf-8"
                )
            )

            for node in ast.walk(tree):
                if not isinstance(
                    node,
                    ast.Call,
                ):
                    continue

                func = node.func

                if (
                    isinstance(
                        func,
                        ast.Attribute,
                    )
                    and func.attr == "passphrase"
                ):
                    offenders.append(
                        relative
                    )

        self.assertEqual(
            offenders,
            [],
        )

    def test_runtime_callers_use_secret_lease(self):
        root = Path(__file__).resolve().parents[1]

        missing = []

        for relative in RUNTIME_CALLERS:
            text = (
                root
                .joinpath(relative)
                .read_text(
                    encoding="utf-8"
                )
            )

            if ".secret_lease()" not in text:
                missing.append(
                    relative
                )

        self.assertEqual(
            missing,
            [],
        )


if __name__ == "__main__":
    unittest.main()
