# -*- coding: utf-8 -*-
"""Регулярные выражения для структурированных реквизитов с проверкой контрольных сумм."""
from __future__ import annotations

import re
from datetime import date as _date

from .entities import Entity


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _mod11(digits: str, coef: list[int]) -> int:
    return sum(int(d) * c for d, c in zip(digits, coef)) % 11 % 10


def valid_inn(inn: str) -> bool:
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
    if not ogrn.isdigit():
        return False
    if len(ogrn) == 13:
        return int(ogrn[:12]) % 11 % 10 == int(ogrn[12])
    if len(ogrn) == 15:  # ОГРНИП
        return int(ogrn[:14]) % 13 % 10 == int(ogrn[14])
    return False


def valid_snils(snils: str) -> bool:
    d = _digits(snils)
    if len(d) != 11:
        return False
    num, check = d[:9], int(d[9:])
    s = sum(int(n) * (9 - i) for i, n in enumerate(num))
    s = s % 101
    if s == 100:
        s = 0
    return s == check


RX_INN = re.compile(r"(?<!\d)(\d{12}|\d{10})(?!\d)")
RX_OGRN = re.compile(r"(?<!\d)(\d{15}|\d{13})(?!\d)")
RX_SNILS = re.compile(r"(?<!\d)\d{3}[- ]\d{3}[- ]\d{3}[- ]?\d{2}(?!\d)")
RX_ACCOUNT = re.compile(r"(?<!\d)[34]0\d{18}(?!\d)")
RX_BIK = re.compile(r"(?<!\d)04\d{7}(?!\d)")
RX_KPP = re.compile(r"(?<!\d)\d{4}[0-9A-Z]{2}\d{3}(?!\d)")
RX_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RX_PHONE = re.compile(
    r"(?<![\d\w])(?:\+7|8)[\s\-()]{0,3}\d{3}[\s\-()]{0,3}\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)"
)
# паспорт: «45 04 123456», «4504 № 123456» — только рядом со словом-контекстом
RX_PASSPORT = re.compile(r"(?<!\d)(\d{2}\s?\d{2})\s?(?:№|N|n)?\s?(\d{6})(?!\d)")
PASSPORT_CTX = re.compile(r"(паспорт|серия|серии|удостоверение личности)", re.IGNORECASE)
KPP_CTX = re.compile(r"КПП", re.IGNORECASE)
BIK_CTX = re.compile(r"БИК", re.IGNORECASE)
INN_CTX = re.compile(r"ИНН", re.IGNORECASE)

# адрес: «г. Москва, ул. Ленина, д. 5, кв. 12» и вариации; индекс опционален
RX_ADDR = re.compile(
    r"(?:\d{6},\s*)?"
    r"(?:(?:г|гор|город|с|село|пос|п|пгт|д|дер|деревня)\.?\s+[А-ЯЁ][\w\-]+,?\s+)?"
    r"(?:ул|улица|пр-т|пр|проспект|пер|переулок|б-р|бульвар|ш|шоссе|наб|набережная|пл|площадь|проезд|тупик|мкр|микрорайон|квартал|линия)"
    r"\.?\s+[«»\"А-ЯЁа-яё0-9][\w\s\-«»\".]{0,40}?,?\s+"
    r"(?:д|дом|вл|владение|стр|строение|корп|корпус)\.?\s*\d+[а-яА-Я]?"
    r"(?:\s*[,/]?\s*(?:корпус|корп|строение|стр|литера|лит|к)(?=[.\s]*[\dА-ЯA-Z])\.?\s*[\w\d]+)?"
    r"(?:\s*,?\s*(?:кв|квартира|оф|офис|пом|помещение|комн|комната)\.?\s*\d+[а-яА-Я]?)?",
    re.UNICODE,
)

# судебные дела не обезличиваем; зона нужна, чтобы номер не приняли за телефон/счёт
RX_CASE = re.compile(r"(?:№\s*)?[АA]\d{1,3}-\d{1,7}/\d{2,4}(?:[-\w/]*)?")

MONTH_NUM = {
    "января": 1, "январь": 1,
    "февраля": 2, "февраль": 2,
    "марта": 3, "март": 3,
    "апреля": 4, "апрель": 4,
    "мая": 5, "май": 5,
    "июня": 6, "июнь": 6,
    "июля": 7, "июль": 7,
    "августа": 8, "август": 8,
    "сентября": 9, "сентябрь": 9,
    "октября": 10, "октябрь": 10,
    "ноября": 11, "ноябрь": 11,
    "декабря": 12, "декабрь": 12,
}
_MONTH_ALT = "|".join(sorted(MONTH_NUM, key=len, reverse=True))
_YEAR_SFX = r"(?:\s*(?:г\.|года|г\b))?"

