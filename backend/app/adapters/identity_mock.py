"""Mock real-name (实名) verification adapter.

Performs only shape validation of a Chinese resident ID number and returns a
masked form. Replace with a real KYC / 公安实名核验 provider later.
"""
from __future__ import annotations

import re

from .base import IdentityAdapter, IdentityResult

_ID_RE = re.compile(r"^\d{17}[\dXx]$")


def mask_id(id_card: str) -> str:
    if len(id_card) < 8:
        return "****"
    return f"{id_card[:4]}**********{id_card[-4:]}"


class MockIdentityAdapter(IdentityAdapter):
    def verify(self, name: str, id_card: str) -> IdentityResult:
        name = (name or "").strip()
        id_card = (id_card or "").strip()
        if not name:
            return IdentityResult(False, "", "", "name required")
        if not _ID_RE.match(id_card):
            return IdentityResult(False, name, "", "invalid ID card format")
        return IdentityResult(True, name, mask_id(id_card), "verified")
