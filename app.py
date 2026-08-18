# -*- coding: utf-8 -*-
"""Веб-интерфейс анонимизатора на Streamlit."""
from __future__ import annotations

import html
import json
import os
import zipfile
from dataclasses import dataclass, field
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components

from anon import config, engine, readers, writers
from anon.entities import (
    ENTITY_TYPES,
    MANUAL_TYPES,
    SETTING_TYPES,
    Entity,
    TagRegistry,
    load_mapping_bytes,
)

APP_TITLE = "Анонимизатор документов"

COLORS = {
    "FIO": "#ffd6d6", "ORG": "#d6e4ff", "ADDR": "#d9f2d9", "DATE": "#fde6c8",
    "INN": "#fff2c2", "OGRN": "#fff2c2", "KPP": "#fff2c2", "BIK": "#fff2c2",
    "SNILS": "#ffe0f0", "PASSPORT": "#ffcfa8", "ACCOUNT": "#e2d6ff",
    "PHONE": "#c9f0f0", "EMAIL": "#c9f0f0", "OTHER": "#e0e0e0",
}

MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".json": "application/json",
    ".zip": "application/zip",
}

AVAILABLE_TYPES = {code for code, _ in SETTING_TYPES}


def count_words(text: str) -> int:
    return len(text.split()) if text else 0


@dataclass
class FileState:
    name: str
    raw: bytes
    text: str = ""
    warnings: list = field(default_factory=list)
    entities: list = field(default_factory=list)
    error: str = ""


@st.cache_resource
def get_analyzer() -> engine.Analyzer:
    return engine.Analyzer()


def init_state():
    st.session_state.setdefault("files", [])
    st.session_state.setdefault("editor_rev", 0)
    st.session_state.setdefault("restore_text", "")
    st.session_state.setdefault("restore_name", "")
    st.session_state.setdefault("restore_leftover", [])
    if "registry" not in st.session_state:
        st.session_state.registry = TagRegistry()
    if "enabled_types" not in st.session_state:
        saved = config.load_settings().get("enabled_types")
        types = (set(saved) & AVAILABLE_TYPES) if saved else set(AVAILABLE_TYPES)
        st.session_state.enabled_types = types | {"OTHER"}


def apply_enabled_types():
    types = st.session_state.enabled_types | {"OTHER"}
    for fs in st.session_state.files:
        for e in fs.entities:
            if e.source == "auto":
                e.enabled = e.type in types


def analyze_uploads(uploads) -> tuple[list[FileState], TagRegistry]:
    analyzer = get_analyzer()
    files: list[FileState] = []
    for up in uploads:
        name = os.path.basename(up.name)
        fs = FileState(name=name, raw=up.getvalue())
        try:
            loaded = readers.load_from_bytes(name, fs.raw)
            fs.text = loaded.text
            fs.warnings = loaded.warnings
            fs.entities = [
                e for e in analyzer.detect(loaded.text)
                if e.type in AVAILABLE_TYPES
            ]
        except Exception as exc:
            fs.error = str(exc)
        files.append(fs)
    registry = TagRegistry()
    tag_package = getattr(engine, "apply_package_tags", None)
    if callable(tag_package):
        tag_package([fs.entities for fs in files], registry)
    else:
        for fs in files:
            engine.apply_tags(fs.entities, registry)
    enabled = st.session_state.enabled_types | {"OTHER"}
    for fs in files:
        for e in fs.entities:
            e.enabled = e.type in enabled
    return files, registry


def set_tag_enabled(tag: str, enabled: bool):
    for fs in st.session_state.files:
        for e in fs.entities:
            if e.tag == tag:
                e.enabled = enabled


def add_manual(fragment: str, etype: str) -> tuple[int, str]:
    fragment = fragment.strip()
    if len(fragment) < 2:
        return 0, "empty"
    added = 0
    seen = 0
    registry: TagRegistry = st.session_state.registry
    for fs in st.session_state.files:
        if not fs.text:
            continue
        hits = engine.find_manual_occurrences(fs.text, fragment)
        seen += len(hits)
        for start, stop in hits:
            cand = Entity(etype, start, stop, fragment,
                          norm_key=fragment.lower(), source="manual")
            clash = [x for x in fs.entities if x.overlaps(cand)]
            if any(x.enabled for x in clash):
                continue
            for x in clash:
                fs.entities.remove(x)
            registry.assign(cand)
            fs.entities.append(cand)
            added += 1
        fs.entities.sort(key=lambda x: x.start)
    if added:
        return added, "ok"
    return 0, "not_found" if seen == 0 else "overlap"


