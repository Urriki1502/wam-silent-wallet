"""PyInstaller hook for coincurve native CFFI backend."""

from PyInstaller.utils.hooks import collect_all


datas, binaries, hiddenimports = collect_all(
    "coincurve"
)

if "coincurve._cffi_backend" not in hiddenimports:
    hiddenimports.append(
        "coincurve._cffi_backend"
    )
