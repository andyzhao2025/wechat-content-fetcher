# Wechat Sync State Design

**Date:** 2026-07-06  
**Project:** `wechat-content-fetcher`

## Goal

Stabilize the IMA to static-site sync pipeline by replacing the current fragile cron-agent flow with a deterministic local sync state machine that:

- tracks whether a target has completed its first full sync
- performs low-cost daily incremental detection
- supports explicit manual sync after user-reported IMA edits
- performs a monthly deep audit to recover from missed changes
- records audit trails for success, partial completion, quota exhaustion, and publish status

The design assumes IMA is read-only. All workflow state is maintained locally.

## Context

The current project already supports:

- reading article links from IMA
- fetching WeChat article content
- rendering article pages and folder indexes
- generating NotebookLM bundle pages
- preparing a GitHub Pages artifact

Current weaknesses:

- OpenClaw cron is defined as an `agentTurn` natural-language task instead of a deterministic script
- daily runs can fail before execution at the model layer
- IMA quota exhaustion is treated as a hard failure instead of a resumable partial state
- existing state files only store article/page snapshots and cannot represent run reason, partial completion, pending work, or audit history

## Sync Reasons

The sync engine supports three explicit reasons:

### 1. `scheduled_daily`

Daily background sync.

Behavior:

- scan IMA target metadata
- compute target fingerprint
- if fingerprint unchanged and there is no pending work, skip article fetching
- if fingerprint changed, fetch only required articles and rebuild affected outputs
- if quota is exhausted, persist partial state and stop cleanly

### 2. `manual`

Explicit sync after the user tells OpenClaw that IMA content was manually edited.

Behavior:

- treated as an explicit operator action
- allowed to bypass the no-change skip logic
- can re-fetch and rebuild even when the fingerprint appears unchanged
- writes a run record showing the action was user-triggered

### 3. `monthly_audit`

Full monthly reconciliation run.

Behavior:

- always performs a deep run
- ignores daily no-change shortcuts
- rebuilds state from IMA and local content end to end
- corrects any drift that was not visible from daily metadata fingerprinting

## Target-Level State Model

State is maintained per target, where target identity is:

- `knowledge_base_id + folder_id`

State remains local in the configured state file. No IMA write-back is required.

Each target state must contain:

- `target_key`
- `sync_status`
  - `never_started`
  - `partial`
  - `complete`
- `known_article_ids`
- `pending_article_ids`
- `article_pages`
- `article_groups`
- `last_seen_fingerprint`
- `last_successful_fingerprint`
- `last_successful_incremental_sync_at`
- `last_successful_full_sync_at`
- `last_successful_monthly_audit_at`
- `last_quota_exhausted_at`
- `last_run_reason`
- `last_run_status`
- `last_error`

### State semantics

`known_article_ids`
: all article IDs most recently observed in IMA metadata for this target.

`pending_article_ids`
: article IDs that were discovered or re-queued but not fully fetched and rendered because of quota exhaustion, fetch errors, or interrupted execution.

`last_seen_fingerprint`
: fingerprint from the latest IMA metadata scan, even if the run did not finish.

`last_successful_fingerprint`
: fingerprint associated with the last run that completed rendering and state persistence successfully.

`sync_status=partial`
: the target is known to have unfinished work. Daily runs should continue from this state before declaring the target clean.

## Fingerprint Strategy

Daily change detection is based on an IMA metadata fingerprint, not article body content.

Fingerprint input should include, per target:

- article IDs returned by IMA
- group or path assignment for each article
- title when available from the list API

Normalization rules:

- sort all items deterministically
- build a normalized text representation
- hash the normalized representation

This supports low-cost detection for:

- article additions
- article removals
- article moves between groups
- title changes visible from list metadata

### Known limitation

If IMA allows an article body to change while leaving article ID, title, and group unchanged, daily metadata fingerprinting will not detect the edit. The monthly deep audit exists specifically to recover from this class of drift.

## Daily Incremental Behavior

For each target:

1. Read previous target state.
2. Scan IMA metadata and compute `current_fingerprint`.
3. Persist `last_seen_fingerprint`.
4. Determine whether work is needed:
   - if `pending_article_ids` is not empty, continue pending work
   - else if `current_fingerprint != last_successful_fingerprint`, compute delta
   - else skip target
5. Build the fetch queue:
   - newly added article IDs
   - article IDs explicitly marked pending
   - optionally re-queued IDs if path or grouping changed
