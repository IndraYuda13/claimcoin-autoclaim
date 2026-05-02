from __future__ import annotations

import unittest

from claimcoin_autoclaim.config import AccountConfig, AppConfig, RuntimeConfig, WithdrawSettings
from claimcoin_autoclaim.models import WithdrawMethod, WithdrawState
from claimcoin_autoclaim.services.account_runner import AccountRunner


WITHDRAW_HTML = """
<form action="https://claimcoin.in/withdraw/withdraw" method="POST">
  <input type="hidden" name="csrf_token_name" value="abc123">
  <input type="hidden" name="_iconcaptcha-token" value="tok123">
  <div><h4><i class="icon-wallet"></i> Litecoin - FaucetPay </h4><input type="radio" name="method" value="4"></div>
  <small id="minimumWithdrawal">Minimum withdrawal is 1000 tokens</small>
  <input type="number" name="amount" value="660">
  <input type="text" name="wallet" value="">
  <div class="iconcaptcha-widget iconcaptcha-theme-light"></div>
</form>
"""


class _StateStore:
    def __init__(self) -> None:
        self.saved = []

    def save_account_state(self, account, cookies, raw):
        self.saved.append((account, cookies, raw))


class _Response:
    def __init__(self, *, text: str, url: str = "https://claimcoin.in/withdraw", status_code: int = 200, headers=None) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        return None


class _Http:
    def __init__(self) -> None:
        self.runtime = RuntimeConfig(base_url="https://claimcoin.in")
        self._session = type("Session", (), {"headers": {"User-Agent": "UA"}})()

    def get(self, path):
        if path == "/login":
            return _Response(
                text='<form action="https://claimcoin.in/auth/login"><input type="hidden" name="csrf_token_name" value="login-csrf"></form>',
                url="https://claimcoin.in/login",
            )
        assert path == "/withdraw"
        return _Response(text=WITHDRAW_HTML)

    def post(self, url, **kwargs):
        return _Response(text="", url="https://claimcoin.in/dashboard", status_code=303, headers={"Location": "https://claimcoin.in/dashboard"})

    def cookies_dict(self):
        return {"ci_session": "abc"}


class AccountRunnerWithdrawPlanningTests(unittest.TestCase):
    def test_plan_withdraw_supports_method_wallet_override(self) -> None:
        account = AccountConfig(
            email="holiskabe@gmail.com",
            password="secret",
            withdraw=WithdrawSettings(
                enabled=True,
                method="4",
                wallet="ltc-wallet",
                fallback_method="5",
                fallback_wallet="btc-wallet",
                threshold_tokens=1000,
            ),
        )
        withdraw_state = WithdrawState(
            ready=True,
            amount_tokens=6502.0,
            minimum_tokens=1000.0,
            methods=[
                WithdrawMethod(value="4", label="Litecoin - FaucetPay"),
                WithdrawMethod(value="5", label="Bitcoin - FaucetPay"),
            ],
        )

        primary = AccountRunner._plan_withdraw(account, withdraw_state)
        fallback = AccountRunner._plan_withdraw(
            account,
            withdraw_state,
            method_override=account.withdraw.fallback_method,
            wallet_override=account.withdraw.fallback_wallet,
        )

        self.assertEqual(primary["method"], "4")
        self.assertEqual(primary["wallet_hint"], "ltc-wallet")
        self.assertEqual(fallback["method"], "5")
        self.assertEqual(fallback["method_label"], "Bitcoin - FaucetPay")
        self.assertEqual(fallback["wallet_hint"], "btc-wallet")
        self.assertEqual(fallback["amount_value"], "6502")

    def test_should_retry_withdraw_fallback_only_for_insufficient_funds(self) -> None:
        self.assertTrue(
            AccountRunner._should_retry_withdraw_fallback(
                "The faucet does not have sufficient funds for this transaction."
            )
        )
        self.assertFalse(AccountRunner._should_retry_withdraw_fallback("The Wallet field is required."))

    def test_http_withdraw_skips_below_threshold_without_browser_helper(self) -> None:
        account = AccountConfig(
            email="holiskabe@gmail.com",
            password="secret",
            withdraw=WithdrawSettings(enabled=True, method="4", wallet="ltc-wallet", threshold_tokens=1000),
        )
        store = _StateStore()
        runner = AccountRunner(AppConfig(runtime=RuntimeConfig(base_url="https://claimcoin.in")), store)  # type: ignore[arg-type]

        result = runner._withdraw_once_with_http_client(account, _Http())  # type: ignore[arg-type]

        self.assertTrue(result.ok)
        self.assertIn("withdraw skipped balance=660", result.detail)
        self.assertTrue(result.raw["skip"])
        self.assertEqual(result.raw["balance_tokens"], 660.0)
        self.assertEqual(store.saved[-1][1], {"ci_session": "abc"})


if __name__ == "__main__":
    unittest.main()
