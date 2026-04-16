# ClaimCoin surface map

## Publicly visible feature inventory from homepage
These are visibly advertised on the public homepage and should be treated as likely automation candidates once login is working:

- Faucet
- PTC Ads
- Shortlinks
- Coupon
- Offerwall
- Achievement
- Weekly Contest
- Login Bonus
- Referral Income

## Unauthenticated route probe results
Live probe used a cleared FlareSolverr page fetch against guessed paths.

### Protected or redirected to homepage when unauthenticated
These look like real account features hidden behind auth or other gating because they collapse back to `/` instead of showing a dedicated public page:

- `/dashboard`
- `/faucet`
- `/ptc`
- `/coupon`
- `/offerwall`
- `/achievements`
- `/withdraw`
- `/auto`
- `/referrals`
- `/history`

### 404 on guessed path
These guesses are not yet confirmed route names and should not be treated as real lanes yet:

- `/shortlinks`
- `/shortlink`
- `/offerwalls`
- `/achievement`
- `/contest`
- `/weekly-contest`
- `/bonus`
- `/login-bonus`
- `/autofaucet`
- `/referral`

## Authenticated dashboard route mapping
Live helper-session dashboard mapping with the working account `holiskabe@gmail.com` confirmed these exact in-account menu routes:

- `Manual Faucet` -> `/faucet`
- `PTC` -> `/ptc`
- `Shortlinks` -> `/links`
- `Auto Faucet` -> `/auto`
- `Coupon` -> `/coupon`
- `Achievements` -> `/achievements`
- `History` -> `/history`
- `Referrals` -> `/referrals`
- `Withdraw` -> `/withdraw`
- `Weekly Contest` -> `/leaderboard`

Important correction from this authenticated map:

- weekly contest is exposed through `/leaderboard`, not `/weekly-contest`
- shortlinks is exposed through `/links`, not `/shortlinks`
- the dashboard menu did not expose an `offerwall` entry in this account snapshot, so treat homepage marketing copy as weaker evidence than the authenticated menu

## Authenticated shortlinks wall snapshot
Live authenticated `GET /links` mapping on the working account confirmed these visible cards and entry routes in one real snapshot:

- `ShrinkEarn` -> `/links/go/6` -> reward text `Earn 120 CCP and 10 energy.` -> quota `Claim 1/1`
- `Shrinkme` -> `/links/go/85` -> reward text `Earn 120 CCP and 10 energy.` -> quota `Claim 1/1`
- `Shortano` -> `/links/go/72` -> reward text `Earn 100 CCP and 10 energy.` -> quota `Claim 5/5`
- `Shortino` -> `/links/go/73` -> reward text `Earn 100 CCP and 10 energy.` -> quota `Claim 5/5`
- `EarNow` -> `/links/go/83` -> reward text `Earn 100 CCP and 0 energy.` -> quota `Claim 30/30`

Live proven callback boundary from the `Shrinkme` card:

- `/links/go/85` redirects to external alias `https://shrinkme.click/G5zGhyl`
- that alias can be bypassed to final ClaimCoin callback `https://claimcoin.in/links/back/kEQsBGWR1Pl9M2aH0dSu`
- opening the callback inside the authenticated ClaimCoin session returns to `/links` with success oracle `Good job! 120 CCP has been added to your balance`
- after the reward callback, the `Shrinkme` quota drops from `Claim 1/1` to `Claim 0/1`, and the card disappears from the refreshed list

## Practical meaning
- ClaimCoin almost certainly has more automation surface than faucet alone.
- Exact post-login route names are now partially confirmed from a real authenticated session, so future handler work should anchor on `/links`, `/ptc`, `/auto`, `/coupon`, `/achievements`, `/history`, `/referrals`, `/withdraw`, and `/leaderboard` instead of the earlier guessed slugs.
- The public marketing copy still suggests broader surface, but authenticated menu reality should now outrank homepage wording when choosing the next implementation target.
- The shortlinks wall is now proven as a real automatable lane with a concrete ClaimCoin-side reward boundary at `/links/back/<token>`. Future shortlinks automation should treat external shortener handling and authenticated callback opening as two separate steps, with success verified only after the callback returns to `/links` and mutates the quota/reward state.

## Authenticated withdraw wall snapshot
Live authenticated `GET /withdraw` mapping on the working account confirmed this current shape:

- form action: `/withdraw/withdraw`
- methods visible in one live snapshot:
  - `4` -> `Litecoin - FaucetPay`
  - `5` -> `Bitcoin - FaucetPay`
- important mutable fields:
  - `amount`
  - `wallet`
  - `captcha`
- important hidden/session-bound fields:
  - `csrf_token_name`
  - `_iconcaptcha-token`
  - `ic-rq`
  - `ic-wid`
  - `ic-cid`
- captcha gate:
  - IconCaptcha widget asking for the icon shown the least number of times

Durable meaning:

- withdraw is a real post-login automation lane, not just a static account page
- the captcha part is solvable from the live helper-session canvas itself
- a full production payout still depends on Boskuu's final wallet target and chosen method, not on missing reverse-engineering anymore
