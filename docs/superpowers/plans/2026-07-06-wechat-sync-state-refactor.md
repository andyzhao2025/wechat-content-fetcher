# Wechat Sync State Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic sync reasons, target-level sync state, resumable quota-aware partial runs, and run-audit logging to the WeChat IMA sync pipeline.

**Architecture:** Extend the existing state and sync layers instead of replacing them. Add richer target state and run-log persistence, then drive sync behavior through explicit execution reasons (`scheduled_daily`, `manual`, `monthly_audit`) so OpenClaw can invoke deterministic local commands rather than agent-authored shell flows.

**Tech Stack:** Python 3.10+, pytest, existing `wechat-content-fetcher` modules, JSON state files

---

### Task 1: Expand state and runtime models

**Files:**
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\src\wechat_content_fetcher\models.py`
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\src\wechat_content_fetcher\storage.py`
- Test: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\tests\test_state.py`

- [ ] **Step 1: Write failing state persistence tests for upgraded target state**

Add tests for:
- legacy state migration from old snapshot-only JSON
- saving and loading new target fields
- append-only run log persistence

- [ ] **Step 2: Run state tests to confirm failure**

Run: `pytest tests/test_state.py -v`
Expected: FAIL because the richer state and run log structures do not exist yet.

- [ ] **Step 3: Implement richer state dataclasses and storage helpers**

Add:
- target sync state model with status, fingerprints, timestamps, pending IDs, and last error fields
- run log dataclass or equivalent structure
- backward-compatible load path for existing `.qiaomu-state*.json`
- save/load helpers for state and run log files

- [ ] **Step 4: Re-run state tests**

Run: `pytest tests/test_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_state.py src/wechat_content_fetcher/models.py src/wechat_content_fetcher/storage.py
git commit -m "feat: add richer sync state persistence"
```

### Task 2: Add sync reasons, fingerprinting, and quota-aware partial handling

**Files:**
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\src\wechat_content_fetcher\sync.py`
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\src\wechat_content_fetcher\ima_client.py`
- Test: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\tests\test_sync_ima.py`
- Test: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\tests\test_ima_client.py`

- [ ] **Step 1: Write failing sync behavior tests**

Add tests for:
- `scheduled_daily` skipping when fingerprint unchanged and no pending work
- `manual` forcing processing even when unchanged
- quota exhaustion producing `partial` state instead of raising
- pending article IDs being resumed on next run
- `monthly_audit` forcing full rebuild

- [ ] **Step 2: Run targeted sync tests to confirm failure**

Run: `pytest tests/test_sync_ima.py tests/test_ima_client.py -v`
Expected: FAIL because sync reasons, partial status, and fingerprint logic are not implemented.

- [ ] **Step 3: Implement runtime sync behavior**

Add:
- explicit sync reason handling
- target fingerprint calculation from source article metadata
- daily skip logic
- pending queue behavior
- quota exhaustion handling that returns a partial summary and preserves progress
- monthly audit full-rescan behavior

- [ ] **Step 4: Re-run targeted sync tests**

Run: `pytest tests/test_sync_ima.py tests/test_ima_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_sync_ima.py tests/test_ima_client.py src/wechat_content_fetcher/sync.py src/wechat_content_fetcher/ima_client.py
git commit -m "feat: add deterministic sync reasons and partial recovery"
```

### Task 3: Add CLI execution intent and run-audit output

**Files:**
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\src\wechat_content_fetcher\cli.py`
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\run_fetcher.py`
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\README.md`
- Test: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\tests\test_sync_ima.py`

- [ ] **Step 1: Write failing CLI-level tests or assertions**

Add tests or smoke-level assertions for:
- `--reason`
- `--force`
- `--full-rescan`
- non-crashing summary output on partial quota runs

- [ ] **Step 2: Run relevant tests**

Run: `pytest tests/test_sync_ima.py -v`
Expected: FAIL because CLI options and summary behavior are missing.

- [ ] **Step 3: Implement CLI flags and result summaries**

Add:
- explicit CLI arguments for sync reason and force/full-rescan controls
- summary output that distinguishes `success`, `skipped`, `partial`, and `failed`
- README usage updates for deterministic local sync flows

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_sync_ima.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_sync_ima.py src/wechat_content_fetcher/cli.py run_fetcher.py README.md
git commit -m "feat: add explicit sync execution modes"
```

### Task 4: Add deterministic publish helper behavior for Windows-friendly automation

**Files:**
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\src\wechat_content_fetcher\pages.py`
- Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\README.md`
- Create or Modify: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\src\wechat_content_fetcher\publish.py`
- Test: `E:\HCWorkArea\qiaomu\wechat-content-fetcher\tests\test_pages.py`

- [ ] **Step 1: Write failing publish decision tests**

Add tests for:
- detecting whether Pages artifact changed
- producing Windows-safe commit message text or publish metadata
- no-op publish decision when site output is unchanged

- [ ] **Step 2: Run publish tests to confirm failure**

Run: `pytest tests/test_pages.py -v`
Expected: FAIL because publish decision helpers do not exist.

- [ ] **Step 3: Implement deterministic publish helpers**

Add:
- artifact-change decision helper
- Windows-safe commit message generation helper
- README guidance replacing bash-specific examples

- [ ] **Step 4: Re-run publish tests**

Run: `pytest tests/test_pages.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_pages.py src/wechat_content_fetcher/pages.py src/wechat_content_fetcher/publish.py README.md
git commit -m "feat: add deterministic publish helpers"
```

### Task 5: Final verification

**Files:**
- Verify only

- [ ] **Step 1: Run focused test suite**

Run: `pytest tests/test_state.py tests/test_ima_client.py tests/test_sync_ima.py tests/test_pages.py -v`
Expected: PASS

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 3: Manual smoke test existing sync commands**

Run:

```powershell
python run_fetcher.py --config config.example.json --mode fixture
python run_fetcher.py --config config.ima.json --mode pages
```

Expected:
- fixture mode completes successfully
- pages mode prepares artifact successfully

- [ ] **Step 4: Commit any remaining documentation/test cleanup**

```bash
git add README.md docs/superpowers/plans/2026-07-06-wechat-sync-state-refactor.md
git commit -m "docs: record sync state refactor plan"
```
