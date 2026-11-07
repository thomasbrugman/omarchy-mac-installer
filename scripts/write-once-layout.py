#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Plan the write-once single-boot layout for a Mac disk.

Given a disk that has an APFS stub and an ESP but still has macOS, return the
partition table to write in Recovery: macOS replaced by root and /boot, with the
stub, ESP and RecoveryOS left at their existing offsets.

This is a planner. It reads, computes and prints. It never writes a disk. The
Recovery step that applies the result is a separate, reviewed change, because it
deletes data.

Usage:
    write-once-layout.py --stub-offset-bytes N --stub-size-bytes N \
        --esp-offset-bytes N --esp-size-bytes N \
        --recovery-offset-bytes N --macos-offset-bytes N --macos-size-bytes N

It prints one JSON object and exits non-zero, with the reason on stderr, when the
layout is impossible.
"""

import argparse
import json
import sys

ALIGNMENT = 1 << 20  # 1 MiB, the engine's PART_ALIGNMENT
MINIMUM_ROOT_BYTES = 40 * (1 << 30)
MINIMUM_BOOT_BYTES = 2 * (1 << 30)


class LayoutError(ValueError):
    pass


def _positive(name, value):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise LayoutError(f"{name} must be a positive integer")
    return value


def _aligned(name, value):
    if value % ALIGNMENT != 0:
        raise LayoutError(f"{name} must be a multiple of {ALIGNMENT} bytes")
    return value


def plan(
    *,
    macos_offset,
    macos_size,
    stub_offset,
    stub_size,
    esp_offset,
    esp_size,
    recovery_offset,
    minimum_root=MINIMUM_ROOT_BYTES,
    minimum_boot=MINIMUM_BOOT_BYTES,
):
    """Return the offsets and sizes for root and /boot inside the macOS extent.

    Root goes first, at the front of the freed space, and /boot directly after
    it. Both end exactly where the macOS extent ends, so nothing is left
    unallocated and the root grows to fill every byte the delete released.
    """
    for name, value in (
        ("macos offset", macos_offset),
        ("macos size", macos_size),
        ("stub offset", stub_offset),
        ("stub size", stub_size),
        ("esp offset", esp_offset),
        ("esp size", esp_size),
        ("recovery offset", recovery_offset),
    ):
        _positive(name, value)

    hole_start = macos_offset
    hole_end = macos_offset + macos_size

    # The macOS extent must sit before the stub and must not overlap it, or the
    # freed space is not where this plan thinks it is.
    if hole_end > stub_offset:
        raise LayoutError("the macOS extent overlaps the stub")
    if esp_offset < stub_offset + stub_size:
        raise LayoutError("the ESP overlaps the stub")
    if recovery_offset < esp_offset + esp_size:
        raise LayoutError("RecoveryOS overlaps the ESP")

    boot = _aligned("boot size", minimum_boot)
    root_floor = _aligned("root size", minimum_root)
    available = hole_end - hole_start
    required = root_floor + boot
    if available < required:
        raise LayoutError(
            f"the macOS extent is {available} bytes, "
            f"but root and boot need {required}"
        )

    # Root takes everything except /boot, so the two together fill the hole.
    root_size = available - boot
    root_offset = hole_start
    boot_offset = root_offset + root_size

    if boot_offset + boot != hole_end:
        raise LayoutError("internal arithmetic error")
    for name, value in (
        ("root offset", root_offset),
        ("root size", root_size),
        ("boot offset", boot_offset),
        ("boot size", boot),
    ):
        _aligned(name, value)

    return {
        "schema": 1,
        "unverified": True,
        "root": {"offset_bytes": root_offset, "size_bytes": root_size},
        "boot": {"offset_bytes": boot_offset, "size_bytes": boot},
        "unchanged": {
            "stub": {"offset_bytes": stub_offset, "size_bytes": stub_size},
            "esp": {"offset_bytes": esp_offset, "size_bytes": esp_size},
            "recovery": {
                "offset_bytes": recovery_offset,
                "size_bytes": None,
            },
        },
        "freed_bytes": available,
        "copied_bytes": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macos-offset-bytes", type=int, required=True)
    parser.add_argument("--macos-size-bytes", type=int, required=True)
    parser.add_argument("--stub-offset-bytes", type=int, required=True)
    parser.add_argument("--stub-size-bytes", type=int, required=True)
    parser.add_argument("--esp-offset-bytes", type=int, required=True)
    parser.add_argument("--esp-size-bytes", type=int, required=True)
    parser.add_argument("--recovery-offset-bytes", type=int, required=True)
    parser.add_argument("--minimum-root-bytes", type=int, default=MINIMUM_ROOT_BYTES)
    parser.add_argument("--minimum-boot-bytes", type=int, default=MINIMUM_BOOT_BYTES)
    args = parser.parse_args(argv)

    try:
        result = plan(
            macos_offset=args.macos_offset_bytes,
            macos_size=args.macos_size_bytes,
            stub_offset=args.stub_offset_bytes,
            stub_size=args.stub_size_bytes,
            esp_offset=args.esp_offset_bytes,
            esp_size=args.esp_size_bytes,
            recovery_offset=args.recovery_offset_bytes,
            minimum_root=args.minimum_root_bytes,
            minimum_boot=args.minimum_boot_bytes,
        )
    except LayoutError as error:
        print(f"write-once layout refused: {error}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
