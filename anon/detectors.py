# -*- coding: utf-8 -*-
"""Регулярные детекторы структурированных персональных и идентифицирующих данных.

Сюда входят реквизиты с фиксированным форматом (ИНН, СНИЛС, счета, даты, адреса
и т.д.). ФИО и свободные названия организаций ищет NER (`ner.py`); юридические
формы в кавычках — `detect_orgs_regex`.

Пересечения спанов здесь не разрешаются: несколько детекторов могут отметить
один и тот же фрагмент. Финальный набор выбирает `engine.resolve_overlaps`.

Номера арбитражных дел (`А40-12345/2024`) в зону детекции не попадают — иначе
цифры дела легко принять за телефон или счёт.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
from typing import Callable

from .checksums import digits_only, valid_inn, valid_ogrn, valid_snils
from .entities import Entity

# Реэкспорт для тестов и внешнего API.
__all__ = [
    "detect_structured",
    "detect_orgs_regex",
    "valid_inn",
    "valid_ogrn",
    "valid_snils",
]


# ---------------------------------------------------------------------------
# Контекст: слово-маркер слева от номера (окно в символах)
# ---------------------------------------------------------------------------

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
# «45 04 123456», «4504 № 123456» — только рядом со словом-контекстом
RX_PASSPORT = re.compile(r"(?<!\d)(\d{2}\s?\d{2})\s?(?:№|N|n)?\s?(\d{6})(?!\d)")

PASSPORT_CTX = re.compile(r"(паспорт|серия|серии|удостоверение личности)", re.IGNORECASE)
KPP_CTX = re.compile(r"КПП", re.IGNORECASE)
BIK_CTX = re.compile(r"БИК", re.IGNORECASE)
INN_CTX = re.compile(r"ИНН", re.IGNORECASE)
OGRN_CTX = re.compile(r"ОГРН|ОРГН", re.IGNORECASE)

_SITE_TLD = r"(?:by|ru|com|org|net|info|biz|su|рф|бел|kz|ua)"
RX_SITE = re.compile(
    r"(?:"
    r"(?:https?://|ftp://)[^\s<>\"']+|"
    r"www\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+|"
    r"(?<![@\w./-])[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\."
    + _SITE_TLD
    + r"(?:/[^\s<>\"']*)?"
    r")",
    re.IGNORECASE,
)
_SITE_TRAIL = ".,;:!?)]»\"'"

# Адрес: «г. Москва, ул. Ленина, д. 5», «Невский пр-т, д. 28», «проспект Независимости, 32А-1»
_STREET_TYPE = (
    r"(?:"
    r"улица|ул\.?|"
    r"проспект|просп\.?|пр\.?-?т|пр\.?|"
    r"переулок|пер\.?|"
    r"бульвар|б-р|"
    r"шоссе|ш\.?|"
    r"набережная|наб\.?|"
    r"площадь|пл\.?|"
    r"микрорайон|мкр\.?|"
    r"проезд|тупик|квартал|линия"
    r")"
)
_STREET_NAME = r"[«»\"А-ЯЁа-яё0-9][\w\s\-«»\".]{0,40}?"
_STREET_NAME_WORD = r"[А-ЯЁ][А-ЯЁа-яё\-]+"
_HOUSE_NUM = r"\d{1,4}[А-Яа-яA-Za-z]?(?:[/-]\d{1,3}[А-Яа-яA-Za-z]?)?"
_NOT_DATE_OR_MONEY = (
    r"(?![./]\d)"
    r"(?!\s*(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|"
    r"сентябр|октябр|ноябр|декабр|руб|тыс|млн))"
)
_HOUSE = (
    r"(?:"
    r"(?:д|дом|вл|владение|стр|строение|корп|корпус)\.?\s*" + _HOUSE_NUM
    + r"|"
    + _HOUSE_NUM + _NOT_DATE_OR_MONEY
    + r")"
    r"(?:\s*[,/]?\s*(?:корпус|корп|строение|стр|литера|лит|к)(?=[.\s]*[\dА-ЯA-Z])\.?\s*[\w\d]+)?"
    r"(?:\s*,?\s*(?:кв|квартира|оф|офис|пом|помещение|комн|комната)\.?\s*\d+[а-яА-Я]?)?"
)
_CITY = r"(?:(?:г|гор|город|с|село|пос|п|пгт|д|дер|деревня)\.?\s+[А-ЯЁ][а-яё]+(?:-[А-ЯЁа-яё]+)*,?\s+)?"
_INDEX = r"(?:\d{6},?\s+)?"
RX_ADDR = re.compile(
    rf"(?:"
    rf"{_INDEX}{_CITY}{_STREET_TYPE}\.?\s+{_STREET_NAME},?\s+{_HOUSE}|"
    rf"{_INDEX}{_CITY}{_STREET_NAME_WORD}(?:\s+{_STREET_NAME_WORD}){{0,2}}\s+"
    rf"{_STREET_TYPE}\.?,?\s+{_HOUSE}"
    rf")",
    re.UNICODE,
)

# Короткие формы без улицы: «г Москва», «гор. Москвы», «городе Москве».
# Юр. форму и «…банк» не захватываем: иначе «г. Жлобине ОАО «БПС-Сбербанк»» съест организацию.
_ORG_FORMS = (
    r"ООО|ОАО|ЗАО|ПАО|НАО|НКО|АНО|МКК|МФК|КПК|ФГУП|ГУП|МУП|ТСЖ|ТСН|СНТ|ЖСК|ИП|АО"
)
# Город: «Жлобине», «Ростове-на-Дону». Не берём заглавный хвост «ОАО» (склейка PDF).
_CITY_WORD = (
    rf"(?!(?:{_ORG_FORMS})\b)"
    r"(?![А-ЯЁа-яё\-]*банк\b)"
    r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁа-яё]+)*"
)
_CITY_PREFIX = r"(?:городе|города|город|гор|г)"
_CITY_ITEM = rf"{_CITY_PREFIX}\.?\s*{_CITY_WORD}"
RX_CITY_ADDR = re.compile(
    rf"\b{_CITY_ITEM}(?:\s+{_CITY_WORD}){{0,2}}\b",
    re.UNICODE,
)
# Список городов в одной строке: «г. Рогачеве, г. Жлобине»
RX_CITY_LIST = re.compile(
    rf"\b{_CITY_ITEM}(?:\s*,\s*{_CITY_ITEM})+\b",
    re.UNICODE,
)

RX_POSTAL = re.compile(r"(?<!\d)\d{6}(?!\d)")
POSTAL_CTX = re.compile(r"адрес|индекс|почтово", re.IGNORECASE)
_NOT_MONEY_AFTER = re.compile(r"^\s*(?:руб|тыс|млн|коп|%)", re.IGNORECASE)

# Судебные дела не обезличиваем; зона нужна, чтобы номер не приняли за телефон/счёт.
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

RX_ORG = re.compile(
    rf"(?<![А-ЯЁA-Z])({_ORG_FORMS})\s*[«\"'“„”]([^»\"'“”„\n]{{1,80}})[»\"'“”]"
)
RX_ORG_BARE = re.compile(
    rf"(?<![А-ЯЁA-Z])({_ORG_FORMS})\s+"
    r"(?!ИНН\b|ОГРН\b|КПП\b|БИК\b)"
    r"([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z0-9]*(?:[\-–—−‑][А-ЯЁа-яёA-Za-z0-9]+)*)"
)
RX_ORG_BANK = re.compile(
    r"[«\"'“„]?(?:БПС[\-–—−‑])?Сбербанк\w*[»\"'”]?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PatternSpec:
    """Простой детектор: regex + опционально КС и/или слово-контекст слева."""

    etype: str
    regex: re.Pattern[str]
    validator: Callable[[str], bool] | None = None
    context: re.Pattern[str] | None = None
    context_window: int = 40
    key_fn: Callable[[str], str] | None = None


# Порядок важен только для SITE (он смотрит уже найденные EMAIL).
_PATTERN_SPECS: tuple[PatternSpec, ...] = (
    PatternSpec("SNILS", RX_SNILS, validator=valid_snils),
    PatternSpec("ACCOUNT", RX_ACCOUNT),
    PatternSpec("OGRN", RX_OGRN, validator=valid_ogrn, context=OGRN_CTX, context_window=24),
    PatternSpec("INN", RX_INN, validator=valid_inn, context=INN_CTX, context_window=24),
    PatternSpec("BIK", RX_BIK, context=BIK_CTX),
    PatternSpec("KPP", RX_KPP, context=KPP_CTX, context_window=20),
    PatternSpec("PHONE", RX_PHONE, key_fn=lambda v: digits_only(v)[-10:]),
    PatternSpec("EMAIL", RX_EMAIL, key_fn=lambda v: v.lower()),
    PatternSpec("PASSPORT", RX_PASSPORT, context=PASSPORT_CTX, context_window=60),
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


def _ctx_before(text: str, start: int, rx: re.Pattern[str], window: int = 40) -> bool:
    return bool(rx.search(text[max(0, start - window):start]))


def _accepted(spec: PatternSpec, text: str, value: str, start: int) -> bool:
    has_ctx = spec.context is not None and _ctx_before(
        text, start, spec.context, spec.context_window,
    )
    if spec.validator is None and spec.context is None:
        return True
    if spec.validator is None:
        return has_ctx
    if spec.context is None:
        return spec.validator(value)
    return spec.validator(value) or has_ctx


def _addr_key(value: str) -> str:
    return re.sub(r"[\s.,]+", "", value).lower()


def _trim_site(value: str) -> str:
    while value and value[-1] in _SITE_TRAIL:
        value = value[:-1]
    return value


def _site_key(value: str) -> str:
    key = _trim_site(value).lower()
    key = re.sub(r"^https?://", "", key)
    key = re.sub(r"^www\.", "", key)
    return key.rstrip("/")


def detect_structured(text: str) -> list[Entity]:
    """Все регулярные детекторы. Возвращает список без разрешения пересечений."""
    out: list[Entity] = []
    case_zones = [(m.start(), m.end()) for m in RX_CASE.finditer(text)]

    def in_case(start: int, stop: int) -> bool:
        return any(start < z2 and z1 < stop for z1, z2 in case_zones)

    def add(etype: str, start: int, stop: int, value: str, key: str | None = None) -> None:
        if in_case(start, stop):
            return
        out.append(Entity(
            etype, start, stop, value,
            key or digits_only(value) or value.lower(),
        ))

    for spec in _PATTERN_SPECS:
        for match in spec.regex.finditer(text):
            value = match.group(0)
            if not _accepted(spec, text, value, match.start()):
                continue
            key = spec.key_fn(value) if spec.key_fn else None
            add(spec.etype, match.start(), match.end(), value, key)

    _detect_sites(text, add, out)
    _detect_city_addr(text, add)
    _detect_street_addr(text, add)
    _detect_postal(text, add)
    _detect_dates(text, add)
    return out


def _detect_sites(text: str, add, existing: list[Entity]) -> None:
    """URL, www.* и домены с белым списком TLD. Email не трогаем."""
    for match in RX_SITE.finditer(text):
        value = _trim_site(match.group(0))
        if len(value) < 4:
            continue
        start = match.start()
        stop = start + len(value)
        if any(e.type == "EMAIL" and e.start < stop and start < e.stop for e in existing):
            continue
        add("SITE", start, stop, value, _site_key(value))


def _detect_city_addr(text: str, add) -> None:
    """«г. Москва», «г. Рогачеве, г. Жлобине» — без юр. формы и «банк»."""
    for match in RX_CITY_LIST.finditer(text):
        value = match.group(0).strip().rstrip(",")
        add("ADDR", match.start(), match.end(), value, _addr_key(value))
    for match in RX_CITY_ADDR.finditer(text):
        value = match.group(0).strip().rstrip(",")
        add("ADDR", match.start(), match.end(), value, _addr_key(value))


def _detect_street_addr(text: str, add) -> None:
    """Улица/проспект + дом, опционально индекс, город, корпус, квартира."""
    for match in RX_ADDR.finditer(text):
        value = match.group(0).strip().rstrip(",")
        add("ADDR", match.start(), match.end(), value, _addr_key(value))


def _detect_postal(text: str, add) -> None:
    """Шестизначный индекс рядом со словами «адрес» / «индекс» / «почтово»."""
    for match in RX_POSTAL.finditer(text):
        if _NOT_MONEY_AFTER.search(text[match.end():match.end() + 12]):
            continue
        if _ctx_before(text, match.start(), POSTAL_CTX, 80):
            add("ADDR", match.start(), match.end(), match.group(0), match.group(0))


def _detect_dates(text: str, add) -> None:
    """Календарные даты; невалидные (31.02) отбрасываются. Один ключ — один тег."""
    for regex, key_fn in _DATE_SPECS:
        for match in regex.finditer(text):
            key = key_fn(match)
            if key:
                add("DATE", match.start(), match.end(), match.group(0).rstrip(), key)


def detect_orgs_regex(text: str) -> list[Entity]:
    """Организации: форма + кавычки, форма + имя без кавычек, варианты «Сбербанк»."""
    out: list[Entity] = []
    seen: set[tuple[int, int]] = set()

    def add_org(start: int, stop: int, value: str, key: str) -> None:
        span = (start, stop)
        if span in seen:
            return
        seen.add(span)
        out.append(Entity("ORG", start, stop, value, norm_key=key))

    for match in RX_ORG.finditer(text):
        add_org(match.start(), match.end(), match.group(0), match.group(2).strip().lower())
    for match in RX_ORG_BARE.finditer(text):
        add_org(match.start(), match.end(), match.group(0), match.group(2).strip().lower())
    for match in RX_ORG_BANK.finditer(text):
        name = match.group(0).strip("«»\"'“”„")
        add_org(match.start(), match.end(), match.group(0), name.lower())
    return out
