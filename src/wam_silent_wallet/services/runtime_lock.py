"""Exclusive process lock for one wallet data directory.

The lock is advisory and process-scoped.  On normal shutdown it is released
explicitly; on crash/SIGKILL the operating system releases it automatically.
"""

from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path


class RuntimeDataLock:
    LOCK_NAME = ".wallet-runtime.lock"

    def __init__(
        self,
        data_dir: Path,
    ):
        self.data_dir = Path(
            data_dir
        )

        self.path = (
            self.data_dir
            / self.LOCK_NAME
        )

        self._fd = None

    @property
    def acquired(self) -> bool:
        return self._fd is not None

    def acquire(self):
        if self._fd is not None:
            return

        self.data_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            os.chmod(
                self.data_dir,
                0o700,
            )
        except OSError:
            pass

        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(
                os,
                "O_NOFOLLOW",
                0,
            )
        )

        try:
            fd = os.open(
                self.path,
                flags,
                0o600,
            )
        except OSError as exc:
            raise RuntimeError(
                "WALLET_RUNTIME_LOCK_OPEN_FAILED"
            ) from exc

        try:
            try:
                fcntl.flock(
                    fd,
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB,
                )

            except OSError as exc:
                if exc.errno in (
                    errno.EACCES,
                    errno.EAGAIN,
                ):
                    raise RuntimeError(
                        "WALLET_ALREADY_RUNNING"
                    ) from None

                raise RuntimeError(
                    "WALLET_RUNTIME_LOCK_FAILED"
                ) from exc

            os.ftruncate(
                fd,
                0,
            )

            os.write(
                fd,
                (
                    str(os.getpid())
                    + "\n"
                ).encode(
                    "ascii"
                ),
            )

            os.fsync(
                fd
            )

            try:
                os.chmod(
                    self.path,
                    0o600,
                )
            except OSError:
                pass

            self._fd = fd
            fd = None

        finally:
            if fd is not None:
                os.close(fd)

    def release(self):
        fd = self._fd

        if fd is None:
            return

        self._fd = None

        try:
            fcntl.flock(
                fd,
                fcntl.LOCK_UN,
            )
        finally:
            os.close(
                fd
            )

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        self.release()
        return False
