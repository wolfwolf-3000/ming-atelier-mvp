#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1260
MARGIN_X = 28
TOP = 12
BOTTOM = 28
LABEL_W = 220
COL_W = (WIDTH - 2 * MARGIN_X - LABEL_W) // 4
BG = "#080604"
PANEL = "#120d07"
LINE = "#3c2c12"
GOLD = "#d8b35f"
TEXT = "#f7ead2"
MUTED = "#cdbb98"
COLORS = {
    "木": "#76b978",
    "火": "#d96b4d",
    "土": "#b89362",
    "金": "#e7a63c",
    "水": "#73a9d8",
    "default": TEXT,
}
STEM_ELEMENT = {
    "甲": "木",
    "乙": "木",
    "丙": "火",
    "丁": "火",
    "戊": "土",
    "己": "土",
    "庚": "金",
    "辛": "金",
    "壬": "水",
    "癸": "水",
}
BRANCH_ELEMENT = {
    "寅": "木",
    "卯": "木",
    "巳": "火",
    "午": "火",
    "辰": "土",
    "戌": "土",
    "丑": "土",
    "未": "土",
    "申": "金",
    "酉": "金",
    "亥": "水",
    "子": "水",
}


TEN_GOD_NORMALIZE = {
    "七": "七杀",
    "殺": "七杀",
    "七殺": "七杀",
    "偏官": "七杀",
}


def normalize_text(value: Any) -> str:
    text = str(value)
    return TEN_GOD_NORMALIZE.get(text, text)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size, index=1 if bold else 0)
        except Exception:
            continue
    return ImageFont.load_default()


FONTS = {
    "title": font(42, True),
    "label": font(36),
    "small": font(32),
    "tiny": font(28),
    "big": font(70, True),
    "shen": font(34),
}


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def draw_center(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    fnt: ImageFont.ImageFont,
    fill: str = TEXT,
    y_offset: int = 0,
) -> None:
    x1, y1, x2, y2 = box
    w, h = text_size(draw, text, fnt)
    draw.text(((x1 + x2 - w) / 2, (y1 + y2 - h) / 2 + y_offset), text, font=fnt, fill=fill)


def draw_multiline_center(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    lines: list[str],
    fnt: ImageFont.ImageFont,
    colors: list[str] | None = None,
    line_gap: int = 12,
) -> None:
    if not lines:
        return
    heights = [text_size(draw, line, fnt)[1] for line in lines]
    total_h = sum(heights) + line_gap * (len(lines) - 1)
    y = (box[1] + box[3] - total_h) / 2
    for i, line in enumerate(lines):
        fill = colors[i] if colors and i < len(colors) else TEXT
        w, h = text_size(draw, line, fnt)
        draw.text(((box[0] + box[2] - w) / 2, y), line, font=fnt, fill=fill)
        y += h + line_gap


def element_color(value: str) -> str:
    for char in value:
        if char in STEM_ELEMENT:
            return COLORS[STEM_ELEMENT[char]]
        if char in BRANCH_ELEMENT:
            return COLORS[BRANCH_ELEMENT[char]]
        if char in COLORS:
            return COLORS[char]
    return COLORS["default"]


def normalize_pillar(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "gan_shen": normalize_text(raw.get("gan_shen", "")),
        "stem": raw.get("stem", ""),
        "branch": raw.get("branch", ""),
        "hidden": raw.get("hidden", []),
        "zhi_shen": [normalize_text(item) for item in raw.get("zhi_shen", [])],
        "nayin": raw.get("nayin", ""),
        "kongwang": raw.get("kongwang", ""),
        "dishi": raw.get("dishi", ""),
        "zi_zuo": raw.get("zi_zuo", ""),
        "shen_sha": raw.get("shen_sha", []),
    }


