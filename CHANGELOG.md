# Changes

## 0.24.1 — 2026-10-01

- Sync the 40 files from the ChatGPT cloud skill download without changing their contents.
- Require observed entity context and completed per-cluster entity review before constructing a Report; account for planned entity outcomes before completion.
- Add supplementary XML discovery feeds with per-run success/failure reuse and First Squawk timestamp correction.
- Expand discovery across companies, policy, security, industries and macro events, with a soft 3–8 event selection guide.
- Keep internal entity-review decisions and completion counts out of the stored Report.
- Update the deterministic release builder for the exact cloud package surface, including its two regression files.

Validation: 26 cloud-packaged tests and 10 release-builder tests passed. All 40 cloud files match the repository and installed skill; the GitHub release ZIP is the original cloud archive. Python syntax and archive integrity passed.

The preserved 0.17-era development suite remains incompatible with several current APIs and expectations (270 tests run, 59 failures and 5 errors, including subtest failures). This release does not claim complete legacy regression coverage, live Notion/Workspace Agent acceptance, connector success or schedule changes.

## 0.17.1 — 2026-09-26

- Add original Alpaca → Alpaca Paper Trading read-only market-data fallback, preserving later providers and evidence gates.
- Preserve actual connector, request, feed, timestamps and failures. No paper orders, account changes or account-P/L substitution.
- Add capability and response-shape guidance for the observed Paper Trading data wrapper.
- Normalize hosted skill visibility to CHAT/CODEX.

Validation: 10 packaging tests passed. Existing market-provider suite: 54/57 passed; three pre-existing VIX provider-order expectations fail, with provider implementation unchanged. Other known upstream full-suite issues are not claimed fixed.
