#!/usr/bin/env python3
"""Generate a zoomer-style PDF course about AI moneymaking."""

from __future__ import annotations

import math
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
WORD_COURSE = 'КУРС'  # assembled to avoid tooling eating glyphs

FONTS = ROOT / "fonts"
OUT = ROOT.parent / "output" / "kak-ebat-neyronki-i-delat-babki.pdf"
ARTIFACT = Path("/opt/cursor/artifacts/kak-ebat-neyronki-i-delat-babki.pdf")

# Visual system: night club + acid zine (not purple, not cream-serif)
BG = HexColor("#0B0B0C")
BG2 = HexColor("#141417")
PANEL = HexColor("#1C1C22")
LIME = HexColor("#C8FF3D")
CORAL = HexColor("#FF4D6A")
CREAM = HexColor("#F4F0E6")
MUTED = HexColor("#9A9AA3")
STROKE = HexColor("#2A2A33")

W, H = A4
MARGIN = 18 * mm


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("Body", str(FONTS / "Montserrat-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("BodyMed", str(FONTS / "Montserrat-Medium.ttf")))
    pdfmetrics.registerFont(TTFont("Semi", str(FONTS / "Montserrat-SemiBold.ttf")))
    pdfmetrics.registerFont(TTFont("Bold", str(FONTS / "Montserrat-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Extra", str(FONTS / "Montserrat-ExtraBold.ttf")))
    pdfmetrics.registerFont(TTFont("Black", str(FONTS / "Montserrat-Black.ttf")))
    # fallbacks for any missing glyph edge-cases
    pdfmetrics.registerFont(TTFont("Noto", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("NotoBold", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("Mono", "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("MonoBold", "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf"))


def paint_bg(c: canvas.Canvas, color: Color = BG) -> None:
    c.setFillColor(color)
    c.rect(0, 0, W, H, fill=1, stroke=0)


def draw_noise_dots(c: canvas.Canvas, seed: int = 7, n: int = 90) -> None:
    """Cheap atmospheric speckles — no images required."""
    x = seed * 1103515245 + 12345
    c.setFillColor(HexColor("#FFFFFF"))
    for i in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        px = (x % int(W))
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        py = (x % int(H))
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        a = 0.03 + (x % 40) / 1000.0
        c.setFillColor(Color(1, 1, 1, alpha=a))
        c.circle(px, py, 0.8 + (x % 3) * 0.4, fill=1, stroke=0)


def draw_diagonal_band(c: canvas.Canvas, y: float, color: Color, height: float = 28) -> None:
    c.saveState()
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(0, y)
    p.lineTo(W, y + 40)
    p.lineTo(W, y + 40 + height)
    p.lineTo(0, y + height)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()


def footer(c: canvas.Canvas, page_no: int, total: int | None = None) -> None:
    c.setFillColor(MUTED)
    c.setFont("BodyMed", 8)
    c.drawString(MARGIN, 10 * mm, "НЕЙРО × БАБКИ  ·  no cap edition")
    label = f"{page_no}" if total is None else f"{page_no} / {total}"
    c.drawRightString(W - MARGIN, 10 * mm, label)


def wrap_text(text: str, font: str, size: float, max_width: float) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        if pdfmetrics.stringWidth(trial, font, size) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def draw_paragraph(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font: str = "Body",
    size: float = 10.5,
    leading: float = 15,
    color: Color = CREAM,
) -> float:
    c.setFillColor(color)
    c.setFont(font, size)
    for line in wrap_text(text, font, size, max_width):
        c.drawString(x, y, line)
        y -= leading
    return y


def draw_bullet(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    bullet: str = "→",
    accent: Color = LIME,
) -> float:
    c.setFillColor(accent)
    c.setFont("Bold", 11)
    c.drawString(x, y, bullet)
    return draw_paragraph(c, text, x + 14, y, max_width - 14, "Body", 10.5, 14.5, CREAM)


def chip(c: canvas.Canvas, text: str, x: float, y: float, bg: Color = LIME, fg: Color = BG) -> float:
    pad_x, pad_y = 8, 4
    c.setFont("Bold", 8)
    tw = pdfmetrics.stringWidth(text, "Bold", 8)
    c.setFillColor(bg)
    c.roundRect(x, y - pad_y, tw + pad_x * 2, 14 + pad_y, 3, fill=1, stroke=0)
    c.setFillColor(fg)
    c.drawString(x + pad_x, y + 1, text)
    return tw + pad_x * 2 + 8


class CoursePDF:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.page = 0
        self.toc_targets: dict[str, int] = {}

    def new_page(self, bg: Color = BG) -> None:
        if self.page:
            self.c.showPage()
        self.page += 1
        paint_bg(self.c, bg)
        draw_noise_dots(self.c, seed=self.page * 17)

    def finish(self) -> None:
        self.c.save()

    # ---------- pages ----------

    def cover(self) -> None:
        self.new_page(BG)
        draw_diagonal_band(self.c, H - 120, LIME, 18)
        draw_diagonal_band(self.c, 80, CORAL, 12)

        self.c.setFillColor(LIME)
        self.c.setFont("Black", 11)
        self.c.drawString(MARGIN, H - 28 * mm, f"PDF-{WORD_COURSE}  ·  2026  ·  FREE-ISH ENERGY")

        self.c.setFillColor(CREAM)
        self.c.setFont("Black", 34)
        lines = [
            "КАК ПОЛЬЗОВАТЬСЯ",
            "НЕЙРОСЕТЯМИ",
            "И ЗАРАБАТЫВАТЬ",
            "ЕБЕЙШИЕ БАБКИ",
        ]
        y = H - 55 * mm
        for line in lines:
            self.c.drawString(MARGIN, y, line)
            y -= 16 * mm

        self.c.setFillColor(MUTED)
        self.c.setFont("BodyMed", 12)
        y = draw_paragraph(
            self.c,
            "Гайд для зумеров без иллюзий: инструменты, промпты, офферы, "
            "автоматизация и как не попасть на хуйню с «пассивным доходом за 2 дня».",
            MARGIN,
            y - 4 * mm,
            W - 2 * MARGIN,
            "BodyMed",
            11.5,
            16,
            MUTED,
        )

        # big badge
        self.c.setFillColor(PANEL)
        self.c.roundRect(MARGIN, 32 * mm, W - 2 * MARGIN, 38 * mm, 8, fill=1, stroke=0)
        self.c.setFillColor(CORAL)
        self.c.setFont("Black", 10)
        self.c.drawString(MARGIN + 10 * mm, 58 * mm, "ВАЙБ")
        self.c.setFillColor(CREAM)
        self.c.setFont("Semi", 11)
        draw_paragraph(
            self.c,
            "Мат есть. Хайп срезан. Схемы рабочие. Если ты пришёл за магической кнопкой «бабло» — "
            "закрой PDF и иди троллить комментарии, бро.",
            MARGIN + 10 * mm,
            50 * mm,
            W - 2 * MARGIN - 20 * mm,
            "Body",
            10,
            14,
            CREAM,
        )
        footer(self.c, self.page)

    def toc(self) -> None:
        self.new_page(BG2)
        self.c.setFillColor(LIME)
        self.c.setFont("Black", 10)
        self.c.drawString(MARGIN, H - 22 * mm, "ОГЛАВЛЕНИЕ")
        self.c.setFillColor(CREAM)
        self.c.setFont("Black", 26)
        self.c.drawString(MARGIN, H - 36 * mm, "Что бляха внутри")

        items = [
            ("01", "Миндсет: почему все срут кирпичами"),
            ("02", "Стек: чем реально ебать задачи"),
            ("03", "Промпт-магия без эзотерики"),
            ("04", "Контент-завод и алгоритм"),
            ("05", "Услуги, фриланс, белые офферы"),
            ("06", "Цифровые продукты и микро-SaaS"),
            ("07", "Автоматизация: ты vs твоя лень"),
            ("08", "Продажи: как закрывать без кринжа"),
            ("09", "Антискам: куда не лезть нахуй"),
            ("10", "30 дней до первых денег"),
            ("XX", "Чит-шит промптов + финал"),
        ]
        y = H - 50 * mm
        for num, title in items:
            self.c.setFillColor(CORAL if num == "XX" else LIME)
            self.c.setFont("Black", 12)
            self.c.drawString(MARGIN, y, num)
            self.c.setFillColor(CREAM)
            self.c.setFont("Semi", 12)
            self.c.drawString(MARGIN + 18 * mm, y, title)
            self.c.setStrokeColor(STROKE)
            self.c.setLineWidth(0.6)
            self.c.line(MARGIN, y - 4 * mm, W - MARGIN, y - 4 * mm)
            y -= 14 * mm
        footer(self.c, self.page)

    def section_divider(self, num: str, title: str, subtitle: str) -> None:
        self.new_page(BG)
        self.c.setFillColor(LIME)
        self.c.rect(0, 0, 14 * mm, H, fill=1, stroke=0)
        self.c.setFillColor(BG)
        self.c.setFont("Black", 14)
        self.c.saveState()
        self.c.translate(9 * mm, H / 2)
        self.c.rotate(90)
        self.c.drawCentredString(0, 0, f"MODULE {num}")
        self.c.restoreState()

        self.c.setFillColor(MUTED)
        self.c.setFont("Bold", 11)
        self.c.drawString(MARGIN + 10 * mm, H - 40 * mm, f"ГЛАВА {num}")

        self.c.setFillColor(CREAM)
        self.c.setFont("Black", 28)
        y = H - 58 * mm
        for line in wrap_text(title, "Black", 28, W - 2 * MARGIN - 12 * mm):
            self.c.drawString(MARGIN + 10 * mm, y, line)
            y -= 12 * mm

        self.c.setFillColor(CORAL)
        self.c.setFont("Semi", 12)
        y = draw_paragraph(
            self.c,
            subtitle,
            MARGIN + 10 * mm,
            y - 6 * mm,
            W - 2 * MARGIN - 12 * mm,
            "Semi",
            12,
            17,
            CORAL,
        )
        footer(self.c, self.page)

    def content_page(self, heading: str, blocks: list[dict]) -> None:
        self.new_page(BG2)
        self.c.setFillColor(LIME)
        self.c.setFont("Black", 9)
        self.c.drawString(MARGIN, H - 18 * mm, "НЕЙРО × БАБКИ")
        self.c.setFillColor(CREAM)
        self.c.setFont("Black", 18)
        y = H - 30 * mm
        for line in wrap_text(heading, "Black", 18, W - 2 * MARGIN):
            self.c.drawString(MARGIN, y, line)
            y -= 8 * mm
        y -= 4 * mm

        for block in blocks:
            kind = block.get("kind", "p")
            if y < 28 * mm:
                footer(self.c, self.page)
                self.new_page(BG2)
                y = H - 22 * mm

            if kind == "h":
                y -= 3 * mm
                self.c.setFillColor(LIME)
                self.c.setFont("Black", 12)
                self.c.drawString(MARGIN, y, block["text"])
                y -= 7 * mm
            elif kind == "p":
                y = draw_paragraph(
                    self.c, block["text"], MARGIN, y, W - 2 * MARGIN, "Body", 10.5, 15, CREAM
                )
                y -= 3 * mm
            elif kind == "b":
                y = draw_bullet(self.c, block["text"], MARGIN, y, W - 2 * MARGIN)
                y -= 2.5 * mm
            elif kind == "callout":
                text = block["text"]
                lines = wrap_text(text, "BodyMed", 10, W - 2 * MARGIN - 16 * mm)
                box_h = 10 * mm + len(lines) * 14
                if y - box_h < 24 * mm:
                    footer(self.c, self.page)
                    self.new_page(BG2)
                    y = H - 22 * mm
                bg = CORAL if block.get("tone") == "warn" else PANEL
                fg = BG if block.get("tone") == "warn" else CREAM
                label_c = BG if block.get("tone") == "warn" else LIME
                self.c.setFillColor(bg)
                self.c.roundRect(MARGIN, y - box_h + 8, W - 2 * MARGIN, box_h, 6, fill=1, stroke=0)
                self.c.setFillColor(label_c)
                self.c.setFont("Black", 8)
                self.c.drawString(MARGIN + 6 * mm, y - 2 * mm, block.get("label", "NOTE").upper())
                ty = y - 8 * mm
                self.c.setFillColor(fg)
                self.c.setFont("BodyMed", 10)
                for line in lines:
                    self.c.drawString(MARGIN + 6 * mm, ty, line)
                    ty -= 14
                y = y - box_h - 4 * mm
            elif kind == "prompt":
                text = block["text"]
                lines = wrap_text(text, "Mono", 8.5, W - 2 * MARGIN - 14 * mm)
                box_h = 12 * mm + len(lines) * 12
                if y - box_h < 24 * mm:
                    footer(self.c, self.page)
                    self.new_page(BG2)
                    y = H - 22 * mm
                self.c.setFillColor(HexColor("#101014"))
                self.c.setStrokeColor(LIME)
                self.c.setLineWidth(1.2)
                self.c.roundRect(MARGIN, y - box_h + 6, W - 2 * MARGIN, box_h, 5, fill=1, stroke=1)
                self.c.setFillColor(LIME)
                self.c.setFont("Bold", 8)
                self.c.drawString(MARGIN + 5 * mm, y - 1 * mm, "PROMPT COPY-PASTE")
                ty = y - 8 * mm
                self.c.setFillColor(CREAM)
                self.c.setFont("Mono", 8.5)
                for line in lines:
                    self.c.drawString(MARGIN + 5 * mm, ty, line)
                    ty -= 12
                y = y - box_h - 4 * mm
            elif kind == "chips":
                x = MARGIN
                row_y = y
                for t in block["items"]:
                    width_needed = pdfmetrics.stringWidth(t, "Bold", 8) + 24
                    if x + width_needed > W - MARGIN:
                        x = MARGIN
                        row_y -= 10 * mm
                    chip(self.c, t, x, row_y, LIME if block.get("tone") != "warn" else CORAL, BG)
                    x += width_needed
                y = row_y - 10 * mm

        footer(self.c, self.page)


def build() -> Path:
    register_fonts()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    doc = CoursePDF(OUT)

    doc.cover()
    doc.toc()

    # 01
    doc.section_divider(
        "01",
        "Миндсет: почему все срут кирпичами",
        "AI не сделает тебя богатым, пока ты сам не перестанешь быть ходячим «потом разберусь».",
    )
    doc.content_page(
        "Сначала мозги, потом нейронки",
        [
            {
                "kind": "p",
                "text": (
                    "Слушай сюда. Нейросети — это не казино и не крипта-2021. Это ускоритель. "
                    "Если ты ускоряешь хуйню, получишь больше хуйни. Если ускоряешь оффер, который "
                    "людям реально нужен — получишь бабки. Кажется очевидным, но половина тиктока "
                    "до сих пор верит в «один промпт = мазерлада»."
                ),
            },
            {"kind": "h", "text": "Три правила, которые не обсуждаются"},
            {
                "kind": "b",
                "text": "Скорость > перфекционизм. Выкатил черновик за час — уже в игре. Полируешь неделю — мертв.",
            },
            {
                "kind": "b",
                "text": "Дистрибуция = кислород. Без аудитории/клиентов твой Midjourney — просто красивая дрочильня.",
            },
            {
                "kind": "b",
                "text": "Ответственность на тебе. Модель ошиблась? Ты проебал проверку. Клиент не простил — твои проблемы.",
            },
            {
                "kind": "callout",
                "label": "hard truth",
                "tone": "warn",
                "text": (
                    "Если твоя стратегия — «сгенерирую 400 статей в день и захвачу SEO», "
                    "приготовься к бану, штрафу и позорному твиту от вебмастеров. Google не долбоёб."
                ),
            },
            {"kind": "h", "text": "Кем ты НЕ должен быть"},
            {
                "kind": "chips",
                "items": [
                    "гуру за 3 дня",
                    "AI-бро без оффера",
                    "копипастер чужих курсов",
                    "крипто-шаман",
                ],
                "tone": "warn",
            },
            {
                "kind": "p",
                "text": (
                    "Будь оператором системы: нашёл боль → собрал решение с AI → продал → улучшил. "
                    "Повторил. Вот и весь «секрет», бля."
                ),
            },
        ],
    )

    # 02
    doc.section_divider(
        "02",
        "Стек: чем реально ебать задачи",
        "Не надо 47 подписок. Нужен узкий набор, который ты реально юзаешь каждый день.",
    )
    doc.content_page(
        "Минимальный стек без кринжа",
        [
            {"kind": "h", "text": "Текст / мозг"},
            {
                "kind": "b",
                "text": "ChatGPT / Claude / Gemini — черновики, стратегия, письма, разбор ниши, код-скелеты.",
            },
            {
                "kind": "b",
                "text": "Perplexity / поиск с цитатами — когда надо факты, а не галлюцинации модели.",
            },
            {"kind": "h", "text": "Картинки / видео / войсы"},
            {
                "kind": "b",
                "text": "Midjourney / Flux / Ideogram — обложки, креативы, мудборды, рекламные ассеты.",
            },
            {
                "kind": "b",
                "text": "Runway / Kling / Pika — короткие ролики, B-roll, анимированные сцены.",
            },
            {
                "kind": "b",
                "text": "ElevenLabs / похожие — войсовер для Reels без «алло это я с микрофона от нокиа».",
            },
            {"kind": "h", "text": "Автоматизация"},
            {
                "kind": "b",
                "text": "Make / n8n / Zapier — связки форм, таблиц, Telegram, CRM и генерации.",
            },
            {
                "kind": "b",
                "text": "Notion / Airtable — база знаний, контент-план, CRM для маленьких сделок.",
            },
            {
                "kind": "callout",
                "label": "stack rule",
                "text": (
                    "Правило одного стека: если инструмент не дал тебе денег или сэкономил 3+ часа "
                    "за неделю — нахуй его, отписывайся. Подписки любят жрать твой баланс молча."
                ),
            },
            {
                "kind": "p",
                "text": (
                    "Лайфхак уровня «вау»: выбери ОДНУ нишу и ОДИН формат контента на 30 дней. "
                    "Не прыгай с «AI-аватаров» на «нейро-тату» и обратно. Фокус — это чит-код."
                ),
            },
        ],
    )

    # 03
    doc.section_divider(
        "03",
        "Промпт-магия без эзотерики",
        "Хороший промпт — это ТЗ для джуна, а не заклинание из ТикТока с 17 ролями «ты гуру».",
    )
    doc.content_page(
        "Как выбивать нормальный аутпут",
        [
            {
                "kind": "p",
                "text": (
                    "Модель — это очень умный стажёр с амнезией. Она не читает твои мысли. "
                    "Если промпт звучит как «сделай круто», на выходе будет среднего качества кал."
                ),
            },
            {"kind": "h", "text": "Формула, которая работает"},
            {
                "kind": "b",
                "text": "Роль: кто говорит (маркетолог / юрист-лайт / редактор Reels).",
            },
            {
                "kind": "b",
                "text": "Контекст: кто клиент, какая боль, какие ограничения.",
            },
            {
                "kind": "b",
                "text": "Задача: конкретный deliverable (текст / таблица / скрипт / оффер).",
            },
            {
                "kind": "b",
                "text": "Критерии: тон, длина, запреты, примеры «хорошо/плохо».",
            },
            {
                "kind": "b",
                "text": "Формат вывода: markdown / JSON / таблица — чтобы сразу юзать.",
            },
            {
                "kind": "prompt",
                "text": (
                    "Ты — прямой маркетолог без воды. Ниша: {ниша}. ЦА: {кто}. Боль: {боль}. "
                    "Сделай: 1) оффер в 1 предложении 2) 5 хуков для Reels 3) скрипт на 30 сек "
                    "4) CTA. Тон: зумерский, жёсткий, без корпоративного дерьма. "
                    "Если данных мало — задай 5 уточняющих вопросов, потом генерируй."
                ),
            },
            {
                "kind": "callout",
                "label": "pro move",
                "text": (
                    "Гони модель через итерации: «жёстче», «короче на 40%», «убери клише», "
                    "«добавь конкретику под РФ/СНГ». Один проход — черновик. Три прохода — уже можно постить."
                ),
            },
            {"kind": "h", "text": "Антипаттерны"},
            {
                "kind": "chips",
                "items": [
                    "будь креативным!!!",
                    "как гуру с Ютуба",
                    "100 вариантов сразу",
                    "игнорируй законы",
                ],
                "tone": "warn",
            },
        ],
    )

    # 04
    doc.section_divider(
        "04",
        "Контент-завод и алгоритм",
        "Алгоритм любит регулярность и удержание. AI даёт скорость. Ты даёшь вкус и позицию.",
    )
    doc.content_page(
        "Контент, который не стыдно постить",
        [
            {
                "kind": "p",
                "text": (
                    "Самая жирная ошибка — генерить безликую кашу и срать ей во все соцсети. "
                    "Люди чувствуют AI-фальшь за три километра. Выход: модель делает каркас, "
                    "ты добавляешь личный опыт, мнение, кейсы, мат (где уместно), детали."
                ),
            },
            {"kind": "h", "text": "Конвейер на минималках"},
            {
                "kind": "b",
                "text": "Банк идей: 50 болей ЦА → кластеры тем.",
            },
            {
                "kind": "b",
                "text": "Пакетная генерация хуков/скриптов раз в неделю.",
            },
            {
                "kind": "b",
                "text": "Съёмка/озвучка пачкой (batch). Не по одному ролику в сутки, страдая.",
            },
            {
                "kind": "b",
                "text": "Монтаж + субтитры + обложка. AI помогает, но финал — твой глаз.",
            },
            {
                "kind": "b",
                "text": "Публикация + ответы в комментах. Комменты — это бесплатный трафик, не игнорь.",
            },
            {
                "kind": "callout",
                "label": "money angle",
                "text": (
                    "Каждый 3–4 пост — мягкий оффер: разбор, консультация, шаблон, гайд. "
                    "Если ты только «полезный контент» без CTA — ты волонтёр алгоритма, а не бизнес."
                ),
            },
            {
                "kind": "prompt",
                "text": (
                    "Сделай контент-план на 14 дней для {платформа}. Ниша: {ниша}. "
                    "Формат: хук / тезис / пример / CTA. 30% — экспертность, 40% — разборы ошибок, "
                    "20% — закулисье процесса, 10% — оффер. Без воды и «не забывайте подписаться»."
                ),
            },
        ],
    )

    # 05
    doc.section_divider(
        "05",
        "Услуги, фриланс, белые офферы",
        "Самый быстрый путь к деньгам для большинства — услуги. Не курс мечты, а закрытие чужой боли.",
    )
    doc.content_page(
        "Что продавать, пока ты не «бренд»",
        [
            {"kind": "h", "text": "Офферы, которые берут"},
            {
                "kind": "b",
                "text": "Упаковка: лендинг + оффер + креативы под рекламу за фикс.",
            },
            {
                "kind": "b",
                "text": "Контент под ключ: 12 Reels/месяц для локального бизнеса.",
            },
            {
                "kind": "b",
                "text": "AI-ассистент для операционки: письма, КП, скрипты продаж, база FAQ.",
            },
            {
                "kind": "b",
                "text": "Исследование ниши + таблица конкурентов + позиционирование.",
            },
            {
                "kind": "b",
                "text": "Автоворонка lite: форма → Notion/CRM → прогрев в Telegram.",
            },
            {
                "kind": "callout",
                "label": "pricing vibe",
                "text": (
                    "Не продавай «час работы». Продавай результат: «12 роликов + сценарии + обложки». "
                    "Часы — это способ клиенту торговаться. Результат — способ тебе зарабатывать."
                ),
            },
            {"kind": "h", "text": "Где искать первых"},
            {
                "kind": "chips",
                "items": [
                    "Telegram-чаты",
                    "друзья бизнеса",
                    "Avito/профи",
                    "холод в Instagram",
                    "партнёрки",
                ],
            },
            {
                "kind": "p",
                "text": (
                    "Скрипт первого сообщения: кто ты → что заметил у них → что сделаешь → "
                    "соцдоказательство/пример → мягкий вопрос. Без «доброго дня, можно минутку» — "
                    "это сразу в игнор."
                ),
            },
            {
                "kind": "prompt",
                "text": (
                    "Напиши 5 холодных сообщений для владельца {тип бизнеса}. "
                    "Стиль: короткий, уважительный, без кринж-продаж. "
                    "Каждое: наблюдение → польза → вопрос. До 500 знаков."
                ),
            },
        ],
    )

    # 06
    doc.section_divider(
        "06",
        "Цифровые продукты и микро-SaaS",
        "Когда услуга стабильна — упакуй процесс в продукт. Масштаб без вечного «ещё один созвон».",
    )
    doc.content_page(
        "От созвонов к ассетам",
        [
            {
                "kind": "p",
                "text": (
                    "Цифровой продукт — это не обязательно «курс за 90к». Это может быть Notion-система, "
                    "пачка промптов, шаблоны креативов, чек-листы найма, мини-бот, табличный дашборд. "
                    "Главное — чтобы человек после покупки сказал: «бля, мне стало легче»."
                ),
            },
            {"kind": "h", "text": "Идеи с низким порогом"},
            {
                "kind": "b",
                "text": "Промпт-паки под узкую нишу (риелторы, стоматологии, коучи без токсичности).",
            },
            {
                "kind": "b",
                "text": "Шаблоны контента + календарь + примеры хуков.",
            },
            {
                "kind": "b",
                "text": "Микро-сервис: «залил бриф → получил 10 креативов».",
            },
            {
                "kind": "b",
                "text": "Чек-лист аудита рекламы / сайта / воронки с AI-разбором.",
            },
            {
                "kind": "callout",
                "label": "product rule",
                "text": (
                    "Сначала продай руками 5–10 раз. Потом автоматизируй. "
                    "Иначе ты пилишь продукт, который никому не нужен, и орёшь в пустоту."
                ),
            },
            {
                "kind": "p",
                "text": (
                    "Микро-SaaS на коленке: Google Form/Typeform → n8n → LLM → Google Doc/Telegram. "
                    "Это уже продукт. Не надо сразу писать свой ChatGPT на Kubernetes, гений."
                ),
            },
        ],
    )

    # 07
    doc.section_divider(
        "07",
        "Автоматизация: ты vs твоя лень",
        "Автоматизируй повторяющееся. Не автоматизируй то, чего ещё не понимаешь руками.",
    )
    doc.content_page(
        "Системы, которые печатают время",
        [
            {"kind": "h", "text": "Что автоматизировать первым"},
            {
                "kind": "b",
                "text": "Сбор лидов в одну таблицу + уведомление в Telegram.",
            },
            {
                "kind": "b",
                "text": "Первичный ответ клиенту (не финальный договор, а «принял/уточнил»).",
            },
            {
                "kind": "b",
                "text": "Генерация черновиков постов из таблицы идей.",
            },
            {
                "kind": "b",
                "text": "Транскрипт созвона → саммари → задачи.",
            },
            {
                "kind": "b",
                "text": "Еженедельный отчёт себе: что сделано / что продано / где затык.",
            },
            {
                "kind": "callout",
                "label": "warning",
                "tone": "warn",
                "text": (
                    "Автоответчики, которые пиздят от себя юридические обещания — путь в бан и суд. "
                    "Держи человека в контуре решений, где есть деньги, риски и репутация."
                ),
            },
            {
                "kind": "prompt",
                "text": (
                    "Спроектируй n8n/Make сценарий: новая заявка из формы → очистка данных → "
                    "LLM классифицирует лид (горячий/тёплый/холодный) → запись в Notion → "
                    "сообщение мне в Telegram с 3 буллетами и черновиком ответа. Выдай узлы по шагам."
                ),
            },
        ],
    )

    # 08
    doc.section_divider(
        "08",
        "Продажи: как закрывать без кринжа",
        "Продажа — это помощь принять решение. Не танцы с бубном и не унижение.",
    )
    doc.content_page(
        "Закрытие сделок по-человечески",
        [
            {
                "kind": "p",
                "text": (
                    "Зумеры часто либо стыдятся продавать, либо впадают в режим токсичного инфоцыганства. "
                    "Середина: ясный оффер, понятная цена, доказательства, нормальный follow-up."
                ),
            },
            {"kind": "h", "text": "Каркас созвона/переписки"},
            {
                "kind": "b",
                "text": "Диагностика: какая сейчас боль и сколько она стоит клиенту.",
            },
            {
                "kind": "b",
                "text": "Показ процесса: как ты решишь это с AI + контролем качества.",
            },
            {
                "kind": "b",
                "text": "Кейс/пример: даже маленький — лучше, чем «я просто шарю».",
            },
            {
                "kind": "b",
                "text": "Оффер и рамки: что входит / что не входит / срок / цена.",
            },
            {
                "kind": "b",
                "text": "Следующий шаг: счёт / предоплата / бриф. Без «ну вы подумайте».",
            },
            {
                "kind": "callout",
                "label": "follow-up",
                "text": (
                    "Люди заняты, а не ненавидят тебя. 2–3 коротких follow-up — норма. "
                    "10 сообщений «ну что там??» — уже сталкер-вайб, стоп."
                ),
            },
            {
                "kind": "prompt",
                "text": (
                    "Клиент сказал: «дорого». Ниша: {ниша}. Мой оффер: {оффер}. "
                    "Дай 4 ответа: 1) переформулировка ценности 2) вариант пакета меньше "
                    "3) вопрос про стоимость проблемы 4) вежливый выход без унижения."
                ),
            },
        ],
    )

    # 09
    doc.section_divider(
        "09",
        "Антискам: куда не лезть нахуй",
        "Деньги бывают быстрые и грязные. Грязные обычно кончаются баном, долгами и стыдом.",
    )
    doc.content_page(
        "Красные флаги индустрии",
        [
            {"kind": "h", "text": "Топ хуйни, которую пропускаем"},
            {
                "kind": "b",
                "text": "«Нейросеть печатает $1000/день без вложений» — классика развода.",
            },
            {
                "kind": "b",
                "text": "Накрутки, серые арбитры с чужими картами, фишинг-креативы — это уже не «бизнес».",
            },
            {
                "kind": "b",
                "text": "Продажа чужих курсов под видом своих — путь к репутационному пиздецу.",
            },
            {
                "kind": "b",
                "text": "Генерация дипфейков людей без согласия — этический и юридический ад.",
            },
            {
                "kind": "b",
                "text": "Мед/фин/юр советы от модели без проверки профи — можно накосячить жестоко.",
            },
            {
                "kind": "callout",
                "label": "keep it clean",
                "tone": "warn",
                "text": (
                    "Белый рынок огромный: локальный бизнес, эксперты, e-com, образование, "
                    "контент, автоматизация. Там хватает денег без криминального вайба."
                ),
            },
            {
                "kind": "p",
                "text": (
                    "Правило репутации: если стыдно рассказать маме/будущему работодателю, "
                    "чем ты занимаешься — скорее всего, это говностратегия."
                ),
            },
        ],
    )

    # 10
    doc.section_divider(
        "10",
        "30 дней до первых денег",
        "План без мотивирующих цитат. Просто делай по дням и не ищи оправданий.",
    )
    doc.content_page(
        "Твой месяц в режиме «оператор»",
        [
            {"kind": "h", "text": "Дни 1–3 · Выбор"},
            {
                "kind": "b",
                "text": "Выбери нишу, где можешь найти 20 потенциальных клиентов уже сейчас.",
            },
            {
                "kind": "b",
                "text": "Сформулируй один оффер на результат. Запиши цену. Да, страшно. Похуй, пиши.",
            },
            {"kind": "h", "text": "Дни 4–7 · Упаковка"},
            {
                "kind": "b",
                "text": "1 страница: кто ты / что делаешь / пример / цена / как купить.",
            },
            {
                "kind": "b",
                "text": "Собери 3 мини-кейса хоть на друзьях/псевдопроекте с честным дисклеймером.",
            },
            {"kind": "h", "text": "Дни 8–14 · Контент + аутрич"},
            {
                "kind": "b",
                "text": "10 единиц контента. 30 холодных/тёплых касаний. Трекай ответы в таблице.",
            },
            {"kind": "h", "text": "Дни 15–21 · Закрытие"},
            {
                "kind": "b",
                "text": "Дожимай диалоги. Сделай 1–3 тестовых работы. Собери отзывы.",
            },
            {"kind": "h", "text": "Дни 22–30 · Система"},
            {
                "kind": "b",
                "text": "Запакуй процесс в шаблоны. Подними цену на 15–30%, если спрос есть.",
            },
            {
                "kind": "b",
                "text": "Автоматизируй одно узкое место. Повтори цикл.",
            },
            {
                "kind": "callout",
                "label": "success metric",
                "text": (
                    "Успех месяца — не «стал миллионером». Успех — первые оплаченные деньги "
                    "за AI-усиленную услугу + понятный повторяемый процесс. Всё остальное — копинг."
                ),
            },
        ],
    )

    # cheat sheet + finale
    doc.section_divider(
        "XX",
        "Чит-шит и выходная",
        "Сохрани. Юзай. Не пересылай родственникам без предупреждения про мат.",
    )
    doc.content_page(
        "Промпты на каждый день",
        [
            {"kind": "h", "text": "Разбор ниши"},
            {
                "kind": "prompt",
                "text": (
                    "Разбери нишу {ниша}: боли, сегменты ЦА, где тусуются, какие офферы уже есть, "
                    "какие дыры можно закрыть с AI за 7 дней. Таблица + приоритеты."
                ),
            },
            {"kind": "h", "text": "Оффер"},
            {
                "kind": "prompt",
                "text": (
                    "Собери 7 офферов формата «результат + срок + доказательство». "
                    "Без слов «качественный» и «профессиональный». Жёстко и конкретно."
                ),
            },
            {"kind": "h", "text": "Контент"},
            {
                "kind": "prompt",
                "text": (
                    "Из этой темы {тема} сделай: 1 вирусный хук, 1 экспертный пост, "
                    "1 карусель из 6 слайдов, 1 CTA на консультацию. Тон: живой, зумерский."
                ),
            },
            {"kind": "h", "text": "Контроль качества"},
            {
                "kind": "prompt",
                "text": (
                    "Проверь текст как злой редактор: убери воду, клише, ложные обещания. "
                    "Выдай: red flags / что усилить / финальная версия."
                ),
            },
        ],
    )
    doc.content_page(
        "Финал: иди делай, а не сохраняй в «прочитать позже»",
        [
            {
                "kind": "p",
                "text": (
                    "Ты дочитал до конца — уже редкий покемон. Но PDF сам бабки не накликает. "
                    "Открой таблицу. Выбери нишу. Напиши 10 сообщений. Выложи первый черновик. "
                    "Сегодня. Не «с понедельника», не «когда прокачаю Notion»."
                ),
            },
            {
                "kind": "callout",
                "label": "last words",
                "text": (
                    "Нейросети дают рычаг. Рычаг без движения — просто палка. "
                    "Двигай. Ошибайся быстро. Чини. Кассируй. И пусть у тебя реально будут "
                    "ебейшие бабки — честно заработанные, без инфоцыганского пиздежа."
                ),
            },
            {
                "kind": "p",
                "text": (
                    "Если курс зашёл — пересобери его под свою нишу своим языком и продавай уже "
                    "свой опыт. Это и есть игра. Удачи, машина."
                ),
            },
            {
                "kind": "chips",
                "items": [
                    "ship > perfect",
                    "offer > tools",
                    "distribution > vibes",
                    "ethics > quick cash",
                ],
            },
        ],
    )

    doc.finish()
    ARTIFACT.write_bytes(OUT.read_bytes())
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path} ({path.stat().st_size} bytes)")
