# Changes

## 0.24.2 — 2026-10-01

- Remove obsolete search-v2, self-contained prompt wording, historical document layout and release-version snapshot tests. Detailed policy is owned by the installed references.
- Remove the test for the retired Collection pagination helper; keep single-Collection rendering and all existing URL, Markdown, property and relation validation checks.
- Update existing plan-validation, Report payload and completion fixtures with explicit entity context/review outcomes. Do not relax required-review gates or change runtime defaults.
- Update provider expectations and fallback examples for Google Finance, TradingView and official Treasury/FRED routes. Preserve partial VIX component provenance and atomic Treasury fallback checks.
- Add independent configuration-transport and current-provider regression files to the installable package; retain package reference and SVG safety checks without coupling them to editorial wording.
- Align the standalone VERSION file with the SKILL.md version label.
- Make the developer test directory a standard Python package so unittest discovery and test fixture imports use the same modules.

Validation: 335 World Memory development tests, 13 release/package tests and 34 independently packaged regressions pass. The 42-file archive is deterministic and matches the installed cloud skill. Runtime Python and operational instructions are unchanged apart from the version label. Live connector, Notion write and scheduled-run behavior are outside this offline maintenance check.

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
