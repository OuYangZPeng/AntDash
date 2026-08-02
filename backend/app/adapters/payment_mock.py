"""Mock payment adapter covering WeChat / Alipay / bank card.

Simulates a payment gateway sandbox: binding returns an opaque token, and
charges / payouts always succeed. Replace with WeChat Pay / Alipay / an
acquiring-bank SDK later.
"""
from __future__ import annotations

import uuid

from .base import PaymentAdapter, PaymentResult

SUPPORTED_KINDS = {"wechat", "alipay", "bank_card"}


class MockPaymentAdapter(PaymentAdapter):
    def bind_method(self, kind: str, credential: str) -> PaymentResult:
        if kind not in SUPPORTED_KINDS:
            return PaymentResult(False, "", kind, 0, f"unsupported payment kind: {kind}")
        token = f"tok_{kind}_{uuid.uuid4().hex[:16]}"
        return PaymentResult(True, token, kind, 0, "bound")

    def charge(self, token: str, amount_cents: int, memo: str = "") -> PaymentResult:
        if amount_cents <= 0:
            return PaymentResult(False, "", "", amount_cents, "amount must be positive")
        return PaymentResult(True, f"chg_{uuid.uuid4().hex[:16]}", "", amount_cents, memo or "charged")

    def payout(self, token: str, amount_cents: int, memo: str = "") -> PaymentResult:
        if amount_cents <= 0:
            return PaymentResult(False, "", "", amount_cents, "amount must be positive")
        return PaymentResult(True, f"pay_{uuid.uuid4().hex[:16]}", "", amount_cents, memo or "paid out")
