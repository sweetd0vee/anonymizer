# -*- coding: utf-8 -*-
"""Модель сущностей, типы тегов и реестр соответствий.

Тег строится как `[МЕТКАN]`, где метка — русское имя типа (`ФИО`, `ИНН`, …),
а N — порядковый номер внутри типа на весь пакет файлов. Одинаковые значения
(после нормализации `norm_key`) получают один и тот же тег.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime


# Код типа -> метка в тексте документа: [ФИО1], [ИНН2], …
ENTITY_TYPES = {
    "FIO": "ФИО",
    "ORG": "ОРГ",
    "ADDR": "АДРЕС",
    "DATE": "ДАТА",
    "INN": "ИНН",
    "OGRN": "ОГРН",
    "SNILS": "СНИЛС",
    "PASSPORT": "ПАСПОРТ",
    "ACCOUNT": "СЧЕТ",
    "BIK": "БИК",
    "KPP": "КПП",
    "PHONE": "ТЕЛЕФОН",
    "EMAIL": "EMAIL",
    "SITE": "САЙТ",
    "OTHER": "ДАННЫЕ",
}

# Подписи в боковой панели. Тег в тексте берётся из ENTITY_TYPES.
SETTING_TYPES = [
    ("FIO", "ФИО"),
    ("ORG", "Организации"),
    ("ADDR", "Адреса"),
    ("DATE", "Даты"),
    ("INN", "ИНН"),
    ("OGRN", "ОГРН"),
    ("KPP", "КПП"),
    ("SNILS", "СНИЛС"),
    ("PASSPORT", "Паспорта"),
    ("ACCOUNT", "Счета"),
    ("BIK", "БИК"),
    ("PHONE", "Телефоны"),
    ("EMAIL", "Email"),
    ("SITE", "Сайты"),
]
MANUAL_TYPES = SETTING_TYPES + [("OTHER", "Другое (перс. данные)")]

# При пересечении спанов выигрывает больший приоритет, затем длина.
# Регулярки с контрольной суммой точнее NER, поэтому ИНН/ОГРН/СНИЛС выше ФИО/ОРГ.
OVERLAP_PRIORITY = {
    "SNILS": 10, "ACCOUNT": 10, "OGRN": 10, "INN": 10, "PASSPORT": 9,
    "BIK": 9, "KPP": 9, "PHONE": 8, "EMAIL": 8, "SITE": 8, "DATE": 8,
    "ADDR": 7, "ORG": 7, "FIO": 5, "OTHER": 4,
}


@dataclass
class Entity:
    """Одно вхождение сущности в тексте документа."""

    type: str             # код из ENTITY_TYPES
    start: int
    stop: int
    text: str
    norm_key: str         # ключ группировки (одинаковый у всех форм одной сущности)
    source: str = "auto"  # auto | manual
    enabled: bool = True
    tag: str = ""         # присвоенный тег вида [ФИО1]
    norm_text: str = ""   # нормализованная форма (именительный падеж), если известна

    def overlaps(self, other: "Entity") -> bool:
        return self.start < other.stop and other.start < self.stop


class TagRegistry:
    """Реестр тегов, общий для всех файлов пакета: (type, norm_key) -> [ФИО1]."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], str] = {}
        self._counters: dict[str, int] = {}
        # tag -> {"type": метка, "canonical": исходное значение, "forms": set}
        self.records: dict[str, dict] = {}

    def assign(self, entity: Entity) -> str:
        key = (entity.type, entity.norm_key)
        best = entity.norm_text or entity.text
        tag = self._by_key.get(key)
        if tag is None:
            label = ENTITY_TYPES[entity.type]
            self._counters[label] = self._counters.get(label, 0) + 1
            tag = f"[{label}{self._counters[label]}]"
            self._by_key[key] = tag
            self.records[tag] = {
                "type": label,
                "canonical": best,
                "forms": set(),
            }
        rec = self.records[tag]
        rec["forms"].add(entity.text)
        # канонической считаем самую длинную нормализованную форму
        if len(best) > len(rec["canonical"]):
            rec["canonical"] = best
        entity.tag = tag
        return tag

    def to_mapping(
        self,
        files: list[str] | None = None,
        include: set[str] | None = None,
    ) -> dict:
        records = self.records
        if include is not None:
            records = {tag: rec for tag, rec in records.items() if tag in include}
        return {
            "version": 1,
            "created": datetime.now().isoformat(timespec="seconds"),
            "files": files or [],
            "tags": {
                tag: {
                    "type": rec["type"],
                    "canonical": rec["canonical"],
                    "forms": sorted(rec["forms"]),
                }
                for tag, rec in records.items()
            },
        }


def load_mapping_bytes(data: bytes) -> dict:
    mapping = json.loads(data.decode("utf-8-sig"))
    if "tags" not in mapping:
        raise ValueError("Файл не похож на файл соответствий: нет раздела 'tags'")
    return mapping
