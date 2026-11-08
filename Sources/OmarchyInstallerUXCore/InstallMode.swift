#if os(macOS)
  import Foundation

  /// How an installation uses this Mac's disk.
  ///
  /// Only `.nextToMacOS` ships today. `.replaceMacOS` describes the write-once
  /// single-boot install, whose engine support does not exist yet, so no
  /// screen offers it unless `InstallerEnvironment.supportsReplaceMacOS` is
  /// true. Keeping the mode here rather than in the view means the copy and
  /// the numbers can be tested without a window.
  public enum InstallMode: String, CaseIterable, Equatable, Sendable {
    /// Keep macOS. Choose either system when the Mac starts.
    case nextToMacOS
    /// Delete macOS, then let Omarchy take the whole disk.
    case replaceMacOS

    public var title: String {
      switch self {
      case .nextToMacOS: "Next to macOS"
      case .replaceMacOS: "Replace macOS"
      }
    }

    public var detail: String {
      switch self {
      case .nextToMacOS:
        "Keep macOS. Choose Omarchy or macOS when the Mac starts."
      case .replaceMacOS:
        "Delete macOS and give its disk to Omarchy."
      }
    }

    /// A second, quieter line for costs that are not about space. Empty when
    /// there is nothing the choice would hide.
    public var caution: String? {
      switch self {
      case .nextToMacOS: nil
      case .replaceMacOS: "This Mac stops getting Apple’s firmware updates."
      }
    }
  }

  /// The partition sizes a single-boot install is built from.
  ///
  /// Every value is supplied, never assumed: the stub size and the ESP size
  /// come from the engine's payload template, and the disk size from the host
  /// inspection. That is what keeps the numbers on screen tied to this Mac
  /// rather than to a comment someone wrote once.
  public struct SingleBootLayout: Equatable, Sendable {
    public let diskBytes: UInt64
    /// The macOS container's size before anything changes.
    public let macOSBytes: UInt64
    /// The stub plus the ESP. Stage one takes exactly this much from macOS.
    public let stageOneBytes: UInt64
    public let bootBytes: UInt64
    /// Everything left in the macOS container's old extent, after `/boot`.
    public let rootBytes: UInt64

    public init(
      diskBytes: UInt64,
      macOSBytes: UInt64,
      stubBytes: UInt64,
      espBytes: UInt64,
      bootBytes: UInt64
    ) throws {
      guard diskBytes > 0, macOSBytes > 0, stubBytes > 0, espBytes > 0, bootBytes > 0 else {
        throw SingleBootLayoutError.notPositive
      }
      let stageOne = stubBytes.addingReportingOverflow(espBytes)
      guard !stageOne.overflow else { throw SingleBootLayoutError.overflow }
      // The freed extent has to survive stage one and still hold /boot.
      guard macOSBytes > stageOne.partialValue else {
        throw SingleBootLayoutError.macOSContainerTooSmall
      }
      let freed = macOSBytes - stageOne.partialValue
      guard freed > bootBytes else {
        throw SingleBootLayoutError.macOSContainerTooSmall
      }
      self.diskBytes = diskBytes
      self.macOSBytes = macOSBytes
      self.stageOneBytes = stageOne.partialValue
      self.bootBytes = bootBytes
      self.rootBytes = freed - bootBytes
    }

    /// What macOS is left with once stage one finishes.
    public var macOSAfterStageOneBytes: UInt64 { macOSBytes - stageOneBytes }
    /// What Omarchy holds once Recovery finishes. It is the whole disk less
    /// the partitions Apple's firmware still needs.
    public var omarchyBytes: UInt64 { rootBytes + bootBytes }
    /// The share of the disk the delete releases, for a zero-to-one bar.
    public var releasedFraction: Double {
      guard diskBytes > 0 else { return 0 }
      return min(1, Double(omarchyBytes) / Double(diskBytes))
    }
  }

  public enum SingleBootLayoutError: Error, Equatable {
    case notPositive
    case overflow
    case macOSContainerTooSmall
  }
#endif
