# SPDX-License-Identifier: MIT
"""The stub-only template a single-boot install plans against.

Stage one of the write-once install creates the stub and the ESP and nothing
else: /boot and root are made later, in Recovery, once macOS is gone. These
tests pin the three places that have to know that, and the one place that must
not change: recognising a full install still has to work exactly as it did.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

# The planner imports these pinned asahi-installer modules, which this
# repository does not carry. Only template selection and install detection are
# exercised here, so the stand-ins need no behaviour.
sys.modules.setdefault("osinstall", SimpleNamespace(OSInstaller=None))
sys.modules.setdefault(
    "util", SimpleNamespace(align_down=lambda value, align: value // align * align))
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

import omarchy_planner  # noqa: E402
from omarchy_planner import (  # noqa: E402
    STUB_ONLY_TARGET,
    TARGET,
    PlanningError,
    collect_existing_installs,
    select_template,
)


GIB = 1024**3
MIB = 1024**2
STUB = 5_999_951_872
ESP = 524_288_000
ALIGN = MIB


def full_template(**overrides):
    template = {
        "omarchy_target": TARGET,
        "default_os_name": "Omarchy",
        "minimum_size": 64 * GIB,
    }
    template.update(overrides)
    return template


def stub_only_template(**overrides):
    template = {
        "omarchy_target": STUB_ONLY_TARGET,
        "default_os_name": "Omarchy",
        "minimum_size": ESP,
    }
    template.update(overrides)
    return template


class TemplateSelectionTests(unittest.TestCase):
    def test_a_payload_with_both_templates_selects_by_name(self):
        data = {"os_list": [full_template(), stub_only_template()]}
        self.assertEqual(select_template(data)["omarchy_target"], TARGET)
        self.assertEqual(
            select_template(data, STUB_ONLY_TARGET)["omarchy_target"], STUB_ONLY_TARGET)

    def test_order_never_decides(self):
        forwards = {"os_list": [full_template(), stub_only_template()]}
        backwards = {"os_list": [stub_only_template(), full_template()]}
        for data in (forwards, backwards):
            self.assertEqual(
                select_template(data, STUB_ONLY_TARGET)["minimum_size"], ESP)
            self.assertEqual(select_template(data)["minimum_size"], 64 * GIB)

    def test_a_payload_with_two_of_the_same_kind_is_refused(self):
        data = {"os_list": [stub_only_template(), stub_only_template()]}
        with self.assertRaises(PlanningError):
            select_template(data, STUB_ONLY_TARGET)

    def test_a_payload_without_the_kind_is_refused(self):
        data = {"os_list": [full_template()]}
        with self.assertRaises(PlanningError):
            select_template(data, STUB_ONLY_TARGET)

    def test_the_refusal_names_the_kind_asked_for(self):
        data = {"os_list": [full_template()]}
        with self.assertRaises(PlanningError) as raised:
            select_template(data, STUB_ONLY_TARGET)
        self.assertIn("stub-only", str(raised.exception))


def part(name, offset, size, *, type=None, label=None, uuid=None, free=False,
         os=None, info=None):
    return SimpleNamespace(
        name=name, offset=offset, size=size, type=type, label=label,
        uuid=uuid, free=free, os=os, info=info or {},
    )


def stub_os(label="Omarchy"):
    return SimpleNamespace(stub=True, label=label, vgid="VGID-1")


def stub_and_esp(start=500 * GIB):
    """What a single-boot install that stopped before Recovery looks like."""
    stub = part(
        "disk0s3", start, STUB,
        type="Apple_APFS", uuid="UUID-STUB", os=[stub_os()],
    )
    esp = part(
        "disk0s4", stub.offset + stub.size, ESP,
        type="EFI", uuid="UUID-ESP", info={"VolumeName": "EFI - OMARC"},
    )
    return [stub, esp]


def stub_esp_and_boot(start=500 * GIB):
    """A full install whose root never got made. Not a finished stage one."""
    stub, esp = stub_and_esp(start)
    boot = part(
        "disk0s5", esp.offset + esp.size, 2 * GIB,
        type="Linux Filesystem", uuid="UUID-BOOT",
    )
    return [stub, esp, boot]


class StubOnlyPayloadTests(unittest.TestCase):
    """What a stub-only payload must still carry.

    Stage one does not write boot.img or root.img, but Recovery does, after
    macOS is gone. A payload missing either would stage cleanly and fail at the
    point where there is no going back, so both stay required.
    """

    def test_the_required_members_keep_the_recovery_images(self):
        source = (
            Path(__file__).resolve().parents[1] / "src" / "omarchy_asahi.py"
        ).read_text()
        start = source.index("    def _validate_full_os_package(self):")
        end = source.index("    def _esp_members(self):", start)
        body = source[start:end]
        self.assertIn('"boot.img"', body)
        self.assertIn('"root.img"', body)
        # And the alignment check must not be conditioned on template kind.
        self.assertNotIn("if name in members", body)


class ExistingInstallDetectionTests(unittest.TestCase):
    def test_a_finished_stage_one_is_recognised(self):
        candidates = collect_existing_installs(
            SimpleNamespace(parts=stub_and_esp()), "Omarchy", STUB, ALIGN)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["kind"], "replace")
        self.assertEqual(candidates[0]["source_identifier"], "disk0s3")
        # Its extent covers the stub and the ESP, so removal frees both.
        self.assertEqual(candidates[0]["length_bytes"], (STUB + ESP) // ALIGN * ALIGN)

    def test_a_stub_esp_and_boot_is_not_mistaken_for_a_finished_stage_one(self):
        # A full install with no root is broken, not partial-by-design, and it
        # must not be offered as replaceable.
        self.assertEqual(
            collect_existing_installs(
                SimpleNamespace(parts=stub_esp_and_boot()), "Omarchy", STUB, ALIGN),
            [])

    def test_a_stub_alone_is_not_offered(self):
        parts = stub_and_esp()[:1]
        self.assertEqual(
            collect_existing_installs(
                SimpleNamespace(parts=parts), "Omarchy", STUB, ALIGN),
            [])

    def test_a_two_partition_group_with_the_wrong_esp_is_refused(self):
        stub, esp = stub_and_esp()
        esp.info = {"VolumeName": "EFI"}
        self.assertEqual(
            collect_existing_installs(
                SimpleNamespace(parts=[stub, esp]), "Omarchy", STUB, ALIGN),
            [])


if __name__ == "__main__":
    unittest.main()
