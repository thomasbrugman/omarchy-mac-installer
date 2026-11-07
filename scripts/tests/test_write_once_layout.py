# SPDX-License-Identifier: MIT
"""Tests for the write-once layout planner."""

import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "write-once-layout.py"

_spec = importlib.util.spec_from_file_location("write_once_layout", SCRIPT)
layout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout)

MiB = 1 << 20
GiB = 1 << 30


def mac_disk(**overrides):
    """A MacBook-shaped disk: macOS, then stub, ESP and RecoveryOS."""
    values = dict(
        macos_offset=1_000 * MiB,
        macos_size=230 * GiB,
        stub_offset=1_000 * MiB + 230 * GiB,
        stub_size=6 * GiB,
        esp_offset=1_000 * MiB + 236 * GiB,
        esp_size=500 * MiB,
        recovery_offset=1_000 * MiB + 237 * GiB,
    )
    values.update(overrides)
    return values


class PlanTests(unittest.TestCase):
    def test_root_and_boot_fill_the_macos_extent_exactly(self):
        disk = mac_disk()
        result = layout.plan(**disk)
        self.assertEqual(result["root"]["offset_bytes"], disk["macos_offset"])
        self.assertEqual(
            result["root"]["offset_bytes"] + result["root"]["size_bytes"],
            result["boot"]["offset_bytes"],
        )
        self.assertEqual(
            result["boot"]["offset_bytes"] + result["boot"]["size_bytes"],
            disk["macos_offset"] + disk["macos_size"],
        )
        self.assertEqual(result["copied_bytes"], 0)

    def test_nothing_else_moves(self):
        disk = mac_disk()
        result = layout.plan(**disk)
        self.assertEqual(result["unchanged"]["stub"]["offset_bytes"], disk["stub_offset"])
        self.assertEqual(result["unchanged"]["esp"]["offset_bytes"], disk["esp_offset"])
        self.assertEqual(
            result["unchanged"]["recovery"]["offset_bytes"], disk["recovery_offset"]
        )

    def test_root_gets_almost_all_the_freed_space(self):
        disk = mac_disk()
        result = layout.plan(**disk)
        self.assertEqual(
            result["root"]["size_bytes"] + result["boot"]["size_bytes"],
            disk["macos_size"],
        )
        self.assertGreater(result["root"]["size_bytes"], 200 * GiB)

    def test_every_output_is_one_mib_aligned(self):
        result = layout.plan(**mac_disk())
        for part in ("root", "boot"):
            self.assertEqual(result[part]["offset_bytes"] % MiB, 0)
            self.assertEqual(result[part]["size_bytes"] % MiB, 0)

    def test_small_disk_is_refused(self):
        disk = mac_disk(macos_size=30 * GiB)
        disk["stub_offset"] = disk["macos_offset"] + disk["macos_size"]
        with self.assertRaises(layout.LayoutError):
            layout.plan(**disk)

    def test_macos_overlapping_the_stub_is_refused(self):
        disk = mac_disk()
        disk["stub_offset"] = disk["macos_offset"] + disk["macos_size"] - MiB
        with self.assertRaises(layout.LayoutError):
            layout.plan(**disk)

    def test_esp_overlapping_the_stub_is_refused(self):
        with self.assertRaises(layout.LayoutError):
            layout.plan(**mac_disk(esp_offset=1_000 * MiB + 234 * GiB))

    def test_recovery_overlapping_the_esp_is_refused(self):
        with self.assertRaises(layout.LayoutError):
            layout.plan(**mac_disk(recovery_offset=1_000 * MiB + 236 * GiB))

    def test_zero_and_negative_sizes_are_refused(self):
        for bad in (0, -1):
            with self.assertRaises(layout.LayoutError):
                layout.plan(**mac_disk(macos_size=bad))

    def test_non_integer_sizes_are_refused(self):
        with self.assertRaises(layout.LayoutError):
            layout.plan(**mac_disk(macos_size="230G"))

    def test_unaligned_minimums_are_refused(self):
        with self.assertRaises(layout.LayoutError):
            layout.plan(**mac_disk(minimum_root=40 * GiB + 1))


class CommandLineTests(unittest.TestCase):
    def test_prints_json_and_exits_zero(self):
        disk = mac_disk()
        argv = []
        for name, value in disk.items():
            argv += ["--" + name.replace("_", "-"), str(value)]
        self.assertEqual(layout.main(argv), 0)

    def test_refusal_exits_two(self):
        disk = mac_disk(macos_size=1 * GiB)
        disk["stub_offset"] = disk["macos_offset"] + disk["macos_size"]
        argv = []
        for name, value in disk.items():
            argv += ["--" + name.replace("_", "-"), str(value)]
        self.assertEqual(layout.main(argv), 2)

    def test_output_is_valid_json(self):
        disk = mac_disk()
        result = layout.plan(**disk)
        round_tripped = json.loads(json.dumps(result))
        self.assertEqual(round_tripped["schema"], 1)
        self.assertTrue(round_tripped["unverified"])


if __name__ == "__main__":
    unittest.main()