RX_DATE_NUM = re.compile(
    rf"(?<!\d)(0?[1-9]|[12]\d|3[01])[./\-](0?[1-9]|1[0-2])[./\-]"
    rf"((?:19|20)\d{{2}}|\d{{2}})(?!\d){_YEAR_SFX}",
    re.IGNORECASE,
)
RX_DATE_TEXT = re.compile(
    rf'(?:[«»"„“]\s*)?(0?[1-9]|[12]\d|3[01])(?:\s*[«»"„“])?\s+'
    rf"({_MONTH_ALT})\b\s+((?:19|20)\d{{2}}){_YEAR_SFX}",
    re.IGNORECASE,
)
RX_DATE_TEXT_NOYEAR = re.compile(
    rf'(?:[«»"„“]\s*)?(0?[1-9]|[12]\d|3[01])(?:\s*[«»"„“])?\s+'
    rf"({_MONTH_ALT})\b(?!\s+(?:19|20)\d{{2}})",
    re.IGNORECASE,
)
RX_DATE_ISO = re.compile(
    r"(?<!\d)((?:19|20)\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?!\d)"
)

# (regex, extractor) — extractor возвращает ключ нормализации или None
_DATE_SPECS = (
    (RX_DATE_NUM, lambda m: _date_key(m.group(1), m.group(2), m.group(3))),
    (RX_DATE_TEXT, lambda m: _date_key(m.group(1), m.group(2), m.group(3))),
    (RX_DATE_TEXT_NOYEAR, lambda m: _date_key(m.group(1), m.group(2))),
    (RX_DATE_ISO, lambda m: _date_key(m.group(3), m.group(2), m.group(1))),
)


def _date_key(day: str, month: int | str, year: str | None = None) -> str | None:
    try:
        d = int(day)
        m = MONTH_NUM[month.lower()] if isinstance(month, str) and not month.isdigit() else int(month)
        if year is None:
            _date(2000, m, d)
            return f"--{m:02d}-{d:02d}"
        y = int(year)
        if y < 100:
            y = 2000 + y if y < 40 else 1900 + y
        _date(y, m, d)
        return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, KeyError):
        return None


def _ctx_before(text: str, start: int, rx: re.Pattern, window: int = 40) -> bool:
    return bool(rx.search(text[max(0, start - window):start]))


def detect_structured(text: str) -> list[Entity]:
    """Все регулярные детекторы. Возвращает список без разрешения пересечений."""
    out: list[Entity] = []
    case_zones = [(m.start(), m.end()) for m in RX_CASE.finditer(text)]

    def in_case(a: int, b: int) -> bool:
        return any(a < z2 and z1 < b for z1, z2 in case_zones)

    def add(etype: str, m_start: int, m_stop: int, value: str, key: str | None = None):
        if in_case(m_start, m_stop):
            return
        out.append(Entity(etype, m_start, m_stop, value, key or _digits(value) or value.lower()))

    for m in RX_SNILS.finditer(text):
        if valid_snils(m.group(0)):
            add("SNILS", m.start(), m.end(), m.group(0))

    for m in RX_ACCOUNT.finditer(text):
        add("ACCOUNT", m.start(), m.end(), m.group(0))

    for m in RX_OGRN.finditer(text):
        if valid_ogrn(m.group(0)):
            add("OGRN", m.start(), m.end(), m.group(0))

    for m in RX_INN.finditer(text):
        # контрольная сумма отсекает ложные 10/12-значные числа;
        # рядом со словом «ИНН» принимаем и номер с опечаткой / тестовый
        if valid_inn(m.group(0)) or _ctx_before(text, m.start(), INN_CTX, 24):
            add("INN", m.start(), m.end(), m.group(0))

    for m in RX_BIK.finditer(text):
        if _ctx_before(text, m.start(), BIK_CTX):
            add("BIK", m.start(), m.end(), m.group(0))

    for m in RX_KPP.finditer(text):
        if _ctx_before(text, m.start(), KPP_CTX, 20):
            add("KPP", m.start(), m.end(), m.group(0))

    for m in RX_PHONE.finditer(text):
        add("PHONE", m.start(), m.end(), m.group(0), key=_digits(m.group(0))[-10:])

    for m in RX_EMAIL.finditer(text):
        add("EMAIL", m.start(), m.end(), m.group(0), key=m.group(0).lower())

    for m in RX_PASSPORT.finditer(text):
        if _ctx_before(text, m.start(), PASSPORT_CTX, 60):
            add("PASSPORT", m.start(), m.end(), m.group(0))

    for m in RX_ADDR.finditer(text):
        add("ADDR", m.start(), m.end(), m.group(0).strip().rstrip(","),
            key=re.sub(r"[\s.,]+", "", m.group(0)).lower())

    for rx, key_fn in _DATE_SPECS:
        for m in rx.finditer(text):
            key = key_fn(m)
            if key:
                add("DATE", m.start(), m.end(), m.group(0).rstrip(), key=key)

    return out


# организации по орг-правовой форме с кавычками: ООО «Ромашка», АО "Вектор Плюс"
RX_ORG = re.compile(
    r"\b(ООО|ОАО|ЗАО|ПАО|АО|НКО|АНО|НАО|МКК|МФК|КПК|ФГУП|ГУП|МУП|ТСЖ|ТСН|СНТ|ЖСК|ИП)\s*"
    r"[«\"']([^»\"'\n]{1,80})[»\"']"
)


def detect_orgs_regex(text: str) -> list[Entity]:
    return [
        Entity("ORG", m.start(), m.end(), m.group(0), norm_key=m.group(2).strip().lower())
        for m in RX_ORG.finditer(text)
    ]
