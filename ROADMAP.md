# ClaimCoin Autoclaim Roadmap

## Top-level checklist
- [done] 1. Map live website boundaries
- [in progress] 2. Build HTTP auth/session client
- [done] 3. Build faucet state + claim runner
- [in progress] 4. Integrate captcha solving lane
- [pending] 5. Add multi-account + proxy support
- [in progress] 6. Validate on live account and document exact runbook
- [in progress] 7. Turn live ClaimCoin runs into solver-quality training data
- [in progress] 8. Add withdraw automation + IconCaptcha solver

## 1. Map live website boundaries
- [done] Identify login endpoint, cookies, CSRF, and storage model
- [done] Identify faucet readiness endpoint and claim mutation/request
- [done] Identify captcha type, sitekey, verification lane, and backend token usage
- [done] Identify anti-bot or replay protections
- [done] Build local CLI scaffold that can run bootstrap and claim placeholder per account
- [done] Compare the live recon against Boskuu's working PHP reference script and correct the target model

## 2. Build HTTP auth/session client
- [done] Create base Python project scaffold and CLI entry points
- [done] Create account config, proxy pool, and session-state storage skeletons
- [done] Wire exact ClaimCoin login/session flow after live mapping
- [in progress] Add optional Cloudflare bootstrap hook so the runner can recover from the current front-door blocker without abandoning the HTTP-first model
- [done] Replace naive cookie-transplant assumptions with a helper-session-aware Cloudflare lane when clearance proves session-bound
- [done] Add cookie-import lane so a browser-cleared session can be injected into local HTTP state
- [done] Wire proven login POST target `/auth/login` with CSRF field handling and Origin/Referer headers
- [done] Replace the browser-first fallback assumption with the exact cURL-style header/cookie/login lane from the reference PHP script
- [pending] Test a cURL/TLS-fingerprint lane because Python `requests` still gets 403 where the reference PHP cURL script is expected to work

## 3. Build faucet state + claim runner
- [done] Pin active claim endpoint as `/faucet/verify` from the working PHP reference script
- [done] Pin readiness oracle as `var wait = <seconds>` in faucet HTML
- [done] Port the anti-bot image extraction + ordered-id submit lane
- [done] Port the `Swal.fire('Good job!', ...)` success oracle and next-wait parsing
- [done] Replace synthetic helper post for `/faucet/verify` with a submit method that preserves the live faucet form context
- [done] Add a bounded autoclaim loop command that can keep claiming across waits
- [done] Deploy the current loop into detached `screen` for real long-run observation
- [done] Move the live helper stack off the OpenClaw service cgroup into dedicated systemd services so gateway restarts do not kill ClaimCoin runtime

## 4. Integrate captcha solving lane
- [done] Pin active faucet token field `recaptchav3`
- [done] Pin active reCAPTCHA v3 sitekey `6LdnVw4qAAAAAFPMxvegAK9JcBflI-0tb8YKMxZU`
- [done] Add solver adapter for `antibotlinks`, preferring Boskuu's `antibot-image-solver`
- [done] Add solver adapter for reCAPTCHA v3 token acquisition and harden it using Boskuu's referenced rv3 lane if needed
- [in progress] Validate the live health of the configured `antibot-image-solver` and rv3 services from this VPS
- [done] Add direct anti-bot solver-core fallback for cases where the local HTTP service times out on real ClaimCoin images
- [done] Persist structured anti-bot attempt metadata from live ClaimCoin runs
- [done] Add a real-data `solver-stats` CLI summary over captured attempts
- [in progress] Grow verdict-labeled corpus large enough to measure accept vs reject buckets honestly
- [done] Add reusable IconCaptcha solver module for future targets
- [done] Add reusable IconCaptcha least-repeated-cell solver for ClaimCoin withdraw
- [done] Prefer the standalone local IconCaptcha HTTP API at `http://127.0.0.1:8091/solve`, with core/internal fallback if the API is down
- [pending] Verify whether ClaimCoin login SmartCaptcha is real or only page copy noise

## 8. Add withdraw automation + IconCaptcha solver
- [done] Map live `/withdraw` form fields, methods, and IconCaptcha endpoint usage inside the authenticated helper session
- [done] Prove the IconCaptcha canvas can be extracted from the live widget and solved by grouping repeated icons
- [done] Integrate `withdraw-once` plus per-account withdraw config into the main ClaimCoin project
- [done] Add Telegram bot notification lane for real auto-withdraw attempts with cooldown-based anti-spam
- [done] Add method-specific withdraw fallback so LTC can retry as BTC on provider-insufficient-funds failures
- [pending] Run a real payout only after Boskuu supplies the final wallet + preferred method for production use
- [pending] Push both the standalone IconCaptcha solver repo and the main ClaimCoin repo to GitHub

## 7. Turn live ClaimCoin runs into solver-quality training data
- [done] Capture full per-attempt challenge payloads under `state/antibot-captures/`
- [done] Label attempts with server-grounded verdict buckets from the live faucet response
- [done] Summarize attempt history through `solver-stats`
- [pending] Add confidence-gated second-pass behavior for weak solves
- [pending] Add regression export path so accepted/rejected live samples can become solver tests

