# -*- coding: utf-8 -*-
"""Модель сущностей и реестр тегов."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime


# Типы сущностей: код -> русская метка для тега [МЕТКА1]
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
    "OTHER": "ДАННЫЕ",
}

# Подписи в боковой панели (тег в тексте — из ENTITY_TYPES)
SETTING_TYPES = [
    ("FIO", "ФИО"),
    ("ORG", "Организации"),
    ("ADDR", "Адреса"),
    ("DATE", "Даты"),
    ("INN", "ИНН"),
    ("OGRN", "ОГРН"),
    ("SNILS", "СНИЛС"),
    ("PASSPORT", "Паспорта"),
    ("ACCOUNT", "Счета"),
    ("BIK", "БИК"),
    ("PHONE", "Телефоны"),
    ("EMAIL", "Email"),
]
MANUAL_TYPES = SETTING_TYPES + [("OTHER", "Другое (перс. данные)")]


@dataclass
class Entity:
    """Одно вхождение сущности в тексте документа."""
    type: str            # код из ENTITY_TYPES
    start: int
    stop: int
    text: str
    norm_key: str        # ключ группировки (одинаковый у всех форм одной сущности)
    source: str = "auto"  # auto | manual
    enabled: bool = True
    tag: str = ""        # присвоенный тег вида [ФИО1]
    norm_text: str = ""  # нормализованная форма (именительный падеж), если известна

    def overlaps(self, other: "Entity") -> bool:
        return self.start < other.stop and other.start < self.stop


class TagRegistry:
    """Реестр тегов, общий для всех файлов пакета: (type, norm_key) -> [ФИО1]."""

    def __init__(self):
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
