# ClaimCoin solver strategy

Baseline from Boskuu on 2026-04-16.

## 1. Faucet anti-bot links
- Preferred solver: `antibot-image-solver`
- Repo: `https://github.com/IndraYuda13/antibot-image-solver/`
- Role:
  - solve the ordered image/link challenge from faucet HTML
  - output the ordered ids string used as `antibotlinks`
- Current Python runner status:
  - dedicated `antibot-image-solver` endpoint integration is now wired in config and `CaptchaClient`
  - local service health is now proven on Rawon at `http://127.0.0.1:8010/health`
  - direct solver-core fallback is now also wired through config, and for ClaimCoin it is currently the preferred lane because it has proven more reliable on live challenges than the HTTP wrapper
  - Waryono-compatible adapter is still kept as fallback if the local solver lane is unavailable

## 2. IconCaptcha
- Goal:
  - prepare a dedicated solver because Boskuu expects it to be easy and reusable for future targets
- Current ClaimCoin relevance:
  - not part of the active faucet claim lane seen in the working PHP script
  - now proven as the real captcha gate on authenticated ClaimCoin withdraw
- Action:
  - keep it as a reusable standalone module, but it is no longer just future work because ClaimCoin withdraw already needs it
  - current live-proven heuristic for ClaimCoin withdraw: split the 5-cell canvas strip, measure pairwise visual distance, group repeated cells, then click the group with the smallest count
  - keep optional external-core hooks in the ClaimCoin runner, but also retain the built-in fallback so withdraw stays runnable even before the separate solver repo is installed

## 3. SmartCaptcha
- Current role:
  - investigate what it is doing on login and whether it matters in practice
- Current ClaimCoin relevance:
  - login page text mentions it, but the working PHP reference script does not submit a SmartCaptcha token
- Action:
  - treat as secondary until a live login path proves it is required

## 4. Cloudflare challenge
- If Cloudflare presents Turnstile:
  - use `turnstile-solver-api`
  - repo: `https://github.com/IndraYuda13/turnstile-solver-api`
- If Cloudflare is a normal Cloudflare challenge:
  - use FlareSolverr path
  - expected outputs: cookies, user-agent, and session state that can be reused by the HTTP runner
- Current ClaimCoin relevance:
  - the current VPS/IP still gets `403 cf-mitigated: challenge` on `/login`
  - post-submit login from a real browser can also hit `Just a moment...` on `/auth/login`
- Action:
  - keep the FlareSolverr helper-session lane active in the runner for session-bound clearance and login diagnostics
  - keep Turnstile solver ready only if the live challenge shape later proves to be Turnstile-specific

## 5. reCAPTCHA v3
- Reference resource:
  - `https://huggingface.co/spaces/IndraYuda/rv3/tree/main`
- Current ClaimCoin relevance:
  - active faucet claim lane uses `recaptchav3`
  - current sitekey from working PHP script: `6LdnVw4qAAAAAFPMxvegAK9JcBflI-0tb8YKMxZU`
- Action:
  - use the separate rv3 HTTP endpoint as the preferred recaptcha-v3 helper when it is healthy
  - keep the older Waryono-compatible lane as fallback
  - if the live helper/browser faucet page already contains a prefilled hidden `recaptchav3` token, prefer reusing that page token inside the same helper-session claim lane instead of generating a fresh external token unnecessarily
  - current public Hugging Face rv3 endpoint probed from Rawon returned `500`, so treat the endpoint contract as integrated but the live hosted dependency as not yet healthy from this VPS

## 6. Evidence loop for making the anti-bot solver GG
- ClaimCoin live faucet is now part of the solver-improvement harness, not only the consumer.
- Every live anti-bot attempt should preserve:
  - instruction image
  - option ids + option images
  - solver provider
  - ordered ids
  - confidence
  - elapsed solve time
  - raw/debug solver output when available
  - final server-grounded verdict bucket
- Current verdict buckets in the ClaimCoin runner:
  - `accepted_success`
  - `server_reject_antibot`
  - `server_reject_captcha_or_session`
  - `csrf_or_submit_error`
  - `solver_runtime_error`
- Practical storage now exists in two layers:
  - full JSON captures under `state/antibot-captures/`
  - provisional solver-native records under `state/solver-core-captures/claimcoin/`
  - summarized stats in `state/claimcoin.sqlite3`, queryable through `claimcoin_autoclaim.cli solver-stats`
- The current integration rule is:
  - solver-core capture is written first with provisional verdict `uncertain`
  - ClaimCoin then annotates that same solver record with the final website verdict after submit
  - ClaimCoin also keeps its own richer website-outcome capture for aggregate stats and troubleshooting
- Rule for future tuning:
  - do not tune the anti-bot solver from anecdotes alone anymore
  - use the growing labeled ClaimCoin corpus first, then convert accepted/rejected cases into regression fixtures inside the solver repo

## Engineering rule
- Use the strongest proven lane first.
- ClaimCoin active build order:
  1. Cloudflare front-door handling
  2. login/session persistence
  3. faucet wait and claim submit
  4. validate live health of rv3 and keep antibot service running reliably
  5. recaptcha-v3 solver hardening
  6. post-login surface mapping, faucet + shortlinks + anything else exposed in account