## Boundary catalog
| Boundary | Status | Notes |
| --- | --- | --- |
| Auth/session gate | done | Proven login POST target is `/auth/login` with `ci_session` + `csrf_cookie_name` context. The helper-session lane is now real and validated with a working account: `holiskabe@gmail.com / Yuda&4321` reaches authenticated `/dashboard` and `/faucet` using the same mobile-UA helper-session flow. Remaining auth caveat: raw Selenium login from this VPS can still hit post-submit Cloudflare `Just a moment...`, so helper-session auth remains the reliable path for now. |
| Faucet state gate | done | Working PHP reference script proves readiness oracle is `var wait = <seconds>` inside `/faucet` HTML. |
| Captcha gate | in progress | Active faucet lane uses external anti-bot image ordering plus reCAPTCHA v3 token `recaptchav3`. The runner now has direct config hooks for local `antibot-image-solver` and the separate rv3 helper, with Waryono kept as fallback. Withdraw IconCaptcha now prefers the standalone local API `iconcaptcha_endpoint` and falls back to core/internal solvers. Register IconCaptcha and login SmartCaptcha clues should not be confused with the active faucet claim lane. |
| Reward/state mutation gate | done | The earlier `opened multiple forms ... without reloading` blocker was traced to a local parser bug, not an unknown server rule. Real faucet HTML uses `name="csrf_token_name" id="token" value="..."`, while the old parser only matched `name` followed immediately by `value`, so helper submits were sending an empty CSRF field. After fixing parser extraction and switching helper claim submit to same-page DOM submit, live `claim-once` succeeded on `holiskabe@gmail.com` with `Good job!` and a returned next-wait window. New hardening on the same boundary: if helper submit bounces back to a plain ready `/faucet` page with no oracle text, the runner now does one same-session settle probe before calling it unknown. |
| Proxy / network fingerprint gate | pending | Still need to see how stable the pure HTTP lane stays under proxy rotation. |
| Cloudflare clearance helper | in progress | Current code now has a configurable FlareSolverr hook for front-door recovery, and live testing proved it can fetch `/login` on this VPS. The helper-session-aware login lane is now wired and used by `check` and `login-probe`. But clearance still behaves session-bound, because normal `requests` and shell `curl` fall back to `403 cf-mitigated` even after reusing the returned cookies and user-agent. |
| Withdraw gate | in progress | Authenticated `/withdraw` is reachable only through the same helper-session lane. The live form uses `POST /withdraw/withdraw`, fields `method`, `amount`, `wallet`, `_iconcaptcha-token`, `ic-wid`, and `ic-cid`, and a ClaimCoin-specific IconCaptcha challenge asking for the icon shown the least times. The solver lane is now proven on repeated live widgets, and the runner can now notify Telegram on real withdraw attempts, but a real payout still needs Boskuu's final wallet target. |

