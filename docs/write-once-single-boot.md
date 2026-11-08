# Write-once single-boot

Two constraints decide this design. Everything else is in the commit message.

## The delete has to happen after enrollment, in the same Recovery session

Enrollment runs in Recovery and lowers the boot policy for the stub's volume
group. Apple checks that policy against the partition table that was present
when the change was authorized. Delete macOS first and the policy is authorized
against a table Apple no longer sees.

So stage one leaves macOS in place, and stage two deletes it, creates `/boot`
and root in the space it leaves, and enrolls, all in one session, after the
password prompt. That rules out every delete-first variant, including a naive
write-once that wipes before enrollment.

## Stage one still shrinks macOS

The engine can only add a partition into free space. `_find_free_extent`
requires a free extent at the planned offset, and a container that fills its
partition leaves none. On a normal Mac the plan is therefore a resize, and
`prepare_target` shrinks the macOS container before it adds the stub.

For a stub-only install that shrink is the stub plus the ESP. The stub is
2,499,805,184 bytes, or 5,999,951,872 on a Mac whose firmware comes from macOS
26. That is the size `omarchy_firmware.stub_size` picks, and it covers the
MacBook Neo (see the ranges in `OmarchyRemovalRecognition.swift`). The ESP is
524 MB. So the shrink is about 3 GB, or about 6.5 GB on the Neo.

Today's install shrinks macOS by the entire installation instead, because its
template also creates `/boot` and root. Dropping those two from the template is
the whole difference, and it is a data change in `Engine/installer_data.json`.

Nothing is copied either way. A resize moves the container's end, not its
blocks. The dual-boot migration copied them, and that is what write-once
removes.

## Enrollment never reads root

The Recovery configuration in `Recovery/Sources/InstallConfiguration.swift`
names the stub's System and Preboot volumes, its Data volume, and the ESP.
Nothing in the account target, the enrollment gate, or the staged payload reads
the root file system. That is why root and `/boot` can be created after the
delete rather than by the engine.

The same reading covers `RecoveryOwnerResolver`: a recovery account is an APFS
volume owner on the stub's Data volume and satisfies the ownership check on its
own, which is what makes this work with no macOS account present.

## What the engine has to change, and why it is blocked

The UI for this is written and behind a gate that defaults to off
(`InstallerEnvironment.supportsReplaceMacOS`). Turning it on needs engine
changes that are pinned by `Engine/source-lock.json`, so they need a lock bump
and a rebuilt archive, and the base archive is not in this checkout.

The template half is arithmetic and works. A stub-only payload template whose
`partitions` list is the ESP alone gives `OSInstaller.min_size` of 524 MB, and
`prepare_target` passes `os_size = plan.length_bytes - stub_size`, which is
exactly the ESP. `partition_disk` then computes `expand_size` of zero and its
own `assert expand_size >= 0` passes. So the sizes line up without a special
case.

Four engine sites still refuse it:

- `omarchy_planner.py:116`, `omarchy_asahi.py:1259` and
  `omarchy_firmware.py:82` each require exactly one template whose
  `omarchy_target` is `apple-silicon-full-os`. A second template with a
  different target makes every one of them raise.
- `omarchy_asahi.py:2120` requires the template's partition list to be exactly
  `EFI`, `Boot`, `Root` in that order. A stub-only template fails that check by
  design.

The fourth one has a consequence outside the obvious. With the template
dropped to the ESP alone, `_install_bounds` computes the plan floor from that
template's `min_size`, which is 524 MB, so the planner would offer candidates a
megabyte wide. The stub is not in that sum. Any plan shorter than the stub then
fails in `prepare_target`, where `os_size` goes negative, which is a refusal
after the point the plan was approved. The floor has to keep the stub even when
the template does not create `/boot` or root.

## Unverified

None of this has run on a Mac. The open questions are whether a stub-only
payload template is accepted end to end, whether Recovery completes enrollment
on a stub with no root, whether `deleteContainer` succeeds against a full macOS
container, and whether Recovery still offers a macOS reinstall afterwards.

One gap is not a question of hardware but of code, and it would bite before any
of those. `collect_existing_installs` (`omarchy_planner.py:218`) recognises an
install as exactly four consecutive partitions. A stub-only install has two, so
an interrupted stage one would not be recognised: the installer would neither
offer to replace it nor refuse, and would plan a second stub beside the first.
That has to be handled with the template change, not after it.