def highlight_html(text: str, entities: list[Entity], show_result: bool) -> str:
    if show_result:
        body = html.escape(engine.anonymize_text(text, entities))
        return body.replace("\n", "<br>")
    parts = []
    last = 0
    for e in sorted(entities, key=lambda x: x.start):
        parts.append(html.escape(text[last:e.start]))
        color = COLORS.get(e.type, "#eeeeee") if e.enabled else "#f0f0f0"
        style = f"background:{color};padding:0 3px;border-radius:3px;"
        if not e.enabled:
            style += "text-decoration:line-through;color:#888;"
        title = html.escape(e.tag or ENTITY_TYPES.get(e.type, e.type))
        parts.append(
            f'<mark style="{style}" title="{title}">{html.escape(e.text)}</mark>'
        )
        last = e.stop
    parts.append(html.escape(text[last:]))
    return "".join(parts).replace("\n", "<br>")


_preview_component = components.declare_component(
    "anon_preview",
    path=os.path.join(os.path.dirname(__file__), "frontend", "preview"),
)


def render_preview(body: str, key: str) -> str:
    value = _preview_component(html=body, key=key, default="")
    return (value or "").strip()


def used_tags() -> set[str]:
    return {e.tag for fs in st.session_state.files
            for e in fs.entities if e.enabled and e.tag}


def mapping_json() -> bytes:
    registry: TagRegistry = st.session_state.registry
    mapping = registry.to_mapping(
        [fs.name for fs in st.session_state.files if not fs.error],
        include=used_tags(),
    )
    return json.dumps(mapping, ensure_ascii=False, indent=2).encode("utf-8")


def export_file(fs: FileState) -> tuple[str, bytes]:
    out_name = os.path.basename(writers.anon_output_path(fs.name))
    loaded = readers.load_from_bytes(fs.name, fs.raw)
    return out_name, writers.anonymized_bytes(loaded, fs.entities, out_name)


def export_zip() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fs in st.session_state.files:
            if fs.error:
                continue
            name, data = export_file(fs)
            zf.writestr(name, data)
        zf.writestr("_mapping.json", mapping_json())
    return buf.getvalue()


def mime_for(name: str) -> str:
    return MIME.get(os.path.splitext(name)[1].lower(), "application/octet-stream")


def render_category_types():
    labels = [label for _, label in SETTING_TYPES]
    by_label = {label: code for code, label in SETTING_TYPES}
    by_code = {code: label for code, label in SETTING_TYPES}

    if "replace_types" not in st.session_state:
        st.session_state.replace_types = [
            by_code[code] for code, _ in SETTING_TYPES
            if code in st.session_state.enabled_types
        ]

    with st.expander("Категории для замены"):
        selected = st.multiselect(
            "Категории для замены",
            options=labels,
            key="replace_types",
            label_visibility="collapsed",
        )
    new_types = {"OTHER"} | {by_label[label] for label in selected}

    if new_types != st.session_state.enabled_types:
        st.session_state.enabled_types = new_types
        config.save_settings({"enabled_types": sorted(new_types)})
        apply_enabled_types()
        st.session_state.editor_rev += 1


def render_highlight_legend() -> None:
    """Список категорий подсветки под выбором категорий."""
    legend = "".join(
        f'<span class="sidebar-legend-tag" style="background:{COLORS[c]};">'
        f'{html.escape(l)}</span>'
        for c, l in SETTING_TYPES
    )
    with st.expander("Подсветка"):
        st.markdown(
            f'<div class="sidebar-legend-tags">{legend}</div>',
            unsafe_allow_html=True,
        )