## Current known state
- Project created on 2026-04-16 after Boskuu requested a full HTTP ClaimCoin faucet autoclaim runner.
- Constraints from Boskuu: full HTTP requests for the main runner, auto login, future multi-account support, future proxy support, captcha bypass can use any suitable existing local bypasser.
- Active workstream now: live flow mapping plus reusable local component audit.
- Local scaffold validation on 2026-04-16: the first raw bootstrap lane received HTTP 403 on `/login` and `/faucet`.
- Correction after Boskuu supplied a working PHP reference script: those 403s were not enough evidence to make browser bootstrap the default path. The active target model is now the exact pure HTTP/cURL flow from the reference script.
- New local capability added in the same work cycle: browser-exported cookies can still be imported into the runner state, but that is now fallback/optional rather than the default first move.
- First public surface inventory is now documented in `docs/SURFACE_MAP.md`. Likely post-login automation candidates are faucet, PTC, shortlinks, coupon, offerwall, achievement, weekly contest, login bonus, and referral income.
- Solver integration contract is now wired in code: local `antibot-image-solver` for anti-bot ordering, separate rv3 helper for reCAPTCHA v3, and Waryono-compatible fallback if those endpoints are not yet healthy.
- Live solver-health checkpoint: local `antibot-image-solver` is up and healthy on Rawon, while the public rv3 Hugging Face endpoint currently returns `500` from this VPS.
- Live auth checkpoint after helper patch: `PYTHONPATH=src python3 -m claimcoin_autoclaim.cli check --config accounts.yaml` now returns `ok=True` via cloudflare helper session, and `login-probe` now returns the narrowed truth oracle `Invalid Details` instead of stopping at the earlier front-door `403` only.
- Live auth checkpoint after mobile-UA helper fix: the helper session now reports the same mobile Chrome UA family as the reference PHP flow and still lands on `Invalid Details`, so the remaining blocker is no longer explained by stale desktop UA parity.
- Live auth comparison checkpoint: current credentials, wrong password, and wrong email all currently collapse to the same helper-session failure shape, while follow-up `/dashboard` and `/faucet` still resolve to homepage. Practical meaning: the current lane now behaves exactly like a generic auth failure, not a hidden partial-login state.
- New positive auth checkpoint: `holiskabe@gmail.com / Yuda&4321` authenticates successfully through the same helper-session lane and reaches `/dashboard` plus `/faucet`.
- New faucet checkpoint from the authenticated account: the page already contains a prefilled hidden `recaptchav3` token, and the local anti-bot solver core can solve the 3-option challenge in `fast` OCR mode.
- New live claim-success checkpoint: the supposed multi-form blocker was closed. Root cause was local CSRF parsing, not a server mystery. After fixing faucet hidden-input extraction, adding a same-page `request.dom_submit` helper command, preferring the direct anti-bot solver core, and retrying helper claims on solver-shaped failures, live `claim-once` now succeeds through the project runner. Sample verified success oracles already seen on `holiskabe@gmail.com` include `Good job!, 31 tokens has been added to your balance success` and `12 CCP has been added to your balance`, with observed cooldowns around 5 to 7 minutes.
- New telemetry checkpoint: live ClaimCoin faucet attempts now persist both summary stats and full capture files. The first verified labeled sample already exists under `state/antibot-captures/20260416T140951.036043Z-holiskabe_at_gmail.com-accepted_success.json`, and `solver-stats` can now report accept rate, provider usage, confidence averages, and recent verdict history from the SQLite state store.
- New autoclaim-loop checkpoint: `claimcoin_autoclaim.cli run-loop --cycles 1` now works end-to-end on the proven live account, chooses loop sleep from returned wait windows, and produced a second accepted anti-bot sample, bringing the live stats snapshot to `2/2 accepted` for the current small sample.
- New deployment checkpoint: the current no-confidence-gate build is now running in detached screen `claimcoin-autoclaim`, logging to `logs/run-loop-screen.log`. First observed screen cycle already completed with a real success entry, so Boskuu can now monitor the live long-run behavior directly.
- New runtime-hosting checkpoint: the repeated helper deaths were traced to infrastructure coupling, not OCR regression. `antibot-solver`, `flaresolverr`, and the live ClaimCoin loop had inherited `/system.slice/openclaw-beta.service`, so OpenClaw restarts killed the whole helper stack via `KillMode=control-group`. The runtime has now been migrated into dedicated systemd units `claimcoin-antibot.service`, `claimcoin-flaresolverr.service`, and `claimcoin-runloop.service`, each verified in its own `/system.slice/claimcoin-*.service` cgroup. Practical meaning: future OpenClaw gateway restarts should no longer automatically kill the ClaimCoin helper stack.
- New withdraw-ops checkpoint: the runner now supports Telegram bot notifications for real withdraw attempts through global config `notifications.telegram`. Threshold-only skip cycles are intentionally silent, and repeated identical withdraw result messages are cooled down so a stuck payout failure does not spam every loop.
- New live-status caution after that migration: the hosting fix is real, but claim-level behavior is still separate from process uptime. After migration the services stayed alive correctly, while one later live attempt still produced an `unknown_failure` shaped authenticated `/faucet` reload with `post_submit_settle_probe` and no success/fail oracle. Treat this as a ClaimCoin/session-flow issue, not proof that the systemd migration failed.
- New recovery checkpoint after the later degraded run: the detached loop depended on two local helpers being alive. `antibot-image-solver` was fine, but FlareSolverr had fallen over locally because the workspace clone lacked its Python venv and crashed on missing `bottle`. After rebuilding `state/flaresolverr-exp/src/.venv`, restarting FlareSolverr, and hardening helper submit with a settle probe for silent `/faucet` reloads, a fresh direct `claim-once` again returned `ok=True` with success text `12.00024 CCP has been added to your balance`.
- New cross-project checkpoint: ClaimCoin now feeds the solver repo's own capture format too. The direct solver-core lane writes provisional records under `state/solver-core-captures/claimcoin/`, and the runner annotates those solver records with the final website verdict after submit. A real `server_reject_antibot` sample is now captured in both layers, which makes it usable for solver-side regression work instead of only project-local logging.
- New authenticated shortlinks checkpoint: real dashboard mapping plus live `/links` inspection now prove the shortlinks wall shape. Current visible cards are `ShrinkEarn`, `Shrinkme`, `Shortano`, `Shortino`, and `EarNow`, each exposed as `/links/go/<id>`. A real `Shrinkme` lane was followed end-to-end: `/links/go/85` redirects to `https://shrinkme.click/G5zGhyl`, our existing shortlink bypass engine resolves that alias to `https://claimcoin.in/links/back/kEQsBGWR1Pl9M2aH0dSu`, and opening that callback inside the authenticated ClaimCoin session returns to `/links` with success oracle `Good job! 120 CCP has been added to your balance` while the `Shrinkme` card quota drops from `Claim 1/1` to `Claim 0/1` and disappears from the post-claim card list.
