# ClaimCoin helper requirements

The current live ClaimCoin runner assumes a patched local FlareSolverr-style helper, not a stock upstream build.

## Required helper commands
- `request.dom_submit`
  - used by the faucet lane so the already-open `/faucet` form can be submitted from the same live page context
- `request.evaluate`
  - used by the withdraw lane to inspect and solve the live IconCaptcha widget inside the authenticated browser session

## Why this matters
ClaimCoin clearance and some form/captcha state are session-bound on this VPS.
Simple cookie transplant back into normal `requests` is not enough.
So the runner keeps specific actions inside the same helper browser session.

## Current local patch tree used during development
- `/root/.openclaw/workspace/state/flaresolverr-exp/src`

If you clone only the ClaimCoin repo onto a fresh machine, you must make sure the helper you point `cloudflare.endpoint` at already exposes the two commands above.
