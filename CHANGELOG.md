
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
