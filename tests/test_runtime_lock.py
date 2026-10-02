import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from wam_silent_wallet.services.runtime_lock import (
    RuntimeDataLock,
)


class RuntimeDataLockTests(
    unittest.TestCase
):
    def test_second_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            first = RuntimeDataLock(
                Path(root)
            )

            second = RuntimeDataLock(
                Path(root)
            )

            first.acquire()

            try:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "WALLET_ALREADY_RUNNING",
                ):
                    second.acquire()

            finally:
                first.release()

    def test_release_allows_reacquire(self):
        with tempfile.TemporaryDirectory() as root:
            first = RuntimeDataLock(
                Path(root)
            )

            first.acquire()
            first.release()

            second = RuntimeDataLock(
                Path(root)
            )

            second.acquire()

            self.assertTrue(
                second.acquired
            )

            second.release()

    def test_sigkill_releases_os_lock(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            code = r'''
import sys
import time
from pathlib import Path

from wam_silent_wallet.services.runtime_lock import RuntimeDataLock

lock = RuntimeDataLock(
    Path(sys.argv[1])
)

lock.acquire()

print(
    "LOCKED",
    flush=True,
)

time.sleep(120)
'''

            env = dict(
                os.environ
            )

            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    code,
                    str(root),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            try:
                line = (
                    proc.stdout
                    .readline()
                    .strip()
                )

                self.assertEqual(
                    line,
                    "LOCKED",
                )

                contender = (
                    RuntimeDataLock(
                        root
                    )
                )

                with self.assertRaisesRegex(
                    RuntimeError,
                    "WALLET_ALREADY_RUNNING",
                ):
                    contender.acquire()

                proc.kill()
                proc.wait(
                    timeout=5,
                )

                # SIGKILL does not run Python cleanup. The kernel
                # itself must release the process lock.
                deadline = (
                    time.time()
                    + 5
                )

                acquired = False

                while time.time() < deadline:
                    try:
                        contender.acquire()
                        acquired = True
                        break

                    except RuntimeError:
                        time.sleep(
                            0.05
                        )

                self.assertTrue(
                    acquired
                )

                contender.release()

            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(
                        timeout=5
                    )


if __name__ == "__main__":
    unittest.main()


class RuntimeLockFilesystemTests(
    unittest.TestCase
):
    def test_lock_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            target = (
                root
                / "target"
            )

            target.write_text(
                "do-not-touch"
            )

            lock_path = (
                root
                / RuntimeDataLock.LOCK_NAME
            )

            lock_path.symlink_to(
                target
            )

            lock = RuntimeDataLock(
                root
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_RUNTIME_LOCK_OPEN_FAILED",
            ):
                lock.acquire()

            self.assertEqual(
                target.read_text(),
                "do-not-touch",
            )

    def test_lock_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            (
                root
                / RuntimeDataLock.LOCK_NAME
            ).mkdir()

            lock = RuntimeDataLock(
                root
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_RUNTIME_LOCK_OPEN_FAILED",
            ):
                lock.acquire()
