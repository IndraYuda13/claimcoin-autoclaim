from __future__ import annotations

import unittest

from claimcoin_autoclaim.parsers.withdraw import parse_withdraw_response, parse_withdraw_state


WITHDRAW_HTML = """
<form action="https://claimcoin.in/withdraw/withdraw" method="POST">
  <input type="hidden" name="csrf_token_name" value="abc123">
  <input type="hidden" name="_iconcaptcha-token" value="tok123">
  <input type="hidden" name="ic-rq" value="1">
  <input type="hidden" name="ic-wid" value="wid123">
  <input type="hidden" name="ic-cid" value="cid123">
  <div><h4><i class="icon-wallet"></i> Litecoin - FaucetPay </h4><input type="radio" name="method" value="4"></div>
  <div><h4><i class="icon-wallet"></i> Bitcoin - FaucetPay </h4><input type="radio" name="method" value="5"></div>
  <small id="minimumWithdrawal">Minimum withdrawal is 1000 tokens</small>
  <input type="number" name="amount" value="1270">
  <input type="text" name="wallet" value="">
  <div class="iconcaptcha-widget iconcaptcha-theme-light"></div>
</form>
"""


class WithdrawParserTests(unittest.TestCase):
    def test_parse_withdraw_state(self) -> None:
        state = parse_withdraw_state(WITHDRAW_HTML)
        self.assertTrue(state.ready)
        self.assertEqual(state.csrf_token, "abc123")
        self.assertEqual(state.amount_tokens, 1270.0)
        self.assertEqual(state.minimum_tokens, 1000.0)
        self.assertEqual([method.value for method in state.methods], ["4", "5"])

    def test_parse_withdraw_response_error(self) -> None:
        ok, success_text, fail_text = parse_withdraw_response(
            "<script> Swal.fire('Error!', '<p>The Wallet field is required.</p>', 'error')</script>"
        )
        self.assertFalse(ok)
        self.assertIsNone(success_text)
        self.assertEqual(fail_text, "The Wallet field is required.")


if __name__ == "__main__":
    unittest.main()