6. Fetch article bodies for queued IDs only.
7. Render article pages and indexes.
8. Rebuild affected NotebookLM bundles.
9. Update target state:
   - remove completed IDs from `pending_article_ids`
   - update `known_article_ids`, `article_pages`, and `article_groups`
   - set `sync_status=complete` if no pending IDs remain
   - set `last_successful_fingerprint=current_fingerprint` only when target output is consistent

## Manual Sync Behavior

Manual sync is triggered by a natural-language request to OpenClaw, but the execution path must still be deterministic.

Manual behavior:

- call the same local sync command with `reason=manual`
- allow `--force` to bypass no-change skipping
- preserve the same target-level auditing and quota handling as daily sync

This treats user intent as an operator signal, not as a free-form agent workflow.

## Monthly Audit Behavior

Monthly audit is a full reconciliation pass.

For each target:

- rescan metadata
- rebuild the full article fetch plan
- re-fetch and re-render all articles
- rebuild all NotebookLM bundles for the target
- rebuild publish artifacts
- refresh `last_successful_fingerprint`
- mark `last_successful_monthly_audit_at`

If monthly audit hits IMA quota, the run must still write:

- partial target status
- remaining pending IDs
- run log with `quota_exhausted=true`

## Quota Exhaustion Handling

IMA quota exhaustion is not treated as a process-level hard error anymore.

Desired behavior:

- recognize the known IMA quota exhaustion error
- stop the current fetch loop cleanly
- preserve all progress completed so far
- mark the target as `partial`
- queue unfinished article IDs in `pending_article_ids`
- write a run result of `partial`
- return a non-crashing summary suitable for OpenClaw notification

Hard failure is reserved for cases such as:

- invalid config
- unreadable state file
- broken local dependencies
- unrecoverable publish step errors

## Run Audit Log

In addition to the target state file, the system writes append-only run records.

Each run record must include:

- `run_id`
- `started_at`
- `ended_at`
- `reason`
- `status`
  - `success`
  - `partial`
  - `skipped`
  - `failed`
- `targets`
- `fingerprint_before`
- `fingerprint_after`
- `articles_added`
- `articles_removed`
- `articles_fetched`
- `articles_failed`
- `pending_article_ids`
- `quota_exhausted`
- `publish_changed`
- `published`
- `error_summary`

This log is used for:

- operator visibility
- OpenClaw result notification
- later debugging of quota interruptions and partial recovery

## Publish Pipeline

Rendering and Pages publishing remain local filesystem operations controlled by Python.

Recommended flow:

1. run sync
2. decide whether anything changed
3. if changed, rebuild Pages artifact
4. if artifact changed, commit and push using Windows-safe commands
5. emit a concise result summary

The local sync logic, not the OpenClaw agent, decides whether publish work is needed.

## OpenClaw Integration

OpenClaw should no longer own the workflow logic.

Recommended role split:

### Python side

- scan IMA
- evaluate fingerprints
- handle partial state
- render outputs
- build publish artifact
- decide whether commit/push is needed
- return a machine-readable or text summary

### OpenClaw side

- trigger the local command on schedule
- trigger manual command when the user asks
- deliver the summary to WeChat

This removes the fragile `agentTurn` dependency from the nightly workflow.

## CLI Changes

The command-line interface should be extended with explicit execution intent.

Planned additions:

- `--reason scheduled_daily|manual|monthly_audit`
- `--force`
- `--full-rescan`
- `--publish`

Expected patterns:

```powershell
python run_fetcher.py --config config.ima.json --mode ima --reason scheduled_daily
python run_fetcher.py --config config.ima.json --mode ima --reason manual --force
python run_fetcher.py --config config.ima.json --mode ima --reason monthly_audit --full-rescan
python run_fetcher.py --config config.ima.json --mode pages
```

## Windows Compatibility

The previous cron definition included shell syntax that is not valid in PowerShell.

Implementation must ensure:

- no bash-only date substitution in commit messages
- deterministic Windows-compatible git invocation
- no dependency on an LLM to stitch shell commands together

## Testing Strategy

Tests should cover:

- state migration from the old snapshot-only format
- fingerprint stability and delta detection
- daily skip when fingerprint unchanged and no pending work
- partial state creation on quota exhaustion
- resumption from `pending_article_ids`
- manual sync forcing work even when fingerprint is unchanged
- monthly audit full rebuild behavior
- publish decision logic when no output changed

## Non-Goals

This design does not include:

- writing data back into IMA
- real-time IMA change subscriptions
- distributed coordination across multiple machines
- replacing GitHub Pages with another deploy target

## Implementation Notes

The current repository already contains useful foundations:

- target snapshot storage
- NotebookLM bundle manifests
- GitHub Pages artifact builder

The implementation should extend those pieces rather than replace them wholesale.
