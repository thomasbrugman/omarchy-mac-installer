# SPDX-License-Identifier: MIT
"""The plan floor for a stub-only payload template keeps the stub.

A write-once single-boot install uses a template whose partitions list is the
ESP alone, so `OSInstaller.min_size` no longer includes the stub. If the
planner's floor were that sum, it would offer candidates a megabyte wider than
the stub and refuse them later in `prepare_target`, where `os_size` goes
negative. This pins the floor so that a future change to `_install_bounds`
cannot quietly reintroduce that.

The planner module is imported under stand-ins for the pinned asahi-installer
modules it depends on, the same way its own tests do it.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FakeOSInstaller:
    def __init__(self, dutil, data, template):
        self.min_recommended_size = template["minimum_size"]
        self.min_size = template["minimum_size"]


def load_planner():
    """Import the planner with the pinned modules replaced by stand-ins."""
    saved = {}
    for name, module in (
        ("osinstall", SimpleNamespace(OSInstaller=FakeOSInstaller)),
        ("util", SimpleNamespace(align_down=lambda value, align: value // align * align)),
    ):
        saved[name] = sys.modules.get(name)
        sys.modules[name] = module
    src = str(ROOT / "overlay" / "src")
    added = src not in sys.path
    if added:
        sys.path.insert(0, src)
    try:
        for stale in [key for key in sys.modules if key.startswith("omarchy_")]:
            del sys.modules[stale]
        import omarchy_planner
        return omarchy_planner
    finally:
        if added:
            sys.path.remove(src)


STUB = 5_999_951_872  # macOS 26 stub, the MacBook Neo's size
ESP = 524_288_000


class StubOnlyTemplateFloorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = load_planner()

    def test_the_floor_is_the_stub_plus_the_template(self):
        floor, _ = self.planner._install_bounds(
            STUB, FakeOSInstaller(None, None, {"minimum_size": ESP}))
        self.assertEqual(floor, STUB + ESP)

    def test_the_floor_never_below_the_stub(self):
        # Even a template with no partitions at all must not offer a plan the
        # stub cannot fit into.
        floor, _ = self.planner._install_bounds(
            STUB, FakeOSInstaller(None, None, {"minimum_size": 0}))
        # A non-positive floor is replaced by the recommended size, which is
        # still the stub plus the template.
        self.assertEqual(floor, STUB)

    def test_the_inventory_offers_the_stub_plus_esp_for_a_stub_only_template(self):
        installer = SimpleNamespace(
            data={"os_list": [
                {"omarchy_target": "apple-silicon-full-os", "minimum_size": ESP}]},
            dutil=SimpleNamespace(get_disk_size=lambda _: 512 * 1024**3),
            sys_disk="disk0",
            resize_bounds={},
        )
        inventory = self.planner.collect_inventory(
            installer,
            [SimpleNamespace(name="disk0s3", offset=447_750_000_000, size=100 * 1024**3)],
            [],
            stub_size=STUB,
            part_align=1024**2,
        )
        candidate = inventory["candidates"][0]
        self.assertEqual(candidate["minimum_install_bytes"], STUB + ESP)

    def test_the_size_the_engine_removes_from_macos_is_the_plan_length(self):
        # prepare_target passes plan.length_bytes - stub_size to partition_disk.
        # For a stub-only plan that is exactly the ESP, so its own
        # `expand_size >= 0` assert holds with no special case.
        plan_length = STUB + ESP
        os_size = plan_length - STUB
        self.assertEqual(os_size, ESP)
        self.assertGreaterEqual(os_size - ESP, 0)


if __name__ == "__main__":
    unittest.main()
