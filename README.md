# ClaimCoin Autoclaim

HTTP-first runner for ClaimCoin faucet, with helper-session-backed withdraw support.

## Planned features
- Login with saved HTTP session
- Optional Cloudflare bootstrap hook via FlareSolverr before normal HTTP login
- Faucet state check and claim runner
- Auto-withdraw runner with IconCaptcha solving
- Method-specific fallback from one FaucetPay currency to another on insufficient-funds failures
- Telegram bot notifications for real withdraw attempts
- Captcha-solving adapter boundary
- Multi-account scheduler
- Optional per-account proxy binding
- State/log persistence for safe resume

## Status
- Initial scaffold created
- Live target mapping in progress
- Proven so far:
  - Cloudflare challenge sits in front of the site
  - login form uses `GET /login` then `POST /auth/login`
  - session artifacts include `ci_session` and `csrf_cookie_name`
  - register flow uses IconCaptcha via `/icaptcha/req`
  - active faucet claim lane from Boskuu's PHP reference script is `antibotlinks` + `recaptchav3` via `POST /faucet/verify`
  - current VPS still hits a session-bound Cloudflare gate on raw HTTP, but helper-session login with a working account is proven
  - `claim-once` now has a verified live success path through the helper-session lane on a real account
  - ClaimCoin withdraw page uses helper-session-bound IconCaptcha, and the local least-repeated-icon solver is now live-proven on real ClaimCoin challenges
  - solver telemetry now persists per-attempt antibot captures plus verdict labels from live ClaimCoin runs

## Current practical workflow
1. try direct HTTP login flow first
2. if the front door still returns Cloudflare challenge, use the optional FlareSolverr bootstrap hook to obtain cookies and user-agent context
3. if direct HTTP still cannot carry the authenticated state, keep the claim flow inside the same helper session
4. reuse page-provided hidden `recaptchav3` when present, and solve `antibotlinks` through the direct solver-core lane first with HTTP service fallback
5. submit the live `/faucet/verify` form from the helper page context
6. retry solver-shaped claim failures with a fresh faucet page before giving up
7. keep Waryono-style fallback only for lanes that still need it

## CLI
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli check --config accounts.yaml`
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli login-probe --config accounts.yaml`
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli import-cookies --config accounts.yaml --account lvtsundere@gmail.com --cookies cookies.json`
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli show-state --config accounts.yaml`
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli claim-once --config accounts.yaml`
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli withdraw-once --config accounts.yaml`
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli run-loop --config accounts.yaml --cycles 1`
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli links-probe --config accounts.yaml`
- `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli solver-stats --config accounts.yaml`

## Notes
- Solver plan is tracked in `docs/SOLVER_STRATEGY.md`.
- Surface inventory is tracked in `docs/SURFACE_MAP.md`.
- If `cloudflare.provider: flaresolverr` is configured, bootstrap and login probes can fall back to a FlareSolverr clearance attempt when direct HTTP still gets blocked at the front door.
- `captcha.antibot_endpoint` is meant for Boskuu's local `antibot-image-solver` service.
- `captcha.antibot_core_python` plus `captcha.antibot_core_src` let the runner call the installed anti-bot solver core directly when the HTTP wrapper times out.
- `captcha.iconcaptcha_core_python` plus `captcha.iconcaptcha_core_src` are optional paths for the standalone IconCaptcha solver repo. If unset, the ClaimCoin project uses its built-in proven fallback solver.
- `captcha.recaptcha_v3_endpoint` is meant for the separate rv3 token helper.
- `captcha.provider: hybrid` keeps the older Waryono lane available as fallback while preferring the dedicated endpoints above when configured.
- Auto-withdraw is configured per account under `withdraw:`. The current live page exposes method `4 = Litecoin - FaucetPay` and `5 = Bitcoin - FaucetPay`.
- Optional per-account withdraw fallback is supported with `fallback_method` + `fallback_wallet`. Current live use case: try LTC first, then retry BTC only when ClaimCoin says the faucet lacks funds for the first currency.
- Telegram notifications are configured globally under `notifications.telegram`. The notifier only sends for real withdraw attempts, not for normal threshold skips, and repeated identical messages are cooled down to avoid spam.
- The helper-session withdraw lane assumes the local patched FlareSolverr build already exposes `request.evaluate`, because that is how the IconCaptcha widget is read and clicked inside the live browser session.
- Helper patch assumptions are summarized in `ops/HELPER_REQUIREMENTS.md`.
- Every live ClaimCoin anti-bot attempt now writes a JSON capture under `state/antibot-captures/` plus a summarized row in `state/claimcoin.sqlite3`, so future solver tuning can be driven by real accept/reject data.
- When the direct solver-core lane is used, ClaimCoin also asks `antibot-image-solver` itself to persist a provisional capture under `state/solver-core-captures/claimcoin/`, then links that solver record back to the final website verdict.

## Local files
- `accounts.yaml` for accounts, not committed
- `proxies.txt` for optional proxies, not committed
- `state/` for cookies and session artifacts
- `state/antibot-captures/` for full per-attempt solver corpora from live ClaimCoin runs
- `state/solver-core-captures/claimcoin/` for raw solver-side provisional captures before final website verdict is known
- `logs/` for run logs
