# ClaimCoin protocol notes

## Proven boundaries

### Front-door gate
- Raw HTTP can hit Cloudflare managed challenge before app routes are reachable.
- Earlier plain `requests` probes returned `403` on `/login` or `/faucet`.
- Boskuu's working PHP reference script proves the target logic can be expressed as pure HTTP/cURL, so those first 403s were **not** enough to conclude browser bootstrap is mandatory.
- Follow-up re-test after that correction: a direct system `curl` GET to `/login` with the script-matching mobile Chrome headers still returned `403` `cf-mitigated: challenge` and `Just a moment...` from the current VPS IP. Current narrowed interpretation:
  - browser-first should not be assumed from early blockers alone
  - but in **this environment right now**, plain `requests` and plain `curl` both still hit Cloudflare at the front door
  - a helper boundary does help: local FlareSolverr can fetch `/login` and return real clearance cookies plus login HTML from this VPS
  - but that clearance is not safely transplantable so far, because replaying the returned cookies and matching UA through normal `requests` or shell `curl` still falls back to `403 cf-mitigated`
  - so the remaining blocker is now specifically a **session-bound Cloudflare clearance** problem, not uncertainty about the app route map itself

### Login flow
- Proven page: `GET /login`
- Proven cookies from mapping lane:
  - `ci_session`
  - `csrf_cookie_name`
- Proven form post target:
  - `POST /auth/login`
- Proven form fields:
  - `csrf_token_name`
  - `email`
  - `password`
- Proven useful headers:
  - `Origin: https://claimcoin.in`
  - `Referer: https://claimcoin.in/login`
- Boskuu reference script uses exactly this lane with no explicit browser bootstrap and no explicit captcha field on login.
- Login page HTML currently shows only static SmartCaptcha wording. In the cleared live HTML fetched through FlareSolverr, there is no separate SmartCaptcha script or hidden token field on the page itself.
- Observed replay result from my earlier mapping lane:
  - `303` back to `/login`
  - flash `Invalid Details`
- New helper-session findings after patching the local FlareSolverr source:
  - a real Selenium browser submit from this VPS still gets stuck on `Just a moment...` at `POST /auth/login` for at least 60 seconds, so there is a real post-submit Cloudflare challenge path in this environment
  - the local FlareSolverr experiment was patched so `request.post` now parses form data correctly and no longer corrupts values containing `&`
  - the helper-session lane was also patched to carry the same mobile Chrome user-agent as the reference PHP flow, and the local FlareSolverr experiment was patched to report the active driver UA instead of a stale startup cache
  - after those patches, helper-session login no longer fails at the transport or UA-parity layer, but the server still returns `200 /login` with flash `Invalid Details`
  - follow-up probes from the same helper session also show `/dashboard -> https://claimcoin.in/` and `/faucet -> https://claimcoin.in/` with homepage HTML, not an authenticated dashboard/faucet state
- Current interpretation:
  - the endpoint mapping was correct, and the special-character corruption bug in the helper submit path was real
  - the helper-session lane is now also using the same mobile UA family as the reference PHP flow, and it still lands on `Invalid Details`
  - the same helper session then gets redirected from `/dashboard` and `/faucet` back to homepage, which confirms the session is not silently authenticated despite the form submit succeeding at transport level
  - comparison probes against deliberately wrong credentials currently produce the same outward failure shape: `200 /login`, flash `Invalid Details`, same invalid-message position, and no authenticated follow-up route access
  - that means the current login blocker has narrowed again: either the provided ClaimCoin credentials are not accepted by the site right now, or there is still some site-side requirement that is presented to the server as the same generic `Invalid Details` result
  - SmartCaptcha is still not proven as that missing requirement, because the cleared login HTML still shows only static wording with no submitted token field

### Captcha boundaries
- Register flow is proven to use IconCaptcha.
- Proven backend endpoint:
  - `POST /icaptcha/req`
- Proven actions:
  - `LOAD`
  - `SELECTION`
