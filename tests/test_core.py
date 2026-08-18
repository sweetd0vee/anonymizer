# -*- coding: utf-8 -*-
"""End-to-end тест ядра: детекция, замена, docx, восстановление."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from anon import engine, readers, writers
from anon.detectors import detect_structured, valid_inn, valid_ogrn, valid_snils
from anon.entities import Entity, TagRegistry

SAMPLE = """АРБИТРАЖНЫЙ СУД ГОРОДА МОСКВЫ
Дело № А40-12345/2024

ИСКОВОЕ ЗАЯВЛЕНИЕ

Истец: Иванов Иван Петрович, паспорт серия 45 04 123456,
СНИЛС 112-233-445 95, проживающий по адресу: г. Москва, ул. Ленина, д. 5, кв. 12,
тел. +7 (916) 123-45-67, email: ivanov.ip@example.com.

Ответчик: ООО «Ромашка», ИНН 7707083893, ОГРН 1027700132195,
КПП 773601001, р/с 40702810900000005555, БИК 044525225.

Иванов И.П. заключил с ООО «Ромашка» договор поставки от 15 марта 2024 г.
Ответчик обязательства не исполнил до 15.03.2024, в связи с чем Иванову Ивану Петровичу
причинены убытки. Представитель истца — Сидорова Анна Викторовна (ИНН 500100732259).