def render(data: dict[str, Any], output: Path) -> None:
    pillars = [normalize_pillar(item) for item in data.get("pillars", [])]
    if len(pillars) != 4:
        raise ValueError("Input JSON must contain exactly four pillars.")

    row_specs = [
        ("干神", 120),
        ("天干", 120),
        ("地支", 120),
        ("藏干", 210),
        ("支神", 210),
        ("纳音", 85),
        ("空亡", 85),
        ("地势", 85),
        ("自坐", 85),
        ("神煞", 360),
    ]
    combo_lines = data.get("relations", [])
    if combo_lines:
        row_specs.append(("关系", 220))
    element_summary = data.get("element_summary", "")
    if element_summary:
        row_specs.append(("五行", 90))

    height = TOP + 80 + sum(h for _, h in row_specs) + BOTTOM
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((MARGIN_X - 10, TOP - 6, WIDTH - MARGIN_X + 10, height - BOTTOM + 12), outline=GOLD, width=3)
    draw.rectangle((MARGIN_X + 12, TOP + 12, WIDTH - MARGIN_X - 12, height - BOTTOM - 10), outline=LINE, width=2)

    headers = data.get("headers", ["年柱", "月柱", "日柱", "时柱"])
    y = TOP
    for i, header in enumerate(headers):
        x1 = MARGIN_X + LABEL_W + i * COL_W
        draw_center(draw, (x1, y, x1 + COL_W, y + 70), header, FONTS["title"], GOLD)
    y += 80

    def col_box(i: int, y1: int, row_h: int) -> tuple[int, int, int, int]:
        x1 = MARGIN_X + LABEL_W + i * COL_W
        return (x1, y1, x1 + COL_W, y1 + row_h)

    for label, row_h in row_specs:
        draw.rectangle((MARGIN_X, y, WIDTH - MARGIN_X, y + row_h), fill=PANEL if label in {"天干", "地支", "神煞"} else BG)
        draw.line((MARGIN_X, y, WIDTH - MARGIN_X, y), fill=LINE, width=2)
        draw_center(draw, (MARGIN_X, y, MARGIN_X + LABEL_W, y + row_h), label, FONTS["label"], GOLD)

        if label == "关系":
            text = "\n".join(combo_lines)
            draw.text((MARGIN_X + LABEL_W + 5, y + 40), text, font=FONTS["small"], fill=TEXT, spacing=18)
        elif label == "五行":
            parts = element_summary if isinstance(element_summary, list) else [str(element_summary)]
            x = MARGIN_X + LABEL_W + 20
            for part in parts:
                fill = element_color(part)
                draw.text((x, y + 24), part, font=FONTS["small"], fill=fill)
                x += text_size(draw, part, FONTS["small"])[0] + 55
        else:
            for i, pillar in enumerate(pillars):
                box = col_box(i, y, row_h)
                if label == "干神":
                    draw_center(draw, box, pillar["gan_shen"], FONTS["small"], element_color(pillar["gan_shen"]))
                elif label == "天干":
                    draw_center(draw, box, pillar["stem"], FONTS["big"], element_color(pillar["stem"]))
                elif label == "地支":
                    draw_center(draw, box, pillar["branch"], FONTS["big"], element_color(pillar["branch"]))
                elif label == "藏干":
                    lines = [str(item) for item in pillar["hidden"]]
                    draw_multiline_center(draw, box, lines, FONTS["tiny"], [element_color(v) for v in lines], 12)
                elif label == "支神":
                    lines = [str(item) for item in pillar["zhi_shen"]]
                    draw_multiline_center(draw, box, lines, FONTS["tiny"], [element_color(v) for v in lines], 12)
                elif label == "纳音":
                    draw_center(draw, box, pillar["nayin"], FONTS["small"], element_color(pillar["nayin"]))
                elif label == "空亡":
                    draw_center(draw, box, pillar["kongwang"], FONTS["small"], TEXT)
                elif label == "地势":
                    draw_center(draw, box, pillar["dishi"], FONTS["small"], TEXT)
                elif label == "自坐":
                    draw_center(draw, box, pillar["zi_zuo"], FONTS["small"], TEXT)
                elif label == "神煞":
                    lines = [str(item) for item in pillar["shen_sha"]]
                    draw_multiline_center(draw, box, lines, FONTS["shen"], [TEXT] * len(lines), 14)
        y += row_h

    draw.line((MARGIN_X, y, WIDTH - MARGIN_X, y), fill=LINE, width=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Bazi chart image for reports.")
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_image", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input_json.read_text(encoding="utf-8"))
    render(data, args.output_image)
    print(args.output_image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
