# Anonymizer

Локальное веб-приложение для обезличивания юридических документов. Находит персональные и идентифицирующие данные, заменяет их на теги вида `[ФИО1]`, затем восстанавливает исходный текст по таблице соответствий.

В облачную LLM уходит только обезличенный текст; JSON-таблица с исходными значениями остаётся у вас.

**Документация:** [пайплайн](docs/pipeline.md) · [алгоритм распознавания](docs/recognition.md) · [использование](docs/usage.md)
https://drive.google.com/file/d/1VwPGKEOiYUn2lNsxKAsQTfSq0Vfpe3We/view?usp=sharing

## Возможности

- Форматы: DOCX, PDF, TXT, CSV (несколько файлов — общий реестр тегов).
- ФИО, организации, адреса, даты, ИНН, ОГРН, КПП, СНИЛС, паспорта, счета, БИК, телефоны, email, сайты (Natasha NER + регулярки).
- PDF-сканы без текстового слоя — через Tesseract OCR.
- Подсветка, выбор категорий, ручное добавление пропусков, восстановление ответа LLM.

## Требования

- Python 3.11+
- Зависимости из `requirements.txt`

Для PDF-сканов нужен Tesseract с языками `rus` и `eng`. Если в PDF уже есть текст, OCR не используется.

## Запуск

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Альтернатива: `python -m anon`. Первый анализ документа может занять ~10 секунд — загрузка моделей Natasha. Приложение откроется в браузере, лимит загрузки — 500 МБ.

### Docker

```powershell
docker compose up --build
```

Интерфейс: http://127.0.0.1:8501. Tesseract уже в образе.

## Tesseract OCR

Ищется в таком порядке: `vendor/tesseract` → `PATH` → стандартные пути Windows (`C:\Program Files\Tesseract-OCR\`). Подробности — в [алгоритме распознавания](docs/recognition.md#ocr-pdf-сканов).

## Тесты

```powershell
python -m pip install pytest
pytest -q
```
