# -*- coding: utf-8 -*-
"""Страницы Streamlit: обезличивание и восстановление."""
from __future__ import annotations

import html
import os

import streamlit as st

from anon import config, engine, readers, writers
from anon.entities import ENTITY_TYPES, MANUAL_TYPES, SETTING_TYPES, Entity, load_mapping_bytes

from .constants import COLORS, DOWNLOAD_FORMATS, EXT_FORMAT, FORMAT_EXT, MIME
from .export import (
    export_zip,
    format_from_files,
    mime_for,
    render_download_format,
)
from .preview import highlight_html, render_preview
from .state import (
    FileState,
    add_manual,
    analyze_uploads,
    apply_enabled_types,
    count_words,
    set_tag_enabled,
)


def page_bottom_spacer() -> None:
    st.markdown('<div class="page-bottom-spacer" aria-hidden="true"></div>', unsafe_allow_html=True)


def render_category_types() -> None:
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
        f'{html.escape(label)}</span>'
        for c, label in SETTING_TYPES
    )
    with st.expander("Подсветка"):
        st.markdown(
            f'<div class="sidebar-legend-tags">{legend}</div>',
            unsafe_allow_html=True,
        )


def page_anonymize() -> None:
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
    _render_process_controls(uploads)

    files: list[FileState] = st.session_state.files
    if not files:
        st.info("Выберите файл или несколько файлов и нажмите «Обработать».")
        page_bottom_spacer()
        return

    errors = [fs for fs in files if fs.error]
    ok_files = [fs for fs in files if not fs.error]
    _render_metrics(files, ok_files, errors)
    if not ok_files:
        page_bottom_spacer()
        return

    current = _select_current_file(files)
    _render_document_preview(current)
    _render_entity_table(current)
    _render_manual_add()
    _render_download(ok_files)
    page_bottom_spacer()


def _render_process_controls(uploads) -> None:
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
            st.session_state.download_format = format_from_files(files)
            st.rerun()
    with toggle_col:
        st.checkbox(
            "Показать результат замены",
            value=False,
            key="show_result",
            disabled=not st.session_state.files,
        )


def _render_metrics(
    files: list[FileState], ok_files: list[FileState], errors: list[FileState],
) -> None:
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


def _select_current_file(files: list[FileState]) -> FileState:
    names = [fs.name for fs in files]
    current_name = st.selectbox("Файл", names, key="current_file")
    current = next(fs for fs in files if fs.name == current_name)
    for warning in current.warnings:
        st.warning(warning)
    if st.session_state.get("shown_file") != current_name:
        st.session_state.shown_file = current_name
        st.session_state.editor_rev += 1
    return current


def _render_document_preview(current: FileState) -> None:
    if current.error:
        st.error(current.error)
        selected = ""
    else:
        selected = render_preview(
            highlight_html(current.text, current.entities, st.session_state.show_result),
            key=f"preview_{current.name}",
        )
    if selected and selected != st.session_state.get("_last_preview_sel"):
        st.session_state._last_preview_sel = selected
        st.session_state.manual_fragment = selected


def _render_entity_table(current: FileState) -> None:
    st.caption("Найденные данные — снимите галочку, чтобы не заменять")
    groups: dict[str, list[Entity]] = {}
    for entity in current.entities:
        groups.setdefault(entity.tag or "?", []).append(entity)
    rows = []
    for tag, ents in groups.items():
        first = ents[0]
        rows.append({
            "Заменить": first.enabled,
            "Тег": tag,
            "Тип": ENTITY_TYPES.get(first.type, first.type),
            "Значение": first.text[:80],
            "Количество": len(ents),
        })
    if not rows:
        st.info("Ничего не найдено. Добавьте фрагмент вручную, если нужно.")
        return
    search = st.text_input(
        "Поиск по значению",
        placeholder="Например: Сбербанк",
        key="entity_value_search",
    )
    query = search.strip().lower()
    display_rows = (
        [row for row in rows if query in row["Значение"].lower()]
        if query else rows
    )
    if query and not display_rows:
        st.info("По вашему запросу ничего не найдено.")
        return
    if query:
        st.caption(f"Показано {len(display_rows)} из {len(rows)}")
    edited = st.data_editor(
        display_rows,
        key=f"ents_{st.session_state.editor_rev}",
        hide_index=True,
        width="stretch",
        disabled=["Тег", "Тип", "Значение", "Количество"],
        column_config={
            "Заменить": st.column_config.CheckboxColumn(width="small"),
            "Количество": st.column_config.NumberColumn(
                "Количество", width="small"
            ),
        },
    )
    records = edited.to_dict("records") if hasattr(edited, "to_dict") else edited
    for row in records:
        tag = row["Тег"]
        want = bool(row["Заменить"])
        if groups.get(tag) and groups[tag][0].enabled != want:
            set_tag_enabled(tag, want)


def _render_manual_add() -> None:
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
    if m3.button("Добавить", type="primary", width="stretch"):
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


def _render_download(ok_files: list[FileState]) -> None:
    st.markdown("---")
    st.subheader("Скачать")
    if st.session_state.get("download_format") not in DOWNLOAD_FORMATS:
        st.session_state.download_format = format_from_files(ok_files)
    selected_format, btn_col = render_download_format("download_format")
    with btn_col:
        st.download_button(
            "Скачать архив (обезличенный файл + таблица соответствий)",
            data=export_zip(selected_format),
            file_name="anonymized.zip",
            mime=MIME[".zip"],
            type="primary",
            key="download_anon_zip",
        )


def page_restore() -> None:
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
            st.session_state.restore_name = answer.name
            st.session_state.restore_download_format = EXT_FORMAT.get(
                os.path.splitext(answer.name)[1].lower(), "DOCX"
            )

    if not st.session_state.restore_text:
        st.info("Укажите оба файла и нажмите «Восстановить».")
        page_bottom_spacer()
        return

    if st.session_state.restore_leftover:
        st.warning(
            "Не найдены в таблице: " + ", ".join(st.session_state.restore_leftover)
        )
    else:
        st.success("Все теги восстановлены. Проверьте текст и скачайте файл.")

    st.text_area("Восстановленный текст", st.session_state.restore_text, height=420)
    source = st.session_state.restore_name or "restored.txt"
    if st.session_state.get("restore_download_format") not in DOWNLOAD_FORMATS:
        st.session_state.restore_download_format = EXT_FORMAT.get(
            os.path.splitext(source)[1].lower(), "DOCX"
        )
    selected_format, btn_col = render_download_format("restore_download_format")
    out_name = os.path.basename(
        writers.restored_output_path(source, ext=FORMAT_EXT[selected_format])
    )
    with btn_col:
        st.download_button(
            f"Скачать {out_name}",
            data=writers.text_bytes(st.session_state.restore_text, out_name),
            file_name=out_name,
            mime=mime_for(out_name),
            type="primary",
            key=f"download_restore_{selected_format}",
        )
    page_bottom_spacer()
