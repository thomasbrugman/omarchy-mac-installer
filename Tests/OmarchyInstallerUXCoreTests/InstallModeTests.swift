#if os(macOS)
  import XCTest

  @testable import OmarchyInstallerUXCore

  /// The numbers on the single-boot screens come from this type, so these
  /// tests pin the arithmetic rather than the copy that shows it.
  final class InstallModeTests: XCTestCase {
    private let gib: UInt64 = 1 << 30

    /// A MacBook Neo-shaped disk: a 6 GB macOS 26 stub, the template's
    /// 524 MB ESP, and a 2 GB /boot.
    private func layout(
      disk: UInt64 = 400_000_000_000,
      macOS: UInt64 = 300_000_000_000,
      stub: UInt64 = 5_999_951_872,
      esp: UInt64 = 524_288_000,
      boot: UInt64 = 2_000_000_000
    ) throws -> SingleBootLayout {
      try SingleBootLayout(
        diskBytes: disk, macOSBytes: macOS, stubBytes: stub, espBytes: esp, bootBytes: boot)
    }

    func testStageOneTakesExactlyTheStubAndTheESP() throws {
      let value = try layout()
      XCTAssertEqual(value.stageOneBytes, 5_999_951_872 + 524_288_000)
      XCTAssertEqual(value.macOSAfterStageOneBytes, 300_000_000_000 - 6_524_239_872)
    }

    func testRecoveryGivesOmarchyWhateverTheContainerHadLeft() throws {
      let value = try layout()
      XCTAssertEqual(value.rootBytes + value.bootBytes, 300_000_000_000 - 6_524_239_872)
      XCTAssertEqual(value.rootBytes, 300_000_000_000 - 6_524_239_872 - 2_000_000_000)
    }

    func testASmallerStubTakesLessFromMacOS() throws {
      // A Mac on older firmware uses the 2.5 GB stub. The screen text is
      // derived, so this is the case where the figure changes on its own.
      let newer = try layout()
      let older = try layout(stub: 2_499_805_184)
      XCTAssertEqual(
        newer.stageOneBytes - older.stageOneBytes, 5_999_951_872 - 2_499_805_184)
      XCTAssertGreaterThan(older.macOSAfterStageOneBytes, newer.macOSAfterStageOneBytes)
    }

    func testTheFractionNeverExceedsOne() throws {
      // A container larger than the reported disk is inconsistent, but the bar
      // must still draw inside its track rather than overflow it.
      let value = try layout(disk: 100_000_000_000, macOS: 300_000_000_000)
      XCTAssertLessThanOrEqual(value.releasedFraction, 1)
      XCTAssertGreaterThan(value.releasedFraction, 0)
    }

    func testTheFractionIsTheShareOmarchyEndsUpWith() throws {
      let value = try layout()
      XCTAssertFalse(value.releasedFraction.isNaN)
      // Omarchy holds the whole container less the stub and the ESP, not the
      // whole container: macOS keeps stage one's bytes until Recovery.
      XCTAssertEqual(
        value.releasedFraction,
        Double(293_475_760_128) / Double(400_000_000_000))
    }

    func testAContainerTooSmallForStageOneIsRefused() {
      XCTAssertThrowsError(
        try layout(macOS: 5_000_000_000)
      ) { error in
        XCTAssertEqual(error as? SingleBootLayoutError, .macOSContainerTooSmall)
      }
    }

    func testAContainerWithNoRoomForBootIsRefused() {
      // Stage one fits, but /boot cannot, so there is no install to plan.
      XCTAssertThrowsError(
        try layout(macOS: 6_524_239_872 + 1_000_000_000)
      ) { error in
        XCTAssertEqual(error as? SingleBootLayoutError, .macOSContainerTooSmall)
      }
    }

    func testZeroSizesAreRefused() {
      for (disk, macOS, stub, esp, boot) in [
        (UInt64(0), 300 * gib, 6 * gib, gib, 2 * gib),
        (400 * gib, 0, 6 * gib, gib, 2 * gib),
        (400 * gib, 300 * gib, 0, gib, 2 * gib),
        (400 * gib, 300 * gib, 6 * gib, 0, 2 * gib),
        (400 * gib, 300 * gib, 6 * gib, gib, 0),
      ] {
        XCTAssertThrowsError(
          try SingleBootLayout(
            diskBytes: disk, macOSBytes: macOS, stubBytes: stub, espBytes: esp,
            bootBytes: boot)
        ) { error in
          XCTAssertEqual(error as? SingleBootLayoutError, .notPositive)
        }
      }
    }

    func testTheTwoModesDifferInWhatTheyPromise() {
      XCTAssertEqual(InstallMode.allCases, [.nextToMacOS, .replaceMacOS])
      XCTAssertNil(InstallMode.nextToMacOS.caution)
      XCTAssertNotNil(InstallMode.replaceMacOS.caution)
      // The ordering is the shipped default: the destructive mode is not first.
      XCTAssertEqual(InstallMode.allCases.first, .nextToMacOS)
    }

    // MARK: Copy reads the layout, never a literal

    func testThePlanLineNamesTheBytesStageOneTakes() throws {
      let value = try layout()
      let line = PlainLanguage.singleBootStageOneLine(value)
      // 6,524,239,872 bytes formats as 7 GB through the app's own formatter.
      XCTAssertTrue(line.contains(PlainLanguage.bytes(value.stageOneBytes)), line)
      XCTAssertTrue(line.contains("Recovery"), line)
    }

    func testThePlanLineFollowsTheStubSize() throws {
      let newer = PlainLanguage.singleBootStageOneLine(try layout())
      let older = PlainLanguage.singleBootStageOneLine(try layout(stub: 2_499_805_184))
      XCTAssertNotEqual(newer, older)
      // The older stub takes 3 GB; the macOS 26 stub takes 7 GB.
      XCTAssertTrue(older.contains("3 GB"), older)
      XCTAssertTrue(newer.contains("7 GB"), newer)
    }

    func testBothBarsUseTheSameLayoutAsTheSentence() throws {
      let value = try layout()
      XCTAssertEqual(
        PlainLanguage.singleBootNowCaption(value),
        "\(PlainLanguage.bytes(300_000_000_000)) · macOS")
      let after = PlainLanguage.singleBootAfterCaption(value)
      XCTAssertTrue(after.hasSuffix("· Omarchy"), after)
      XCTAssertTrue(after.contains(PlainLanguage.bytes(value.omarchyBytes)), after)
    }

    func testTheConfirmationNamesTheShrinkAndTheContainer() throws {
      let value = try layout()
      let body = PlainLanguage.replaceMacOSConfirmationBody(value)
      XCTAssertTrue(body.contains(PlainLanguage.bytes(value.stageOneBytes)), body)
      XCTAssertTrue(body.contains(PlainLanguage.bytes(value.macOSBytes)), body)
      XCTAssertTrue(body.contains("cannot be undone"), body)
      // The sheet must not claim install leaves macOS alone: it does not.
      XCTAssertFalse(body.contains("leaves macOS alone"), body)
    }

    func testTheSimulationIsTheOnlyPlaceTheModeAppears() {
      // Without a Mac to run on, the simulated single-boot scenario is the
      // only environment that turns the gate on, and it carries a layout.
      let environment = InstallerSimulationEnvironment(scenario: .singleBoot, delay: .zero)
      XCTAssertTrue(environment.supportsReplaceMacOS)
      XCTAssertNotNil(environment.singleBootLayout)

      let other = InstallerSimulationEnvironment(scenario: .success, delay: .zero)
      XCTAssertFalse(other.supportsReplaceMacOS)
      XCTAssertNil(other.singleBootLayout)
    }
  }
#endif
