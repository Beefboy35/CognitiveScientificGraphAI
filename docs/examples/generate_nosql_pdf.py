"""Генератор демонстрационного PDF «Введение в NoSQL базы данных».

Скрипт берёт markdown-источник `nosql_databases.md` (рядом в этой папке)
и собирает на его основе многостраничный PDF с встроенным text layer
(то есть pypdf корректно извлечёт текст обратно при upload).

Зависимости: только `reportlab` (pip install reportlab).

Использование:
    cd backend
    pip install reportlab
    python ../docs/examples/generate_nosql_pdf.py
    # → ../docs/examples/nosql_databases.pdf

После генерации можно сразу загрузить:
    curl -X POST http://localhost:8000/v1/publications/upload \\
        -F "file=@docs/examples/nosql_databases.pdf"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE_MD = HERE / "nosql_databases.md"
OUTPUT_PDF = HERE / "nosql_databases.pdf"


def load_sections(md_path: Path) -> tuple[str, list[tuple[str, str]]]:
    """Парсит markdown-источник: заголовок-1 как title, остальные блоки —
    как (section_name, paragraph). Секции опознаются по одной строке,
    которая совпадает с заголовком (Аннотация / Введение / Метод / …)."""
    text = md_path.read_text(encoding="utf-8")
    lines = [line.rstrip() for line in text.splitlines()]
    title = ""
    sections: list[tuple[str, str]] = []
    current_section = ""
    current_paragraph: list[str] = []

    SECTION_NAMES = {
        "Аннотация",
        "Введение",
        "Метод",
        "Модели и данные",
        "Результаты",
        "Сравнение",
        "Гипотеза",
        "Ограничения",
        "Заключение",
        "Противоречие",
        "Воспроизводимость",
    }

    def flush() -> None:
        if current_section and current_paragraph:
            sections.append((current_section, " ".join(current_paragraph).strip()))

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            continue
        if stripped in SECTION_NAMES:
            flush()
            current_section = stripped
            current_paragraph = []
            continue
        current_paragraph.append(stripped)
    flush()
    return title, sections


def build_pdf(title: str, sections: list[tuple[str, str]], output: Path) -> None:
    """Собирает PDF через reportlab. Title — крупный жирный, секции —
    подзаголовки полужирные + параграф в одну колонку."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        sys.stderr.write(
            "ERROR: требуется `reportlab`. Установите его командой:\n"
            "    pip install reportlab\n"
        )
        sys.exit(1)

    # Подключаем шрифт с кириллицей. На большинстве дистрибутивов есть
    # DejaVuSans (Linux) или Arial/Times New Roman (Windows). Пробуем по
    # цепочке; если ничего не нашли — используем Helvetica (cyrillic не отрисует).
    font_paths = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        # Windows
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        # macOS
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    body_font = "Helvetica"
    bold_font = "Helvetica-Bold"
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("BodyFont", fp))
                body_font = "BodyFont"
                # Bold-вариант ищем рядом, иначе обходимся самим шрифтом.
                bold_candidate = fp.replace(".ttf", "-Bold.ttf").replace(
                    "DejaVuSans", "DejaVuSans-Bold"
                )
                if os.path.exists(bold_candidate):
                    pdfmetrics.registerFont(TTFont("BodyFontBold", bold_candidate))
                    bold_font = "BodyFontBold"
                else:
                    bold_font = body_font
                break
            except Exception:
                continue

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=20,
        leading=26,
        spaceAfter=18,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName=bold_font,
        fontSize=14,
        leading=18,
        spaceBefore=14,
        spaceAfter=6,
        textColor="#1a3a5a",
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=body_font,
        fontSize=11,
        leading=16,
        alignment=4,  # justify
        spaceAfter=6,
    )

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.0 * cm,
        title=title,
        author="CognitiveBaseAI demo",
    )

    story = []
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.4 * cm))
    for section_name, paragraph in sections:
        story.append(Paragraph(section_name, section_style))
        story.append(Paragraph(paragraph, body_style))

    doc.build(story)
    print(f"PDF written to {output}  ({output.stat().st_size:,} bytes)")


def main() -> None:
    if not SOURCE_MD.exists():
        sys.stderr.write(f"source not found: {SOURCE_MD}\n")
        sys.exit(1)
    title, sections = load_sections(SOURCE_MD)
    if not title or not sections:
        sys.stderr.write("could not parse title or sections from markdown\n")
        sys.exit(1)
    print(f"parsed: title={title!r}, sections={len(sections)}")
    build_pdf(title, sections, OUTPUT_PDF)


if __name__ == "__main__":
    main()