Прошу взыскать с ООО «Ромашка» в пользу Иванова И.П. 1 000 000 рублей.
"""


def banner(s):
    print("\n" + "=" * 20, s, "=" * 20)


def test_helpers():
    assert valid_inn("7707083893") and valid_inn("500100732259")
    assert valid_ogrn("1027700132195")
    assert valid_snils("112-233-445 95")

    kpp = detect_structured("Организация, КПП 7701AB001, далее по тексту.")
    assert any(e.type == "KPP" and "7701AB001" in e.text for e in kpp)

    dates = detect_structured(
        "Договор от 15 марта 2024 г., срок до 15.03.2024 и 2024-03-15."
    )
    date_keys = {e.norm_key for e in dates if e.type == "DATE"}
    assert date_keys == {"2024-03-15"}
    assert all(e.tag == "" for e in dates)

    a = [Entity("FIO", 0, 21, "Иванов Иван Петрович", "иванов|и")]
    b = [Entity("FIO", 0, 6, "Иванов", "иванов")]
    registry = TagRegistry()
    engine.apply_package_tags([a, b], registry)
    assert a[0].tag == b[0].tag == "[ФИО1]"

    mapping = {
        "tags": {
            "[ФИО1]": {"type": "ФИО", "canonical": r"ref\1value"},
            "[ФИО10]": {"type": "ФИО", "canonical": "Петров"},
        }
    }
    restored, leftover = engine.deanonymize_text("[ФИО1] и [ФИО10]", mapping)
    assert restored == r"ref\1value и Петров"
    assert not leftover
    print("Вспомогательные проверки: ok")


def main():
    test_helpers()

    analyzer = engine.Analyzer()
    entities = analyzer.detect(SAMPLE)
    banner("Найденные сущности")
    for e in entities:
        print(f"  {e.type:9} {e.text!r:55} key={e.norm_key}")

    registry = TagRegistry()
    engine.apply_tags(entities, registry)
    anon_text = engine.anonymize_text(SAMPLE, entities)
    banner("Обезличенный текст")
    print(anon_text)

    # проверки
    assert "А40-12345/2024" in anon_text, "номер дела должен сохраниться"
    assert "АРБИТРАЖНЫЙ СУД" in anon_text.upper(), "суд не обезличиваем"
    for pii in (
        "Иванов",
        "7707083893",
        "1027700132195",
        "112-233-445",
        "40702810900000005555",
        "ivanov.ip@example.com",
        "123-45-67",
        "Сидорова",
        "Ромашка",
        "45 04 123456",
        "500100732259",
        "ул. Ленина",
        "15.03.2024",
        "15 марта 2024",
    ):
        assert pii not in anon_text, f"НЕ ЗАМЕНЕНО: {pii}"

    date_tags = {e.tag for e in entities if e.type == "DATE" and e.norm_key == "2024-03-15"}
    assert len(date_tags) == 1, f"одна дата получила разные теги: {date_tags}"

    # консистентность: Иванов везде один тег
    fio_tags = {e.tag for e in entities if e.type == "FIO" and "иванов" in e.norm_key}
    assert len(fio_tags) == 1, f"Иванов получил разные теги: {fio_tags}"
    print("\nПроверки замены: ok; тег Иванова:", fio_tags)

    # round-trip
    mapping = registry.to_mapping()
    restored, leftover = engine.deanonymize_text(anon_text, mapping)
    assert not leftover, f"остались теги: {leftover}"
    assert "Иванов Иван Петрович" in restored
    assert "ООО «Ромашка»" in restored
    print("Восстановление: ok")

    # docx round-trip с форматированием
    banner("docx")
    import docx

    d = docx.Document()
    p = d.add_paragraph()
    p.add_run("Истец ")
    r = p.add_run("Иванов Иван Петрович")
    r.bold = True
    p.add_run(" предъявил иск к ")
    r2 = p.add_run("ООО «Ромашка»")
    r2.italic = True
    p.add_run(", ИНН 7707083893.")

    table = d.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "СНИЛС"
    table.rows[0].cells[1].text = "112-233-445 95"

    src = os.path.join(os.path.dirname(__file__), "sample.docx")
    d.save(src)

    loaded = readers.load(src)
    ents = analyzer.detect(loaded.text)
    reg2 = TagRegistry()
    engine.apply_tags(ents, reg2)
    out = os.path.join(os.path.dirname(__file__), "sample.anon.docx")
    writers.save_anonymized(loaded, ents, out)

    check = readers.load(out)
    print(check.text)
    assert "Иванов" not in check.text and "Ромашка" not in check.text
    assert "7707083893" not in check.text and "112-233-445" not in check.text
    # форматирование сохранилось: жирный run содержит тег ФИО
    d2 = docx.Document(out)
    bold_runs = [r.text for p2 in d2.paragraphs for r in p2.runs if r.bold]
    assert any("[ФИО" in t for t in bold_runs), f"жирный тег не найден: {bold_runs}"
    print("docx: ok (форматирование сохранено)")

    # адрес, разрезанный переносом абзаца
    split = os.path.join(os.path.dirname(__file__), "sample_split.docx")
    ds = docx.Document()
    ds.add_paragraph("Адрес: г. Москва, ул. Ленина,")
    ds.add_paragraph("д. 5, кв. 12.")
    ds.save(split)
    loaded_s = readers.load(split)
    ents_s = analyzer.detect(loaded_s.text)
    assert any(e.type == "ADDR" for e in ents_s), "адрес на стыке абзацев не найден"
    engine.apply_tags(ents_s, TagRegistry())
    out_s = os.path.join(os.path.dirname(__file__), "sample_split.anon.docx")
    writers.save_anonymized(loaded_s, ents_s, out_s)
    check_s = readers.load(out_s)
    assert "Ленина" not in check_s.text
    print("docx на стыке абзацев: ok")

    banner("xlsx")
    from openpyxl import Workbook
    from openpyxl.comments import Comment

    wb = Workbook()
    ws = wb.active
    ws.title = "Иск"
    ws["A1"] = "Истец Иванов Иван Петрович"
    ws["B1"] = 7707083893
    ws["A2"] = "ООО «Ромашка»"
    ws["B2"] = "email: ivanov.ip@example.com"
    ws["A1"].comment = Comment("Паспорт Сидоровой", "Сидорова Анна")

    src_x = os.path.join(os.path.dirname(__file__), "sample.xlsx")
    wb.save(src_x)

    loaded_x = readers.load(src_x)
    assert "7707083893" in loaded_x.text, "числовой ИНН должен читаться как текст"
    ents_x = analyzer.detect(loaded_x.text)
    engine.apply_tags(ents_x, TagRegistry())
    out_x = os.path.join(os.path.dirname(__file__), "sample.anon.xlsx")
    writers.save_anonymized(loaded_x, ents_x, out_x)
    check_x = readers.load(out_x)
    print(check_x.text)
    for pii in (
        "Иванов",
        "Ромашка",
        "7707083893",
        "ivanov.ip@example.com",
        "Сидорова",
    ):
        assert pii not in check_x.text, f"xlsx НЕ ЗАМЕНЕНО: {pii}"
    print("xlsx: ok")

    banner("pptx")
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(8), Inches(1.2))
    p = box.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = "Истец Иванов Иван Петрович"
    r.font.bold = True
    table = slide.shapes.add_table(1, 2, Inches(0.5), Inches(2), Inches(6), Inches(1)).table
    table.cell(0, 0).text = "Ответчик"
    table.cell(0, 1).text = "ООО «Ромашка», ИНН 7707083893"
    src_p = os.path.join(os.path.dirname(__file__), "sample.pptx")
    prs.save(src_p)

    loaded_p = readers.load(src_p)
    ents_p = analyzer.detect(loaded_p.text)
    engine.apply_tags(ents_p, TagRegistry())
    out_p = os.path.join(os.path.dirname(__file__), "sample.anon.pptx")
    writers.save_anonymized(loaded_p, ents_p, out_p)
    check_p = readers.load(out_p)
    print(check_p.text)
    for pii in ("Иванов", "Ромашка", "7707083893"):
        assert pii not in check_p.text, f"pptx НЕ ЗАМЕНЕНО: {pii}"

    d2p = Presentation(out_p)
    bold_runs = []
    for sl in d2p.slides:
        for sh in sl.shapes:
            if not getattr(sh, "has_text_frame", False):
                continue
            for para in sh.text_frame.paragraphs:
                for run in para.runs:
                    if run.font.bold:
                        bold_runs.append(run.text)
    assert any("[ФИО" in t for t in bold_runs), f"pptx: жирный тег не найден: {bold_runs}"
    print("pptx: ok (форматирование сохранено)")

    print("\nВСЕ ТЕСТЫ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()