def page_anonymize():
    st.markdown(
        "Загрузите документы, проверьте подсветку и скачайте обезличенные файлы."
    )
    uploads = st.file_uploader(
        "Документы (docx, pdf, txt). Несколько файлов — общая таблица тегов.",
        type=["docx", "pdf", "txt"],
        accept_multiple_files=True,
        key="anon_uploads",
    )
    render_category_types()
    render_highlight_legend()
    btn_col, toggle_col, _ = st.columns((1.1, 1.4, 3))
    with btn_col:
        if st.button("Обработать", type="primary", disabled=not uploads):
            with st.spinner("Анализ… первый запуск занимает около 10 секунд"):
                files, registry = analyze_uploads(uploads)
            st.session_state.files = files
            st.session_state.registry = registry
            st.session_state.editor_rev += 1
            st.session_state.pop("current_file", None)
            st.session_state.pop("shown_file", None)
            st.session_state.pop("_last_preview_sel", None)
            st.session_state.manual_fragment = ""
            st.rerun()
    with toggle_col:
        st.checkbox(
            "Показать результат замены",
            value=False,
            key="show_result",
            disabled=not st.session_state.files,
        )

    files: list[FileState] = st.session_state.files
    if not files:
        st.info("Выберите файл или несколько файлов и нажмите «Обработать».")
        return

    errors = [fs for fs in files if fs.error]
    ok_files = [fs for fs in files if not fs.error]
    total = sum(len(fs.entities) for fs in ok_files)
    total_words = sum(count_words(fs.text) for fs in ok_files)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Файлов", len(ok_files))
    c2.metric("Найдено данных", total)
    c3.metric("С ошибкой", len(errors))
    c4.metric("Слов в тексте", total_words)
    st.dataframe(
        [
            {
                "Файл": fs.name,
                "Слов в тексте": count_words(fs.text) if not fs.error else "—",
            }
            for fs in files
        ],
        hide_index=True,
        width="stretch",
    )
    for fs in errors:
        st.error(f"{fs.name}: {fs.error}")

    if not ok_files:
        return

    names = [fs.name for fs in files]
    current_name = st.selectbox("Файл", names, key="current_file")
    current = next(fs for fs in files if fs.name == current_name)
    for w in current.warnings:
        st.warning(w)

    show_result = st.session_state.show_result
    if st.session_state.get("shown_file") != current_name:
        st.session_state.shown_file = current_name
        st.session_state.editor_rev += 1

    # Превью с подсветкой показываем в основной области.
    if current.error:
        st.error(current.error)
        selected = ""
    else:
        selected = render_preview(
            highlight_html(current.text, current.entities, show_result),
            key=f"preview_{current.name}",
        )
    if selected and selected != st.session_state.get("_last_preview_sel"):
        st.session_state._last_preview_sel = selected
        st.session_state.manual_fragment = selected

    st.caption("Найденные данные — снимите галочку, чтобы не заменять")
    groups: dict[str, list[Entity]] = {}
    for e in current.entities:
        groups.setdefault(e.tag or "?", []).append(e)
    rows = []
    for tag, ents in groups.items():
        e0 = ents[0]
        rows.append({
            "Заменить": e0.enabled,
            "Тег": tag,
            "Тип": ENTITY_TYPES.get(e0.type, e0.type),
            "Значение": e0.text[:80],
            "×": len(ents),
        })
    if not rows:
        st.info("Ничего не найдено. Добавьте фрагмент вручную, если нужно.")
    else:
        edited = st.data_editor(
            rows,
            key=f"ents_{st.session_state.editor_rev}",
            hide_index=True,
            width="stretch",
            disabled=["Тег", "Тип", "Значение", "×"],
            column_config={
                "Заменить": st.column_config.CheckboxColumn(width="small"),
                "×": st.column_config.NumberColumn(width="small"),
            },
        )
        records = edited.to_dict("records") if hasattr(edited, "to_dict") else edited
        for row in records:
            tag = row["Тег"]
            want = bool(row["Заменить"])
            if groups.get(tag) and groups[tag][0].enabled != want:
                set_tag_enabled(tag, want)

    st.markdown("**Пропущенное**")
    labels = [label for _, label in MANUAL_TYPES]
    m1, m2, m3 = st.columns((3, 1.4, 1))
    fragment = m1.text_input(
        "Фрагмент из текста",
        placeholder="Выделите в документе или вставьте сюда",
        key="manual_fragment",
        label_visibility="collapsed",
    )
    chosen = m2.selectbox(
        "Тип",
        labels,
        index=0,
        label_visibility="collapsed",
    )
    m3.markdown("<div style='height: 1.55rem;'></div>", unsafe_allow_html=True)
    if m3.button("Добавить", width="stretch"):
        etype = MANUAL_TYPES[labels.index(chosen)][0]
        n, reason = add_manual(fragment, etype)
        if n:
            st.session_state.editor_rev += 1
            st.success(f"Добавлено вхождений: {n}")
            st.rerun()
        elif reason == "empty":
            st.warning("Выделите текст в документе слева или вставьте его в поле.")
        elif reason == "not_found":
            st.warning("Такой фрагмент не найден в тексте. Скопируйте его точно как в документе.")
        else:
            st.warning(
                "Этот фрагмент уже входит в найденную сущность. "
                "Снимите галочку у неё в таблице или выберите другой фрагмент."
            )

    st.markdown("---")
    st.subheader("Скачать")
    d1, d2, d3 = st.columns(3)
    if len(ok_files) == 1:
        name, data = export_file(ok_files[0])
        d1.download_button(
            f"Обезличенный файл ({name})",
            data=data,
            file_name=name,
            mime=mime_for(name),
            type="primary",
            width="stretch",
        )
    else:
        d1.download_button(
            "Все файлы + таблица (ZIP)",
            data=export_zip(),
            file_name="anonymized.zip",
            mime=MIME[".zip"],
            type="primary",
            width="stretch",
        )
    d2.download_button(
        "Таблица соответствий",
        data=mapping_json(),
        file_name="_mapping.json" if len(ok_files) > 1 else (
            os.path.splitext(ok_files[0].name)[0] + ".mapping.json"
        ),
        mime=MIME[".json"],
        width="stretch",
    )
    if len(ok_files) > 1:
        d3.caption("В ZIP уже есть `_mapping.json`.")