- Source-oriented note:
  - login page copy mentions SmartCaptcha, but the working PHP reference script does **not** submit a SmartCaptcha token on login, so this login-page clue must be treated as unverified for the actual working auth lane.
- Boskuu reference script proves the active faucet claim lane instead uses:
  - anti-bot image ordering challenge solved externally as `antibotlinks`
  - reCAPTCHA v3 token field `recaptchav3`
  - hard-coded sitekey `6LdnVw4qAAAAAFPMxvegAK9JcBflI-0tb8YKMxZU`

### Withdraw flow
- Authenticated helper-session mapping now confirms the withdraw page lives at `GET /withdraw`.
- Proven form submit target:
  - `POST /withdraw/withdraw`
- Proven important fields on the real form:
  - `csrf_token_name`
  - `method`
  - `amount`
  - `wallet`
  - `captcha=icaptcha`
  - `_iconcaptcha-token`
  - `ic-rq`
  - `ic-wid`
  - `ic-cid`
- Proven currently visible payout methods in the live page snapshot:
  - `4 = Litecoin - FaucetPay`
  - `5 = Bitcoin - FaucetPay`
- Proven live IconCaptcha rule text from the withdraw widget:
  - select the image displayed the least amount of times
- New live solver finding:
  - the canvas strip can be extracted from the helper browser session, split into 5 horizontal cells, grouped by visual similarity, and solved by clicking the least-repeated group
  - repeated live tests reached widget oracle `VERIFICATION COMPLETE.`
- Safe submit probe result after a solved IconCaptcha:
  - deliberately invalid submit returned SweetAlert error `The Wallet field is required.`
  - practical meaning: the submit lane is mapped and the remaining missing production input is only the final payout wallet/method

### Faucet flow
- `/faucet` exists and is protected.
- New live auth proof on 2026-04-16: account `holiskabe@gmail.com / Yuda&4321` reaches authenticated `/dashboard` and `/faucet` through the helper-session lane, so the current login architecture is valid when credentials are accepted.
- Working PHP reference script shows the actual claim sequence:
  1. `GET /dashboard` to detect logged-in state
  2. if needed, `GET /login` -> `POST /auth/login`
  3. `GET /faucet`
  4. if `var wait = <n>` exists, sleep and retry
  5. parse hidden `csrf_token_name`
  6. parse anti-bot image order challenge from faucet HTML
  7. obtain `antibotlinks` solve from external solver
  8. obtain reCAPTCHA v3 token for the sitekey above
  9. `POST /faucet/verify` with:
     - `captcha=recaptchav3`
     - `recaptchav3=<token>`
     - `antibotlinks=<ordered ids>`
     - `csrf_token_name=<token>`
  10. success oracle in returned HTML: `Swal.fire('Good job!', ...)`
- This means the active claim endpoint is very likely `/faucet/verify`, not a normal POST back to `/faucet`.
- New live faucet-page findings from the authenticated `holiskabe` session:
  - page title is `Faucet | ClaimCoin - ClaimCoin Faucet`
  - anti-bot challenge is present with 3 option images
  - hidden input `csrf_token_name` is present
  - hidden input `antibotlinks` exists and starts empty
  - hidden input `recaptchav3` is already prefilled on the page by the live browser session, so an external rv3 service is not always required when the claim runs inside an active browser context
- New live submit finding from the same account:
  - the earlier `opened multiple forms and submit them one by one without reloading` response was traced to a local parser bug, not an unexplained site rule. The live faucet CSRF field is rendered as `name="csrf_token_name" id="token" value="..."`, while the old parser only matched `name` immediately followed by `value`, so helper submits were accidentally sending an empty CSRF field.
  - after fixing faucet hidden-input extraction and submitting the already-open live faucet form from the same helper browser context, the full claim lane succeeded live.
  - current verified success shape on the working account:
    - authenticated helper session reaches `/faucet`
    - page-provided hidden `recaptchav3` token is reused
    - anti-bot challenge is solved locally
    - submit target stays `/faucet/verify`
    - success oracle is now proven live, with sample returned texts including `Good job!, 31 tokens has been added to your balance success` and `12 CCP has been added to your balance`
    - observed returned cooldowns are around `5` to `7` minutes
  - later stabilization pass showed solver-shaped flakiness can still happen on some challenges, producing `Invalid Anti-Bot Links` or `Invalid Captcha`. The current runner mitigates this by preferring direct anti-bot solver-core execution and retrying helper claim attempts with a fresh faucet page up to three times before failing.

