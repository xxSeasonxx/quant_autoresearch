## 1. Regression Tests

- [x] 1.1 Add a plateau-after-discard regression test proving terminal survivor snapshots come from the best kept attempt, not the terminal workspace.
- [x] 1.2 Add continuation rejection tests for changed mechanism/falsifier, changed protocol hash, and changed experiment bounds hash.
- [x] 1.3 Add an allowed-continuation test proving param value changes within unchanged bounds do not violate the thesis lock.

## 2. Attempt Snapshots And Terminal Manifest

- [x] 2.1 Write per-attempt source snapshots under each generated attempt artifact directory.
- [x] 2.2 Update terminal manifest payload to expose terminal attempt snapshot and best survivor snapshot separately.
- [x] 2.3 Ensure terminal Train failure manifests do not expose a best survivor snapshot.

## 3. Active Thesis Lock

- [x] 3.1 Add normalized thesis identity and experiment-bounds hashing helpers.
- [x] 3.2 Create `.autoresearch/thesis_lock.json` on the first ordinary attempt.
- [x] 3.3 Reject continuation before quick-run materialization when thesis text, protocol hash, or bounds hash drift from the active lock.

## 4. Verification

- [x] 4.1 Run focused tests for loop identity, snapshots, and lock behavior.
- [x] 4.2 Run the full local test suite.
- [x] 4.3 Run OpenSpec validation/status for the change and update task checkboxes.
