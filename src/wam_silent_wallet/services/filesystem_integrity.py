"""Private runtime filesystem boundary.

Security goals:
- never follow a runtime symlink;
- reject non-regular files / non-directories;
- reject foreign-owned runtime objects on POSIX;
- reject hard-linked private files;
- canonicalize private directory mode to 0700;
- canonicalize private file mode to 0600.

The mode repair is intentionally limited to files owned by the
current process user.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat


def _assert_owner(
    metadata,
    code: str,
):
    if (
        os.name == "posix"
        and hasattr(os, "geteuid")
        and hasattr(metadata, "st_uid")
        and metadata.st_uid != os.geteuid()
    ):
        raise RuntimeError(
            code
        )


def harden_private_directory(
    path,
    *,
    create: bool,
    code: str,
) -> bool:
    path = Path(
        path
    )

    if path.is_symlink():
        raise RuntimeError(
            code
        )

    if create:
        try:
            path.mkdir(
                parents=True,
                exist_ok=True,
                mode=0o700,
            )
        except OSError as exc:
            raise RuntimeError(
                code
            ) from exc

    flags = os.O_RDONLY

    flags |= getattr(
        os,
        "O_DIRECTORY",
        0,
    )

    flags |= getattr(
        os,
        "O_NOFOLLOW",
        0,
    )

    try:
        descriptor = os.open(
            path,
            flags,
        )

    except FileNotFoundError:
        if not create:
            return False

        raise RuntimeError(
            code
        ) from None

    except OSError as exc:
        raise RuntimeError(
            code
        ) from exc

    try:
        metadata = os.fstat(
            descriptor
        )

        if not stat.S_ISDIR(
            metadata.st_mode
        ):
            raise RuntimeError(
                code
            )

        _assert_owner(
            metadata,
            code,
        )

        if (
            os.name == "posix"
            and hasattr(
                os,
                "fchmod",
            )
        ):
            try:
                os.fchmod(
                    descriptor,
                    0o700,
                )
            except OSError as exc:
                raise RuntimeError(
                    code
                ) from exc

            metadata = os.fstat(
                descriptor
            )

            if (
                stat.S_IMODE(
                    metadata.st_mode
                )
                != 0o700
            ):
                raise RuntimeError(
                    code
                )

    finally:
        os.close(
            descriptor
        )

    return True


def harden_private_file(
    path,
    *,
    required: bool,
    code: str,
) -> bool:
    path = Path(
        path
    )

    if path.is_symlink():
        raise RuntimeError(
            code
        )

    flags = os.O_RDONLY

    flags |= getattr(
        os,
        "O_NOFOLLOW",
        0,
    )

    try:
        descriptor = os.open(
            path,
            flags,
        )

    except FileNotFoundError:
        if required:
            raise RuntimeError(
                code
            ) from None

        return False

    except OSError as exc:
        raise RuntimeError(
            code
        ) from exc

    try:
        metadata = os.fstat(
            descriptor
        )

        if not stat.S_ISREG(
            metadata.st_mode
        ):
            raise RuntimeError(
                code
            )

        _assert_owner(
            metadata,
            code,
        )

        if (
            getattr(
                metadata,
                "st_nlink",
                1,
            )
            != 1
        ):
            raise RuntimeError(
                code
            )

        if (
            os.name == "posix"
            and hasattr(
                os,
                "fchmod",
            )
        ):
            try:
                os.fchmod(
                    descriptor,
                    0o600,
                )
            except OSError as exc:
                raise RuntimeError(
                    code
                ) from exc

            metadata = os.fstat(
                descriptor
            )

            if (
                stat.S_IMODE(
                    metadata.st_mode
                )
                != 0o600
            ):
                raise RuntimeError(
                    code
                )

    finally:
        os.close(
            descriptor
        )

    return True
