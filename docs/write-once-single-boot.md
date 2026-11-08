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

## What the engine change is

The engine half is done. `select_template` picks the one template for a target
name, so a payload can carry both the full-OS template and the stub-only one
and they are told apart by name, never by position. `collect_inventory` takes
the target as an argument and defaults to the full-OS one, so every existing
caller plans exactly as before. The adapter's payload contract accepts the ESP
alone for a stub-only template and requires `boot.img` and `root.img` for
every template, because Recovery writes those after macOS is gone.

`collect_existing_installs` also recognises a finished stage one: a stub with
the Omarchy ESP and nothing Linux after it. A stub, ESP and `/boot` without a
root stays refused, since that is a full install that broke rather than a stage
one that finished.

The template half works numerically. With the ESP alone in the partitions list,
`OSInstaller.min_size` is 524 MB, `prepare_target` passes
`os_size = plan.length_bytes - stub_size`, which is exactly the ESP, and
`partition_disk` computes an `expand_size` of zero that satisfies its own
assert. `_install_bounds` adds `stub_size` to the template's `min_size`, so the
plan floor is the stub plus the ESP.

The engine digests are bumped and the lock names
`v0.9.2-omarchy.20261108.00a5b9b333d6`. The rebuild is reproducible here: two
runs of `Engine/rebuild-python-overlay.py` against the published
`installer-v0.9.2-omarchy.28` base produce the same archive. It is not
published, and `docs/engine-versions.md` lists that as a separate step before
the release pipeline can use it.

## What is still missing

The image builder still writes only the full-OS template. Until it emits the
stub-only one, the engine has nothing of that kind to select, so the gate stays
off. Writing it is a change to the metadata every published payload carries,
which is the payload's signed identity in the catalog, so it belongs with a
Mac to qualify it rather than with this branch.

## Unverified

None of this has run on a Mac. The open questions are whether a stub-only
payload template is accepted end to end, whether Recovery completes enrollment
on a stub with no root, whether `deleteContainer` succeeds against a full macOS
container, and whether Recovery still offers a macOS reinstall afterwards.

The engine now recognises a finished stage one, so an install that stopped
before Recovery is offered for replacement rather than duplicated. That part is
no longer a known gap; whether the recognition holds on a real disk is still
unverified, like everything else here.
