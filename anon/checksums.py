# -*- coding: utf-8 -*-
"""Контрольные суммы российских идентификаторов.

Алгоритмы совпадают с официальными правилами ФНС / ПФР:
ИНН-10/12, ОГРН-13, ОГРНИП-15, СНИЛС-11.
"""
from __future__ import annotations

import re


def digits_only(value: str) -> str:
    """Оставляет только цифры — для ключей группировки и проверки КС."""
    return re.sub(r"\D", "", value)


def _mod11(digits: str, coef: list[int]) -> int:
    return sum(int(d) * c for d, c in zip(digits, coef)) % 11 % 10


def valid_inn(inn: str) -> bool:
    """ИНН юрлица (10 цифр) или физлица/ИП (12 цифр) с верной контрольной суммой."""
    if not inn.isdigit():
        return False
    if len(inn) == 10:
        return _mod11(inn, [2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(inn[9])
    if len(inn) == 12:
        return (
            _mod11(inn, [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(inn[10])
            and _mod11(inn, [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(inn[11])
        )
    return False


def valid_ogrn(ogrn: str) -> bool:
    """ОГРН (13) или ОГРНИП (15) с верной контрольной суммой."""
    if not ogrn.isdigit():
        return False
    if len(ogrn) == 13:
        return int(ogrn[:12]) % 11 % 10 == int(ogrn[12])
    if len(ogrn) == 15:
        return int(ogrn[:14]) % 13 % 10 == int(ogrn[14])
    return False


def valid_snils(snils: str) -> bool:
    """СНИЛС XXX-XXX-XXX XX: контрольное число по правилам ПФР."""
    digits = digits_only(snils)
    if len(digits) != 11:
        return False
    num, check = digits[:9], int(digits[9:])
    total = sum(int(n) * (9 - i) for i, n in enumerate(num))
    total = total % 101
    if total == 100:
        total = 0
    return total == check