def page_restore():
    st.markdown(
        "Загрузите ответ LLM и таблицу соответствий — теги вернутся в исходные значения."
    )
    a1, a2 = st.columns(2)
    answer = a1.file_uploader(
        "Ответ LLM (txt, docx)",
        type=["txt", "docx"],
        key="restore_answer",
    )
    mapping_file = a2.file_uploader(
        "Таблица соответствий (JSON)",
        type=["json"],
        key="restore_mapping",
    )
    btn_col, _ = st.columns(2)
    with btn_col:
        if st.button(
            "Восстановить",
            type="primary",
            disabled=not (answer and mapping_file),
            width="stretch",
        ):
            try:
                mapping = load_mapping_bytes(mapping_file.getvalue())
                loaded = readers.load_from_bytes(answer.name, answer.getvalue())
            except Exception as exc:
                st.error(f"Не удалось прочитать файлы: {exc}")
                return
            restored, leftover = engine.deanonymize_text(loaded.text, mapping)
            st.session_state.restore_text = restored
            st.session_state.restore_leftover = leftover
            out_name = os.path.basename(writers.restored_output_path(answer.name))
            st.session_state.restore_name = out_name

    if not st.session_state.restore_text:
        st.info("Укажите оба файла и нажмите «Восстановить».")
        return

    if st.session_state.restore_leftover:
        st.warning(
            "Не найдены в таблице: " + ", ".join(st.session_state.restore_leftover)
        )
    else:
        st.success("Все теги восстановлены. Проверьте текст и скачайте файл.")

    st.text_area("Восстановленный текст", st.session_state.restore_text, height=420)
    out_name = st.session_state.restore_name or "restored.txt"
    st.download_button(
        f"Скачать {out_name}",
        data=writers.text_bytes(st.session_state.restore_text, out_name),
        file_name=out_name,
        mime=mime_for(out_name),
        type="primary",
    )


def inject_theme():
    css_path = os.path.join(os.path.dirname(__file__), "frontend", "theme.css")
    with open(css_path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def load_page_icon():
    icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "sberbank.png"))
    if not os.path.exists(icon_path):
        return "📄"
    try:
        from PIL import Image
        return Image.open(icon_path)
    except Exception:
        return icon_path


def main():
    page_icon = load_page_icon()
    st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon=page_icon)
    inject_theme()
    st.title(APP_TITLE)
    init_state()
    tab_anon, tab_restore = st.tabs(["Обезличивание", "Восстановление"])
    with tab_anon:
        page_anonymize()
    with tab_restore:
        page_restore()


if __name__ == "__main__":
    main()
