# Changes

## 0.17.1 — 2026-09-26

- Add original Alpaca → Alpaca Paper Trading read-only market-data fallback, preserving later providers and evidence gates.
- Preserve actual connector, request, feed, timestamps and failures. No paper orders, account changes or account-P/L substitution.
- Add capability and response-shape guidance for the observed Paper Trading data wrapper.
- Normalize hosted skill visibility to CHAT/CODEX.

Validation: 10 packaging tests passed. Existing market-provider suite: 54/57 passed; three pre-existing VIX provider-order expectations fail, with provider implementation unchanged. Other known upstream full-suite issues are not claimed fixed.
