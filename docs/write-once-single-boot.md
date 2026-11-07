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

## Unverified

None of this has run on a Mac. The open questions are whether a stub-only
payload template is accepted end to end, whether Recovery completes enrollment
on a stub with no root, whether `deleteContainer` succeeds against a full macOS
container, and whether Recovery still offers a macOS reinstall afterwards.
