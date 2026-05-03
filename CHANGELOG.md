
## 2026-05-03 - ClaimCoin withdraw helper 500 root-cause fix

- Incident: repeated auto-withdraw failure for `holiskabe@gmail.com` reported as `withdraw helper failed: HTTPError: 500 Server Error for http://127.0.0.1:8195/v1`.
- Root cause evidence:
  - `run-loop-screen.log` showed claim bootstrap failing with proxy `407 Proxy Authentication Required`.
  - `claimcoin-flaresolverr.service` logs showed the 8195 helper returned 500 because Cloudflare blocked `/login` through the configured Proxyrack mobile proxy.
  - Direct proxy smoke confirmed configured Proxyrack proxy failed with 407, while local Surfshark node-01 `127.0.0.1:31001` returned IP `93.185.162.147` and FlareSolverr could fetch `https://claimcoin.in/login` with HTTP 200.
- Fixes:
  - Runtime `accounts.yaml` was switched from the stale Proxyrack mobile proxy to local Surfshark node-01 for both `cloudflare.proxy` and the `holiskabe@gmail.com` account proxy. This file is intentionally not committed because it contains secrets.
  - `CloudflareClient._request()` now wraps FlareSolverr HTTP errors with the response body, so future failures show the real helper message instead of only generic `HTTPError 500`.
  - Added regression coverage in `tests/test_cloudflare_requests_bridge.py` for FlareSolverr HTTP error body propagation.
- Verification:
  - Local proxy smoke via `https://api.ipify.org?format=json` returned Surfshark node-01 IP.
  - `claimcoin-runloop.service` restarted and next cycle succeeded through the helper session.
  - Auto-withdraw success oracle observed: `8428 CCP has been sent to your FaucetPay.io account!`; post balance parsed as `0.0`.
  - `python -m unittest discover -s tests` passed: 29 tests OK.
- Do not casually switch ClaimCoin back to the old Proxyrack credential unless a fresh proxy smoke confirms it no longer returns 407 and FlareSolverr `/login` succeeds through it.

## 2026-05-03 - screen launcher and dashboard

- Moved visible ClaimCoin 24x7 operation from hidden systemd-only run-loop into screen sessions on user request:
  - `claimcoin-24x7` runs the autoclaim loop and tees output to `logs/run-loop-screen.log`.
  - `claimcoin-dashboard` runs a Rich live dashboard showing screens, Cloudflare proxy, accounts, DB table counts, and recent cycles.
- Added `scripts/start-claimcoin-screen.sh` and `scripts/claimcoin_dashboard.py`.
- Runtime account proxy mapping updated in ignored `accounts.yaml`: `holiskabe@gmail.com` uses Surfshark node-01 `127.0.0.1:31001`; disabled `lvtsundere@gmail.com` is preassigned node-02 `127.0.0.1:31002` if re-enabled later.
- Current account status: only `holiskabe@gmail.com` is enabled. `lvtsundere@gmail.com` remains disabled because live login-probe still failed (`301 /login?/login`) and should not be turned on without refreshed working credentials/cookies.

## 2026-05-03 - second ClaimCoin account activation

- Runtime `accounts.yaml` updated to enable `lvtsundere@gmail.com` with a distinct Surfshark proxy from the main account:
  - `holiskabe@gmail.com` -> node-01 `http://127.0.0.1:31001`
  - `lvtsundere@gmail.com` -> node-05 `http://127.0.0.1:31005`
- Node-02, node-03, and node-04 were tested against ClaimCoin login through FlareSolverr and reached LiteSpeed `Bot Verification` instead of the real login form, so they were not used for the second account.
- `lvtsundere@gmail.com` login-probe succeeded through node-05 with HTTP 303 to dashboard. After restarting `claimcoin-24x7`, both accounts are included in the screen run-loop.
- Current known issue: `lvtsundere@gmail.com` claim attempts are reaching submit but returning unparsed HTTP 200 / `unknown_failure` solver verdict in current cycles. Keep monitoring/tuning; do not report it as fully claiming successfully until a success oracle appears.

## 2026-05-03 - per-account Cloudflare helper proxy fix

- Root cause for `lvtsundere@gmail.com` failing while `holiskabe@gmail.com` worked:
  - HTTP account traffic used per-account proxy correctly (`lvtsundere` on Surfshark node-05), but the rendered Cloudflare/recaptcha helper path still used global `cloudflare.proxy` node-01.
  - That mixed node-01 rendered `cf_clearance`/reCAPTCHA token into node-05 HTTP submit. ClaimCoin accepted the POST but redirected `/faucet/verify` to `/` with no SweetAlert, so the runner logged `unparsed claim response status=200`.
  - Manual isolation proved the account itself was valid: `lvtsundere` succeeded when helper and HTTP both used node-01, and then succeeded after the helper was fixed to use account proxy node-05.
- Fix: `_maybe_bootstrap_cloudflare()` now clones Cloudflare config with `account.proxy` for helper requests when an account proxy is set.
- Added regression test `test_account_runner_uses_account_proxy_for_cloudflare_helper`.
- Added unparsed claim response HTML capture under `state/debug-claim-responses/` to preserve future silent redirects/errors.
- Verification: full test suite `30 tests OK`; `claimcoin-24x7` restarted; next live cycle succeeded for both accounts: `holiskabe@gmail.com` added `12.0372 CCP`, `lvtsundere@gmail.com` added `12 CCP`.