## Current engineering implication
- Correct near-term lane is now:
  1. stay HTTP-first
  2. mimic the working PHP flow exactly
  3. treat browser bootstrap only as a fallback if the refined HTTP client still hits 403
  4. use a Cloudflare clearance helper such as FlareSolverr for the current front-door blocker before giving up on the HTTP lane
  5. keep the login submit inside the cleared helper session whenever clearance proves session-bound, instead of assuming cookie transplant is enough
  6. for faucet claims, submit the real already-open helper page form instead of a detached synthetic helper form
  7. reuse the page-provided hidden `recaptchav3` token when it already exists in the active helper session
  8. fall back to direct anti-bot solver-core execution if the local HTTP wrapper times out on real ClaimCoin images
  9. for withdraw, keep the solve and submit inside the same helper session because the IconCaptcha state is session-bound too
  10. refactor the PHP logic into a structured multi-account, proxy-capable runner around those verified boundaries

### Shortlinks flow
- Authenticated dashboard mapping now confirms the shortlinks wall lives at `GET /links`.
- Current visible card shape on the working account is:
  - provider name
  - reward text such as `Earn 120 CCP and 10 energy.`
  - quota badge such as `Claim 1/1`
  - action link `GET /links/go/<id>`
- Live confirmed examples from one authenticated snapshot:
  - `ShrinkEarn` -> `/links/go/6`
  - `Shrinkme` -> `/links/go/85`
  - `Shortano` -> `/links/go/72`
  - `Shortino` -> `/links/go/73`
  - `EarNow` -> `/links/go/83`
- Live end-to-end proof for `Shrinkme`:
  1. authenticated ClaimCoin `/links` exposes card `Shrinkme Earn 120 CCP and 10 energy. Claim 1/1`
  2. `GET /links/go/85` redirects out to `https://shrinkme.click/G5zGhyl`
  3. existing `projects/shortlink-bypass-bot` engine resolves that alias to ClaimCoin callback `https://claimcoin.in/links/back/kEQsBGWR1Pl9M2aH0dSu`
  4. opening that callback inside the authenticated ClaimCoin session returns to `/links`
  5. success oracle on the returned page is `Good job! 120 CCP has been added to your balance`
  6. the `Shrinkme` quota drops to `Claim 0/1`, and the card disappears from the refreshed list
- Durable meaning:
  - the ClaimCoin shortlinks reward boundary is `GET /links/back/<token>`
  - the important success oracle is on the returned ClaimCoin `/links` page, not on the external shortlink host
  - for at least this family, the external part can be bypassed into a final ClaimCoin callback URL, then the real account mutation is verified only after that callback is opened in the authenticated ClaimCoin session

## Solver strategy overlay
- Boskuu's current preferred solver map is tracked in `docs/SOLVER_STRATEGY.md`.
- Practical interpretation for ClaimCoin right now:
  - anti-bot image lane should move toward `antibot-image-solver`
  - IconCaptcha should be prepared as a reusable module, but it is not the first blocker for live faucet claims
  - SmartCaptcha stays secondary until live evidence proves login actually needs it
  - Cloudflare should branch into FlareSolverr for generic challenges or Turnstile solver if the live challenge shape later proves to be Turnstile
  - reCAPTCHA v3 should keep the current working hook but be hardened with Boskuu's rv3 references if the token lane degrades
  - every live anti-bot ClaimCoin attempt should now be treated as labeling data for the solver project too, because the runner persists full captures under `state/antibot-captures/` and summary verdicts in SQLite for `solver-stats`
