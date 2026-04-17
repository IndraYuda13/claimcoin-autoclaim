from __future__ import annotations

import unittest

from claimcoin_autoclaim.config import AccountConfig, WithdrawSettings
from claimcoin_autoclaim.models import WithdrawMethod, WithdrawState
from claimcoin_autoclaim.services.account_runner import AccountRunner


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


if __name__ == "__main__":
    unittest.main()
