from __future__ import annotations

import json
import html
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from PIL import Image as PILImage, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "auto_report_app"
STATIC = APP / "static"
GENERATED = APP / "generated"
RECORDS = GENERATED / "records.jsonl"
PYTHON = Path(sys.executable)
RENDER = APP / "render_bazi_chart.py"
FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]
DEPS = ROOT / ".deps/python"
if DEPS.exists():
    sys.path.insert(0, str(DEPS))

from lunar_python import Solar  # noqa: E402
from lunar_python.util import LunarUtil  # noqa: E402


STEM_ELEMENT = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
STEM_POLARITY = {"甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳", "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴"}
BRANCH_ELEMENT = {"寅": "木", "卯": "木", "巳": "火", "午": "火", "辰": "土", "戌": "土", "丑": "土", "未": "土", "申": "金", "酉": "金", "亥": "水", "子": "水"}
HIDDEN_WEIGHT = {"巳": [("丙", 0.55), ("庚", 0.25), ("戊", 0.20)], "午": [("丁", 0.7), ("己", 0.3)], "申": [("庚", 0.55), ("壬", 0.25), ("戊", 0.20)], "酉": [("辛", 1.0)], "寅": [("甲", 0.55), ("丙", 0.25), ("戊", 0.20)], "卯": [("乙", 1.0)], "亥": [("壬", 0.7), ("甲", 0.3)], "子": [("癸", 1.0)], "辰": [("戊", 0.5), ("乙", 0.25), ("癸", 0.25)], "戌": [("戊", 0.5), ("辛", 0.25), ("丁", 0.25)], "丑": [("己", 0.5), ("癸", 0.25), ("辛", 0.25)], "未": [("己", 0.5), ("丁", 0.25), ("乙", 0.25)]}
BRANCH_NUMBER = {"子": 1, "丑": 2, "寅": 3, "卯": 4, "辰": 5, "巳": 6, "午": 7, "未": 8, "申": 9, "酉": 10, "戌": 11, "亥": 12}
LIU_HE = {"子丑": "子丑合土", "寅亥": "寅亥合木", "卯戌": "卯戌合火", "辰酉": "辰酉合金", "巳申": "巳申合水", "午未": "午未合土"}
LIU_CHONG = {"子午": "子午冲", "丑未": "丑未冲", "寅申": "寅申冲", "卯酉": "卯酉冲", "辰戌": "辰戌冲", "巳亥": "巳亥冲"}
LIU_HAI = {"子未": "子未害", "丑午": "丑午害", "寅巳": "寅巳害", "卯辰": "卯辰害", "申亥": "申亥害", "酉戌": "酉戌害"}
LIU_PO = {"子酉": "子酉破", "丑辰": "丑辰破", "寅亥": "寅亥破", "卯午": "卯午破", "巳申": "巳申破", "未戌": "未戌破"}
SAN_HE = {
    frozenset("申子辰"): "申子辰三合水局",
    frozenset("亥卯未"): "亥卯未三合木局",
    frozenset("寅午戌"): "寅午戌三合火局",
    frozenset("巳酉丑"): "巳酉丑三合金局",
}
SAN_HE_HALVES = {"申子": "申子半合水", "子辰": "子辰半合水", "亥卯": "亥卯半合木", "卯未": "卯未半合木", "寅午": "寅午半合火", "午戌": "午戌半合火", "巳酉": "巳酉半合金", "酉丑": "酉丑半合金"}
SAN_XING = {"寅巳申": "寅巳申三刑", "丑戌未": "丑戌未三刑"}
PAIR_XING = {"子卯": "子卯刑", "寅巳": "寅巳刑", "巳申": "巳申刑", "丑戌": "丑戌刑", "戌未": "戌未刑", "丑未": "丑未刑"}
SELF_XING = {"辰": "辰辰自刑", "午": "午午自刑", "酉": "酉酉自刑", "亥": "亥亥自刑"}
TIANYI = {"甲": "丑未", "戊": "丑未", "庚": "丑未", "乙": "子申", "己": "子申", "丙": "亥酉", "丁": "亥酉", "壬": "卯巳", "癸": "卯巳", "辛": "寅午"}
WENCHANG = {"甲": "巳", "乙": "午", "丙": "申", "丁": "酉", "戊": "申", "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯"}
LUSHEN = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳", "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
YANGREN = {"甲": "卯", "乙": "寅", "丙": "午", "丁": "巳", "戊": "午", "己": "巳", "庚": "酉", "辛": "申", "壬": "子", "癸": "亥"}
TAIJI = {"甲": "子午", "乙": "子午", "丙": "卯酉", "丁": "卯酉", "戊": "辰戌丑未", "己": "辰戌丑未", "庚": "寅亥", "辛": "寅亥", "壬": "巳申", "癸": "巳申"}
GUOYIN = {"甲": "戌", "乙": "亥", "丙": "丑", "丁": "寅", "戊": "丑", "己": "寅", "庚": "辰", "辛": "巳", "壬": "未", "癸": "申"}
JINYU = {"甲": "辰", "乙": "巳", "丙": "未", "丁": "申", "戊": "未", "己": "申", "庚": "戌", "辛": "亥", "壬": "丑", "癸": "寅"}
GROUP_STARS = {
    "申子辰": {"桃花": "酉", "驿马": "寅", "华盖": "辰", "将星": "子"},
    "寅午戌": {"桃花": "卯", "驿马": "申", "华盖": "戌", "将星": "午"},
    "巳酉丑": {"桃花": "午", "驿马": "亥", "华盖": "丑", "将星": "酉"},
    "亥卯未": {"桃花": "子", "驿马": "巳", "华盖": "未", "将星": "卯"},
}
TRIGRAMS = {
    1: ("乾", "天", "金", (1, 1, 1)),
    2: ("兑", "泽", "金", (1, 1, 0)),
    3: ("离", "火", "火", (1, 0, 1)),
    4: ("震", "雷", "木", (0, 0, 1)),
    5: ("巽", "风", "木", (1, 0, 0)),
    6: ("坎", "水", "水", (0, 1, 0)),
    7: ("艮", "山", "土", (0, 1, 1)),
    8: ("坤", "地", "土", (0, 0, 0)),
}
GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
GAN_HE = {"甲己": "甲己合土", "乙庚": "乙庚合金", "丙辛": "丙辛合水", "丁壬": "丁壬合木", "戊癸": "戊癸合火"}
HEXAGRAM_NAMES = {
    ("乾", "乾"): "乾为天", ("乾", "兑"): "天泽履", ("乾", "离"): "天火同人", ("乾", "震"): "天雷无妄", ("乾", "巽"): "天风姤", ("乾", "坎"): "天水讼", ("乾", "艮"): "天山遁", ("乾", "坤"): "天地否",
    ("兑", "乾"): "泽天夬", ("兑", "兑"): "兑为泽", ("兑", "离"): "泽火革", ("兑", "震"): "泽雷随", ("兑", "巽"): "泽风大过", ("兑", "坎"): "泽水困", ("兑", "艮"): "泽山咸", ("兑", "坤"): "泽地萃",
    ("离", "乾"): "火天大有", ("离", "兑"): "火泽睽", ("离", "离"): "离为火", ("离", "震"): "火雷噬嗑", ("离", "巽"): "火风鼎", ("离", "坎"): "火水未济", ("离", "艮"): "火山旅", ("离", "坤"): "火地晋",
    ("震", "乾"): "雷天大壮", ("震", "兑"): "雷泽归妹", ("震", "离"): "雷火丰", ("震", "震"): "震为雷", ("震", "巽"): "雷风恒", ("震", "坎"): "雷水解", ("震", "艮"): "雷山小过", ("震", "坤"): "雷地豫",
    ("巽", "乾"): "风天小畜", ("巽", "兑"): "风泽中孚", ("巽", "离"): "风火家人", ("巽", "震"): "风雷益", ("巽", "巽"): "巽为风", ("巽", "坎"): "风水涣", ("巽", "艮"): "风山渐", ("巽", "坤"): "风地观",
    ("坎", "乾"): "水天需", ("坎", "兑"): "水泽节", ("坎", "离"): "水火既济", ("坎", "震"): "水雷屯", ("坎", "巽"): "水风井", ("坎", "坎"): "坎为水", ("坎", "艮"): "水山蹇", ("坎", "坤"): "水地比",
    ("艮", "乾"): "山天大畜", ("艮", "兑"): "山泽损", ("艮", "离"): "山火贲", ("艮", "震"): "山雷颐", ("艮", "巽"): "山风蛊", ("艮", "坎"): "山水蒙", ("艮", "艮"): "艮为山", ("艮", "坤"): "山地剥",
    ("坤", "乾"): "地天泰", ("坤", "兑"): "地泽临", ("坤", "离"): "地火明夷", ("坤", "震"): "地雷复", ("坤", "巽"): "地风升", ("坤", "坎"): "地水师", ("坤", "艮"): "地山谦", ("坤", "坤"): "坤为地",
}


def register_font() -> str:
    for font_path in FONT_CANDIDATES:
        if not Path(font_path).exists():
            continue
        name = "MingCJK"
        if name not in pdfmetrics.getRegisteredFontNames():
            try:
                pdfmetrics.registerFont(TTFont(name, font_path))
            except Exception:
                continue
        return name
    name = "STSong-Light"
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(name))
    return name


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(str(text).replace("\n", "<br/>"), style)


def table(rows, widths, font_name, font_size=8.0, repeat=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if repeat else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d8d2c7")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eee7dc")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fbf8f2")))
    t.setStyle(TableStyle(style))
    return t


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name.strip())
    return cleaned.strip("-") or "report"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_record(record: dict) -> None:
    # MVP privacy: do not persist tester report/divination history.
    return


def read_records(limit: int = 50) -> list[dict]:
    if not RECORDS.exists():
        return []
    rows = []
    for line in RECORDS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return list(reversed(rows[-limit:]))


def element_profile(ec) -> dict[str, int]:
    score = {k: 0.0 for k in "金木水火土"}
    for prefix in ["Year", "Month", "Day", "Time"]:
        gan = getattr(ec, f"get{prefix}Gan")()
        zhi = getattr(ec, f"get{prefix}Zhi")()
        score[STEM_ELEMENT[gan]] += 1.0
        for hidden, weight in HIDDEN_WEIGHT.get(zhi, []):
            score[STEM_ELEMENT[hidden]] += weight
    total = sum(score.values()) or 1
    return {k: round(v / total * 100) for k, v in score.items()}


def branch_pair_key(a: str, b: str) -> str:
    return "".join(sorted([a, b], key=lambda item: BRANCH_NUMBER[item]))


def group_for_branch(branch: str) -> dict[str, str]:
    for group, stars in GROUP_STARS.items():
        if branch in group:
            return stars
    return {}


def unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def build_branch_relations(branches: list[str]) -> list[str]:
    full_sets = []
    half_sets = []
    pair_sets = []
    counts = {branch: branches.count(branch) for branch in set(branches)}

    branch_set = set(branches)
    for combo, label in SAN_HE.items():
        if combo.issubset(branch_set):
            full_sets.append(label)

    for raw, label in SAN_HE_HALVES.items():
        if raw[0] in branch_set and raw[1] in branch_set:
            if not any(set(raw).issubset(set(full)) for full in [label]):
                half_sets.append(label)

    for raw, label in SAN_XING.items():
        if set(raw).issubset(branch_set):
            pair_sets.append(label)

    for i, a in enumerate(branches):
        for b in branches[i + 1 :]:
            if a == b:
                continue
            key = branch_pair_key(a, b)
            for mapping in (LIU_HE, LIU_CHONG, LIU_HAI, LIU_PO, PAIR_XING):
                if key in mapping:
                    pair_sets.append(mapping[key])

    for branch, count in counts.items():
        if count > 1:
            pair_sets.append(f"{branch}{branch}伏吟")
            if branch in SELF_XING:
                pair_sets.append(SELF_XING[branch])

    relations = []
    if full_sets or half_sets:
        relations.append("地支合局：" + "；".join(unique(full_sets + half_sets)))
    if pair_sets:
        relations.append("地支冲刑害破：" + "；".join(unique(pair_sets)))
    if not relations:
        relations.append("地支关系：未见明显合冲刑害破，仍需结合大运流年触发")
    return relations


def calculate_shensha(day_stem: str, day_branch: str, branch: str, xunkong: str) -> list[str]:
    stars = []
    group_stars = group_for_branch(day_branch)
    if branch in TIANYI.get(day_stem, ""):
        stars.append("天乙贵人")
    if branch == WENCHANG.get(day_stem):
        stars.append("文昌贵人")
    if branch == LUSHEN.get(day_stem):
        stars.append("禄神")
    if branch == YANGREN.get(day_stem):
        stars.append("羊刃")
    if branch in TAIJI.get(day_stem, ""):
        stars.append("太极贵人")
    if branch == GUOYIN.get(day_stem):
        stars.append("国印")
    if branch == JINYU.get(day_stem):
        stars.append("金舆")
    for star_name, star_branch in group_stars.items():
        if branch == star_branch:
            stars.append(star_name)
    if branch in xunkong:
        stars.append("空亡")
    return unique(stars)


def free_report_summary(data: dict, computed: dict) -> str:
    ec = computed["ec"]
    profile = computed["profile"]
    day_stem = ec.getDayGan()
    day_element = STEM_ELEMENT.get(day_stem, "")
    dominant = sorted(profile.items(), key=lambda item: item[1], reverse=True)[:2]
    dominant_text = "、".join(f"{k}{v}%" for k, v in dominant)
    industry = data.get("industry") or data.get("role") or "尚未填写具体行业"
    role = data.get("role") or "当前角色未填"
    gender = data.get("gender", "")
    spouse_logic = "财星" if gender == "男" else "官杀"
    if day_element in {"金", "水"}:
        personality = "思考偏理性，重效率、信息、规则和边界，适合把复杂问题拆成流程。"
        industries = "数据分析、金融风控、供应链、跨境贸易、运营管理、咨询、技术产品、研究型岗位。"
    elif day_element in {"木", "火"}:
        personality = "表达和成长动能更明显，容易被目标、作品、曝光和人与人的互动推动。"
        industries = "教育培训、内容传播、品牌营销、产品增长、设计创意、管理培训、咨询服务。"
    else:
        personality = "稳定性和承接力较强，重现实结果、资源整合和长期积累。"
        industries = "地产空间、项目管理、供应链、财务运营、人力行政、组织管理、传统行业升级。"
    return (
        f"大白话看，这个命盘的日主是{day_stem}{day_element}，五行里目前以{dominant_text}最显眼，所以性格上不是单纯外放或单纯内向，"
        f"而是会先看事情有没有结构、有没有确定性，再决定要不要投入。{personality}"
        f"事业上，你当前填写的行业/角色是“{industry} / {role}”，从五行气质看，比较适合往{industries}"
        f"如果要做得更顺，关键不是追热点，而是把自己的专业、流程、交付标准和现金流规则固定下来。"
        f"感情上，{gender or '此盘'}看{spouse_logic}与日支状态，关系里最需要的是边界、节奏和现实责任感；"
        "如果一段关系长期让你在钱、时间、承诺或城市选择上反复消耗，就不适合硬拖。"
        "免费版只做排盘后的基础阅读，不展开大运、流年、正缘年份和深度风险细断。"
    )


def normalize_time(value: str) -> str:
    match = re.search(r"(\d{1,2}):(\d{2})", str(value or ""))
    if not match:
        raise ValueError("时间格式请填写为 HH:MM")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("时间格式请填写为 HH:MM")
    return f"{hour:02d}:{minute:02d}"


def build_chart(data: dict, run_id: str) -> tuple[dict, Path]:
    data["birthTime"] = normalize_time(data["birthTime"])
    birth = datetime.fromisoformat(data["birthDate"] + "T" + data["birthTime"])
    solar = Solar.fromYmdHms(birth.year, birth.month, birth.day, birth.hour, birth.minute, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    day_stem = ec.getDayGan()
    day_branch = ec.getDayZhi()
    pillars = []
    for prefix in ["Year", "Month", "Day", "Time"]:
        hidden = getattr(ec, f"get{prefix}HideGan")()
        shen = getattr(ec, f"get{prefix}ShiShenZhi")()
        branch = getattr(ec, f"get{prefix}Zhi")()
        xunkong = getattr(ec, f"get{prefix}XunKong")()
        pillars.append(
            {
                "gan_shen": getattr(ec, f"get{prefix}ShiShenGan")(),
                "stem": getattr(ec, f"get{prefix}Gan")(),
                "branch": branch,
                "hidden": [f"{g}·{STEM_ELEMENT.get(g, '')}" for g in hidden],
                "zhi_shen": shen,
                "nayin": getattr(ec, f"get{prefix}NaYin")(),
                "kongwang": xunkong,
                "dishi": getattr(ec, f"get{prefix}DiShi")(),
                "zi_zuo": getattr(ec, f"get{prefix}DiShi")(),
                "shen_sha": calculate_shensha(day_stem, day_branch, branch, xunkong),
            }
        )
    pillars[2]["gan_shen"] = "日主"
    branches = [pillar["branch"] for pillar in pillars]
    chart = {
        "headers": ["年柱", "月柱", "日柱", "时柱"],
        "pillars": pillars,
        "relations": build_branch_relations(branches),
        "element_summary": [f"{k}{v}%" for k, v in element_profile(ec).items()],
    }
    chart_json = GENERATED / f"{run_id}-chart.json"
    chart_png = GENERATED / f"{run_id}-chart.png"
    chart_json.write_text(json.dumps(chart, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run([str(PYTHON), str(RENDER), str(chart_json), str(chart_png)], check=True)
    return {"solar": solar, "lunar": lunar, "ec": ec, "profile": element_profile(ec), "chart": chart}, chart_png


def current_dayun(ec, gender: str, target_year: int = 2026):
    gender_code = 1 if gender == "男" else 0
    yun = ec.getYun(gender_code)
    selected = None
    rows = []
    for dy in yun.getDaYun():
        if not dy.getGanZhi():
            continue
        rows.append([dy.getGanZhi(), f"{dy.getStartYear()}-{dy.getEndYear()}", f"{dy.getStartAge()}-{dy.getEndAge()}岁"])
        if dy.getStartYear() <= target_year <= dy.getEndYear():
            selected = dy
    return yun, selected, rows[:6]


def trigram_index_from_lines(lines: tuple[int, int, int]) -> int:
    for index, item in TRIGRAMS.items():
        if item[3] == lines:
            return index
    return 8


def hexagram_name(upper_index: int, lower_index: int) -> str:
    upper = TRIGRAMS[upper_index][0]
    lower = TRIGRAMS[lower_index][0]
    return HEXAGRAM_NAMES.get((upper, lower), f"{upper}{lower}卦")


def element_relation(body_element: str, use_element: str) -> tuple[str, int, str]:
    if body_element == use_element:
        return "体用同气", 8, "内在状态和外部事情同频，推进阻力较小，但也容易停在原有节奏里。"
    if GENERATES.get(use_element) == body_element:
        return "用生体", 14, "外部条件来生扶自己，事情容易得到资源、回应或贵人助力。"
    if GENERATES.get(body_element) == use_element:
        return "体生用", -8, "自己要付出更多去托举事情，容易先耗精力、时间或情绪。"
    if CONTROLS.get(body_element) == use_element:
        return "体克用", 4, "自己能压住局面，但要靠主动争取、规则和执行力，不能等对方自然配合。"
    if CONTROLS.get(use_element) == body_element:
        return "用克体", -16, "外部条件对自己形成压力，容易遇到卡点、反复、拖延或对方强势。"
    return "体用关系混杂", -2, "卦气不算顺直，需要结合现实进展判断，不宜只凭感觉推进。"


def support_score(element: str, month_element: str, day_element: str) -> int:
    score = 0
    if month_element == element:
        score += 7
    elif GENERATES.get(month_element) == element:
        score += 4
    elif CONTROLS.get(month_element) == element:
        score -= 6
    if day_element == element:
        score += 5
    elif GENERATES.get(day_element) == element:
        score += 3
    elif CONTROLS.get(day_element) == element:
        score -= 4
    return score


def moving_line_reading(line: int) -> tuple[str, int, str]:
    if line in (1, 2):
        return "初段", 4, "事情还在起势阶段，先看信息是否补齐、对方是否回应，不宜急着定终局。"
    if line in (3, 4):
        return "中段", -6, "事情进入拉扯区，变数最大，容易因为沟通、条件或节奏出现反复。"
    return "后段", -2, "事情已经有明显走势，后续更看收尾、承诺兑现和现实条件能否落地。"


def verdict_from_score(score: int) -> tuple[str, str, str]:
    if score >= 72:
        return "吉", "顺势可进", "整体卦气偏顺，适合主动推进，但仍要把承诺、时间和边界落到具体动作。"
    if score >= 60:
        return "小吉", "可进但要控节奏", "有推进空间，但不是无条件顺利，需要先处理关键阻力。"
    if score >= 48:
        return "平", "谨慎观察", "事情未到定局，短期适合试探、补信息、留后手，不宜重押。"
    return "凶", "暂缓为宜", "阻力较明显，当前不适合硬推；若必须推进，应先降风险、缩小投入。"


def divination_topic(question: str, background: str) -> str:
    text = question + " " + background
    topics = [
        ("合作/副业", ["合作", "合伙", "副业", "项目", "客户", "合同", "报价", "资源", "推进"]),
        ("感情/关系", ["感情", "恋爱", "复合", "分手", "结婚", "对象", "关系", "伴侣"]),
        ("事业/工作", ["工作", "跳槽", "面试", "升职", "老板", "公司", "事业", "职业"]),
        ("财务/投资", ["投资", "买", "卖", "钱", "收入", "财", "股票", "房", "资产"]),
        ("学业/考试", ["考试", "申请", "学校", "学业", "录取", "论文", "证书"]),
    ]
    for label, words in topics:
        if any(word in text for word in words):
            return label
    return "具体事项"


def divination_contextual_reading(topic: str, question: str, background: str, verdict: str, relation: str, phase: str) -> tuple[str, list[str], list[str]]:
    relation_hint = {
        "用生体": "外部条件有助力，但助力是否能落地，取决于对方承诺是否具体。",
        "体生用": "你会比较主动付出资源和精力，容易先投入、后等回报。",
        "体克用": "你有主动掌控空间，但也容易因为控制太急而让对方退缩。",
        "用克体": "外部压力压到自己身上，推进时要先判断成本是否已经超过收益。",
        "同气": "双方节奏相近，成败更取决于细节、时机和执行纪律。",
    }.get(relation, "卦象提示要把抽象判断落到具体条件。")
    phase_hint = {
        "初段": "事情还在起势阶段，先验证对方态度，不宜一上来绑定大承诺。",
        "中段": "事情正在拉扯，最关键的是谈清条件和权责，不要靠默契推进。",
        "后段": "事情已经接近见结果，重点是收口、验收、付款、期限和退出条件。",
    }.get(phase, "当前要把节奏拆成可验证节点。")
    if topic == "合作/副业":
        reading = f"这卦要落回你问的合作/副业本身看：{relation_hint}{phase_hint} 所以不是简单问“能不能做”，而是要先看合同边界、分工、收款、交付和退出条件。若这些条件能写清，{verdict}可以转成可控推进；若对方只给资源想象、不肯给具体承诺，就算卦面不差，也容易变成你单方面消耗。"
        advice = ["先要一版书面合作范围：谁负责什么、何时交付、如何分账。", "先做小单或试运行，不要一开始押长期排他或大额投入。", "把退出条件写在前面：对方逾期、付款不清、范围扩大时如何停止。"]
        risks = ["最怕“资源很多但边界很虚”，最后变成你补交付、补沟通、补成本。", "如果对方回避合同、账期或责任人，说明卦里的阻力已经在现实中出现。", "涉及大额资金或股权时，必须用合同和专业意见复核。"]
    elif topic == "感情/关系":
        reading = f"这卦落在感情/关系上，核心不是只看对方有没有感觉，而是看关系能否进入稳定承诺。{relation_hint}{phase_hint} 若对方愿意把时间安排、关系名分、金钱边界和未来计划讲清楚，事情还有推进空间；若一直停在情绪拉扯，短期不要用牺牲自己来换确定性。"
        advice = ["先问清一个现实问题：关系定位、见面频率或下一步安排。", "不要在情绪最满的时候逼承诺，给对方一个具体反馈期限。", "如果对方只给暧昧回应，不给行动，就按低投入处理。"]
        risks = ["高情绪沟通容易让问题失焦。", "不要把金钱、同居、城市选择和关系承诺混在一起一次谈完。", "若涉及安全、控制或伤害，优先现实求助，不以卦象判断。"]
    elif topic == "事业/工作":
        reading = f"这卦落在事业/工作上，重点是机会背后的制度与成本。{relation_hint}{phase_hint} 如果岗位、汇报线、薪酬、绩效口径清楚，可以小步推进；如果只是口头机会很大，但权责不清，后期压力会落到你身上。"
        advice = ["把薪酬、职责、考核和资源支持问清楚。", "先争取试用节点或阶段性目标，不要只凭热情接盘。", "保留现有现金流和备选方案。"]
        risks = ["口头承诺和实际资源不匹配。", "上级或客户临时改需求，导致你承担额外成本。", "职业重大选择仍需结合现实 offer 和长期规划。"]
    elif topic == "财务/投资":
        reading = f"这卦落在财务/投资上，要先看风险暴露，而不是只看收益想象。{relation_hint}{phase_hint} 当前更适合小额验证、分批进入或先做尽调，不适合因为一时机会感而重仓。"
        advice = ["先设最大亏损线，不到条件不加码。", "确认流动性、退出方式和最坏情况。", "任何高收益承诺都要反向验证风险。"]
        risks = ["不要把卦象当投资建议或收益保证。", "高杠杆、借钱投入、短线追涨都应回避。", "重大金额必须做专业财务和法律核查。"]
    else:
        reading = f"这卦需要贴着你的问题看：{relation_hint}{phase_hint} 当前最重要的不是抽象判断吉凶，而是把问题拆成一个可验证动作，看对方/环境是否给出明确反馈。"
        advice = ["把问题缩小成一个具体动作和一个明确期限。", "先验证信息，再扩大投入。", "保留退出条件，不要把所有选择押在一次判断上。"]
        risks = ["问题越模糊，卦象可用度越低。", "现实反馈和卦象不一致时，以现实证据为先。", "重大事项需要专业意见和更多信息。"]
    return reading, advice, risks


def build_divination(data: dict) -> dict:
    question = data.get("question", "").strip()
    if not question:
        raise ValueError("请填写要问的具体事情")
    if data.get("divinationDate") and data.get("divinationTime"):
        data["divinationTime"] = normalize_time(data["divinationTime"])
        divination_time = datetime.fromisoformat(data["divinationDate"] + "T" + data["divinationTime"])
    else:
        divination_time = datetime.now()
    solar = Solar.fromYmdHms(divination_time.year, divination_time.month, divination_time.day, divination_time.hour, divination_time.minute, divination_time.second)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    year_branch = ec.getYearZhi()
    hour_branch = ec.getTimeZhi()
    year_num = BRANCH_NUMBER[year_branch]
    hour_num = BRANCH_NUMBER[hour_branch]
    lunar_month = lunar.getMonth()
    lunar_day = lunar.getDay()
    upper_index = (year_num + lunar_month + lunar_day) % 8 or 8
    lower_index = (year_num + lunar_month + lunar_day + hour_num) % 8 or 8
    moving_line = (year_num + lunar_month + lunar_day + hour_num) % 6 or 6
    lines = list(TRIGRAMS[lower_index][3] + TRIGRAMS[upper_index][3])
    changed = lines[:]
    changed[moving_line - 1] = 0 if changed[moving_line - 1] else 1
    changed_lower = trigram_index_from_lines(tuple(changed[:3]))
    changed_upper = trigram_index_from_lines(tuple(changed[3:]))
    mutual_lower = trigram_index_from_lines(tuple(lines[1:4]))
    mutual_upper = trigram_index_from_lines(tuple(lines[2:5]))
    body_element = TRIGRAMS[upper_index][2]
    use_element = TRIGRAMS[lower_index][2]
    month_element = BRANCH_ELEMENT.get(ec.getMonthZhi(), "")
    day_element = BRANCH_ELEMENT.get(ec.getDayZhi(), "")
    relation, relation_score, relation_text = element_relation(body_element, use_element)
    phase, phase_score, phase_text = moving_line_reading(moving_line)
    body_score = support_score(body_element, month_element, day_element)
    use_score = support_score(use_element, month_element, day_element)
    success = max(28, min(86, 58 + relation_score + body_score - max(0, use_score - body_score) // 2 + phase_score))
    risk = 5 + (2 if success < 48 else 0) + (1 if moving_line in (3, 4) else 0) + (1 if relation == "用克体" else 0) - (1 if success >= 68 else 0)
    risk = max(2, min(9, risk))
    verdict, verdict_tone, verdict_text = verdict_from_score(success)
    confidence = 58
    confidence += 4 if data.get("location", "").strip() else -4
    confidence += 3 if data.get("background", "").strip() else -4
    confidence += 3 if data.get("omen", "").strip() else -2
    confidence = max(45, min(72, confidence))
    action_window = {
        "初段": "先用 24-72 小时观察回应；若反馈顺，再推进下一步。",
        "中段": "未来 3-14 天是关键拉扯期，适合谈条件、补材料、看对方态度。",
        "后段": "未来 7-30 天看落地结果，重点放在确认、收尾和防反复。",
    }[phase]
    background = data.get("background", "").strip()
    topic = divination_topic(question, background)
    question_reading, advice, risk_points = divination_contextual_reading(topic, question, background, verdict, relation, phase)
    return {
        "question": question,
        "time": divination_time.strftime("%Y-%m-%d %H:%M"),
        "location": data.get("location", "").strip() or "未填，按当前本地时间起卦",
        "background": background or "未填",
        "topic": topic,
        "omen": data.get("omen", "").strip() or "无",
        "baseHexagram": hexagram_name(upper_index, lower_index),
        "mutualHexagram": hexagram_name(mutual_upper, mutual_lower),
        "changedHexagram": hexagram_name(changed_upper, changed_lower),
        "movingLine": moving_line,
        "phase": phase,
        "body": f"{TRIGRAMS[upper_index][0]}卦（{body_element}）",
        "use": f"{TRIGRAMS[lower_index][0]}卦（{use_element}）",
        "relation": relation,
        "relationText": relation_text,
        "seasonText": f"月令偏{month_element or '未明'}，日辰偏{day_element or '未明'}；体卦得分 {body_score:+d}，用卦得分 {use_score:+d}。",
        "movementText": phase_text,
        "verdict": verdict,
        "verdictTone": verdict_tone,
        "verdictText": verdict_text,
        "success": f"{success}%",
        "risk": f"{risk}/10",
        "confidence": f"{confidence}%",
        "actionWindow": action_window,
        "questionReading": question_reading,
        "advice": advice,
        "riskPoints": risk_points,
        "summary": f"此卦判断为「{verdict}」，倾向是「{verdict_tone}」。对应你问的“{question}”，结论不是抽象吉凶，而是：{question_reading}",
    }


def report_pdf(data: dict, computed: dict, chart_png: Path, output: Path) -> None:
    font = register_font()
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("title", parent=base["Title"], fontName=font, fontSize=22, leading=30, alignment=1, wordWrap="CJK"),
        "sub": ParagraphStyle("sub", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=14, alignment=1, textColor=colors.HexColor("#666666"), wordWrap="CJK"),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=font, fontSize=14.5, leading=21, spaceBefore=12, spaceAfter=8, wordWrap="CJK"),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=font, fontSize=12, leading=18, spaceBefore=8, spaceAfter=5, wordWrap="CJK"),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=font, fontSize=9, leading=14, spaceAfter=5, wordWrap="CJK"),
        "note": ParagraphStyle("note", parent=base["BodyText"], fontName=font, fontSize=8.2, leading=12, backColor=colors.HexColor("#fff6df"), borderColor=colors.HexColor("#ead69d"), borderWidth=0.4, borderPadding=6, textColor=colors.HexColor("#6d541d"), wordWrap="CJK"),
    }
    ec = computed["ec"]
    yun, selected, dayun_rows = current_dayun(ec, data.get("gender", "男"))
    pillars = f"{ec.getYear()} 年｜{ec.getMonth()} 月｜{ec.getDay()} 日｜{ec.getTime()} 时"
    profile = computed["profile"]
    summary = free_report_summary(data, computed)
    story = [
        paragraph(f"{data.get('name') or '匿名'} 免费排盘报告", styles["title"]),
        paragraph(f"{data.get('calendar', '阳历')} {data.get('birthDate')} {data.get('birthTime')}｜{data.get('birthPlace', '')}｜{data.get('gender', '')}｜金额单位：人民币 RMB", styles["sub"]),
        Spacer(1, 8),
        paragraph("免费版说明：本报告只做排盘和一段基础大白话总结。命盘图保留神煞与地支关系，正文不展开深度格局、大运、流年和风险细断。", styles["note"]),
        Spacer(1, 8),
        Image(str(chart_png), width=135 * mm, height=205 * mm),
        PageBreak(),
        paragraph("一、原始盘信息", styles["h1"]),
        table([["项目", "内容"], ["四柱", pillars], ["日主", ec.getDayGan()], ["当前/2026大运", selected.getGanZhi() if selected else "未识别"], ["五行估计", "，".join(f"{k}{v}%" for k, v in profile.items())]], [34 * mm, 136 * mm], font),
        paragraph("二、大白话总结", styles["h1"]),
        paragraph(summary, styles["body"]),
    ]
    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    doc.build(story)


TEN_GOD_TEXT = {
    "比肩": "自我、同辈、独立和竞争意识。",
    "劫财": "抢机会、分利、合伙、人际竞争和现金流波动。",
    "食神": "稳定输出、表达、产品、服务体验和长期口碑。",
    "伤官": "突破规则、表达锋芒、创新、销售和挑战权威。",
    "正财": "稳定现金流、客户、交易、现实资源和伴侣星。",
    "偏财": "机会财、项目财、资源整合、市场嗅觉和投资倾向。",
    "正官": "规则、职位、责任、名分、长期秩序和伴侣星。",
    "七杀": "压力、竞争、速度、外部约束、风险和执行力。",
    "正印": "学习、资质、保护、长辈、系统支持和恢复力。",
    "偏印": "洞察、模型、非标知识、研究、灵感和孤独感。",
}
SHENSHA_TEXT = {
    "天乙贵人": "强贵人星，指关键人物、机构、专业人士或保护性资源。",
    "天德贵人": "德星缓冲，能降低冲突后果，但不能取消风险。",
    "月德贵人": "柔性贵人，偏修复、转圜和减损。",
    "文昌贵人": "文书、学习、合同、表达、考试和专业沟通。",
    "学堂": "正式学习、训练、资质和可被验证的专业能力。",
    "国印": "制度、权责、平台、资质、官方流程和正式身份。",
    "福星贵人": "资源缓冲、顺手感、福气和生活支持。",
    "太极贵人": "抽象思维、系统研究、玄学/哲学、模式识别。",
    "将星": "主导、统筹、管理、号令和执行。",
    "十灵日": "敏感、直觉、快速感知、表达或创造性灵气。",
    "羊刃": "竞争、锋芒、执行、冲突和伤损倾向，需要规则约束。",
    "禄神": "稳定收入、岗位资源、技能底盘和可持续供养。",
    "驿马": "迁移、出行、跨境、物流、市场流动和业务扩展。",
    "华盖": "研究、艺术、玄学、审美、独处和专业深度。",
    "金舆": "车辆、舒适、资源支持、体面感和生活质量。",
    "空亡": "虚、迟、落空、兑现折扣和不稳定。",
    "灾煞": "阻滞、突发问题、外部干扰和风险提示。",
    "童子": "敏感、疏离、非主流偏好或关系节奏特殊，需保守解读。",
}
PILLAR_LABELS = ["年柱", "月柱", "日柱", "时柱"]
PILLAR_MEANING = {
    "年柱": "外部环境、早年、家族背景、社会圈层和远端资源。",
    "月柱": "事业底层、现实赛道、父母/上级、职业环境和执行场。",
    "日柱": "自我、伴侣宫、亲密关系、贴身资源和个人决策。",
    "时柱": "长期规划、子女/下属、副业、晚期发展和未来项目。",
}
TEN_GOD_GROUP = {
    "比肩": "peer",
    "劫财": "peer",
    "食神": "output",
    "伤官": "output",
    "正财": "wealth",
    "偏财": "wealth",
    "正官": "officer",
    "七杀": "officer",
    "正印": "resource",
    "偏印": "resource",
}
GROUP_LABEL = {
    "peer": "比劫",
    "output": "食伤",
    "wealth": "财星",
    "officer": "官杀",
    "resource": "印星",
}
GROUP_BEHAVIOR = {
    "peer": "自我、同辈、竞争、合伙与分利",
    "output": "表达、作品、销售、技术输出与产品化",
    "wealth": "客户、现金流、定价、资源整合与现实交易",
    "officer": "规则、岗位、压力、合规、名分与责任",
    "resource": "学习、资质、方法论、贵人、系统支持与恢复",
}
GANZHI_2026_2036 = ["丙午", "丁未", "戊申", "己酉", "庚戌", "辛亥", "壬子", "癸丑", "甲寅", "乙卯", "丙辰"]
MONTHS_2026 = [
    ("2026-02", "庚寅", "立春-惊蛰"),
    ("2026-03", "辛卯", "惊蛰-清明"),
    ("2026-04", "壬辰", "清明-立夏"),
    ("2026-05", "癸巳", "立夏-芒种"),
    ("2026-06", "甲午", "芒种-小暑"),
    ("2026-07", "乙未", "小暑-立秋"),
    ("2026-08", "丙申", "立秋-白露"),
    ("2026-09", "丁酉", "白露-寒露"),
    ("2026-10", "戊戌", "寒露-立冬"),
    ("2026-11", "己亥", "立冬-大雪"),
    ("2026-12", "庚子", "大雪-小寒"),
    ("2027-01", "辛丑", "小寒-立春"),
]
SEASON_STRENGTH = {
    "木": {"寅": 30, "卯": 30, "亥": 16, "子": 12, "辰": 5, "未": 3, "巳": -14, "午": -18, "申": -32, "酉": -34, "戌": -12, "丑": -10},
    "火": {"巳": 30, "午": 30, "寅": 16, "卯": 12, "未": 8, "戌": 5, "申": -12, "酉": -14, "亥": -32, "子": -34, "辰": -8, "丑": -12},
    "土": {"辰": 24, "戌": 24, "丑": 20, "未": 24, "巳": 16, "午": 18, "申": 4, "酉": 2, "寅": -18, "卯": -20, "亥": -14, "子": -16},
    "金": {"申": 32, "酉": 34, "辰": 14, "戌": 16, "丑": 12, "未": 10, "亥": 6, "子": 4, "寅": -18, "卯": -20, "巳": -16, "午": -20},
    "水": {"亥": 32, "子": 34, "申": 18, "酉": 14, "辰": 10, "丑": 8, "寅": -10, "卯": -12, "巳": -28, "午": -30, "未": -12, "戌": -10},
}


def element_for_group(day_element: str, group: str) -> str:
    parent = next((k for k, v in GENERATES.items() if v == day_element), "")
    return {
        "peer": day_element,
        "resource": parent,
        "output": GENERATES.get(day_element, ""),
        "wealth": CONTROLS.get(day_element, ""),
        "officer": next((k for k, v in CONTROLS.items() if v == day_element), ""),
    }.get(group, "")


def group_for_element(day_element: str, element: str) -> str:
    for group in ("peer", "resource", "output", "wealth", "officer"):
        if element_for_group(day_element, group) == element:
            return group
    return "other"


def day_master_diagnostics(ec, profile: dict | None = None) -> dict:
    day_stem = ec.getDayGan()
    day_element = STEM_ELEMENT.get(day_stem, "")
    month_branch = ec.getMonthZhi()
    score = 50.0 + SEASON_STRENGTH.get(day_element, {}).get(month_branch, 0)
    support = 0.0
    pressure = 0.0
    sources = []
    branches = [ec.getYearZhi(), ec.getMonthZhi(), ec.getDayZhi(), ec.getTimeZhi()]
    stems = [ec.getYearGan(), ec.getMonthGan(), ec.getTimeGan()]
    stem_weight = {"peer": 8, "resource": 8, "output": -4, "wealth": -6, "officer": -8}
    hidden_weight = {"peer": 16, "resource": 12, "output": -5, "wealth": -7, "officer": -9}

    for stem in stems:
        group = group_for_ten_god(ten_god_for(day_stem, stem))
        delta = stem_weight.get(group, 0)
        score += delta
        if delta > 0:
            support += delta
        elif delta < 0:
            pressure += abs(delta)
        if group in GROUP_LABEL:
            sources.append(f"天干{stem}{GROUP_LABEL[group]}{'扶身' if delta > 0 else '耗压' if delta < 0 else '中性'}")

    for index, branch in enumerate(branches):
        multiplier = 1.75 if index == 1 else (1.15 if index == 2 else 1.0)
        for hidden, weight in HIDDEN_WEIGHT.get(branch, []):
            group = group_for_ten_god(ten_god_for(day_stem, hidden))
            delta = hidden_weight.get(group, 0) * weight * multiplier
            score += delta
            if delta > 0:
                support += delta
            elif delta < 0:
                pressure += abs(delta)

    score = round(max(18, min(82, score)))
    if score >= 62:
        label = "身强"
        useful_groups = ["output", "wealth"]
    elif score <= 45:
        label = "身弱"
        useful_groups = ["resource", "peer"]
    else:
        label = "中和"
        useful_groups = ["output", "wealth"] if pressure < support else ["resource", "output"]

    useful = unique([element_for_group(day_element, group) for group in useful_groups if element_for_group(day_element, group)])[:2]
    season_note = f"月令{month_branch}{BRANCH_ELEMENT.get(month_branch, '')}对{day_stem}{day_element}的季节分为{SEASON_STRENGTH.get(day_element, {}).get(month_branch, 0)}"
    return {
        "label": label,
        "strength": score,
        "useful": useful,
        "useful_groups": useful_groups,
        "support": round(support),
        "pressure": round(pressure),
        "season_note": season_note,
        "source_note": "；".join(sources[:4]) or "以月令、藏干和透干综合评估",
    }


def day_master_assessment(ec, profile: dict) -> tuple[str, int, str, str]:
    diag = day_master_diagnostics(ec, profile)
    day_stem = ec.getDayGan()
    day_element = STEM_ELEMENT.get(day_stem, "")
    useful_text = "、".join(diag["useful"]) or "节奏"
    if diag["label"] == "身弱":
        useful = f"宜先取{useful_text}，以印比补根、稳专业、稳支持系统；不能按五行缺失机械补财官食伤。"
    elif diag["label"] == "身强":
        useful = f"宜用{useful_text}泄化承接，把行动力转成产品、现金流和规则；仍要看大运流年是否触发合冲刑害。"
    else:
        useful = f"宜围绕{useful_text}做调候、通关和节奏控制；旺时泄化，弱时补资源。"
    reason = f"日主{day_stem}{day_element}，{diag['season_note']}；扶身约{diag['support']}点，耗压约{diag['pressure']}点。{diag['source_note']}。"
    return diag["label"], diag["strength"], useful, reason


def useful_elements(ec, profile: dict) -> list[str]:
    return day_master_diagnostics(ec, profile)["useful"]


def element_behavior(element: str) -> str:
    return {
        "金": "边界、合同、定价、财务、审计、复盘和资产化。",
        "水": "规则、冷静、流动、沟通、数据、压力管理和跨境/流通。",
        "木": "学习、生长、内容、教育、产品迭代、长期主义和人脉生发。",
        "火": "表达、曝光、品牌、销售、速度、热情和公众影响力。",
        "土": "承接、流程、库存、组织、风控、信用和长期稳定。",
    }.get(element, "节奏、边界和现实校准。")


def crystal_rows(elements: list[str]) -> list[list[str]]:
    mapping = {
        "金": ["白水晶 / 白幽灵", "清晰、定价、合同、复盘与资产意识", "放在工作台或合同/账本附近，作为做决策前先算账的提醒。"],
        "水": ["黑曜石 / 海蓝宝", "降火、稳情绪、沟通、边界和压力管理", "适合出门谈判或高压沟通时佩戴，提醒自己慢半拍再答应。"],
        "木": ["绿幽灵 / 东陵玉", "学习、生长、作品、长期计划和恢复力", "适合放在学习区或项目规划区，提醒持续迭代而不是急于求成。"],
        "火": ["红玛瑙 / 石榴石", "表达、曝光、行动力、销售和热启动", "适合在需要展示、面试、发布和表达时使用，避免过度亢奋。"],
        "土": ["黄水晶 / 虎眼石", "承接、组织、现金流、库存和现实落地", "适合放在财务/库存/项目管理区，提醒先有规则再扩张。"],
    }
    return [[e] + mapping.get(e, ["白水晶", "清晰与稳定", "作为行动锚点使用。"]) for e in elements]


def ten_god_rows(computed: dict) -> list[list[str]]:
    rows = []
    for label, pillar in zip(PILLAR_LABELS, computed["chart"]["pillars"]):
        meaning = PILLAR_MEANING[label].rstrip("。")
        rows.append([
            pillar["gan_shen"] or "日主",
            f"{label}天干 {pillar['stem']}",
            TEN_GOD_TEXT.get(pillar["gan_shen"], "日主自身、行动中枢和判断核心。"),
            f"{pillar['stem']}落{label}，影响{meaning}。此处结论置信度约70%，需结合月令和大运修正。",
        ])
        for hidden, shen in zip(pillar.get("hidden", []), pillar.get("zhi_shen", [])):
            rows.append([
                shen,
                f"{label}地支 {pillar['branch']}藏{hidden.split('·')[0]}",
                TEN_GOD_TEXT.get(shen, "藏干提供支撑、潜在动机和暗线资源。"),
                f"{shen}藏于{pillar['branch']}，不是外显资源，更像{meaning}里的潜在驱动力；置信度约66%。",
            ])
    return rows


def shensha_rows(computed: dict) -> dict[str, list[list[str]]]:
    result = {}
    for index, (label, pillar) in enumerate(zip(PILLAR_LABELS, computed["chart"]["pillars"])):
        rows = []
        stars = pillar.get("shen_sha") or ["无明显主星"]
        for pos, star in enumerate(stars, 1):
            meaning = PILLAR_MEANING[label].rstrip("。")
            base = 7 if label in {"月柱", "日柱"} else 5
            if star in {"羊刃", "天乙贵人", "文昌贵人", "国印"}:
                base += 1
            if star == "空亡":
                base -= 1
            strength = max(3, min(9, base - pos // 4))
            rows.append([
                str(pos),
                star,
                f"{strength}/10",
                SHENSHA_TEXT.get(star, "该神煞作为辅助信号，需结合十神、地支关系和大运判断。"),
                f"在{label}主要影响{meaning}；本盘中不单独定吉凶，只作结构修正。",
            ])
        result[label] = rows
    return result


def branch_relation_rows(computed: dict) -> list[list[str]]:
    relations = computed["chart"].get("relations") or ["无明显合冲刑害破"]
    rows = []
    for relation in relations:
        rows.append([
            relation,
            "提示盘面内部存在互动，不是单柱孤立判断。",
            "会影响事业节奏、关系稳定、财富承接或情绪波动，需结合大运流年触发。",
            "用合同、账期、复盘、沟通边界和退出条件做现实制化。",
        ])
    return rows


def wealth_tone(strength: int, useful: list[str], ec, profile: dict, context: dict | None = None) -> dict[str, str]:
    day_stem = ec.getDayGan()
    day_element = STEM_ELEMENT.get(day_stem, "")
    useful_text = "、".join(useful) or "节奏"
    strong_element = max(profile, key=profile.get)
    flags = {flag["key"] for flag in (context or {}).get("risk_flags", [])}
    if "weak_officer" in flags:
        return {
            "base": f"这张盘的财运不能按“缺什么补什么”处理。日主{day_stem}{day_element}承压时，钱不是越刺激越来，先要用{useful_text}稳住专业、信息、规则和支持系统；真正能赚钱的窗口，是先用输出破局，再用合同和现金流纪律收口。",
            "million": f"百万级来自轻资产、技术/认知/内容/咨询/产品化变现，先用{useful_text}把专业壁垒和交付边界立住。",
            "five": "500万级必须有法务、账期、交付团队和客户归属规则，不能靠朋友情怀或口头分成放大。",
            "ten": "千万级只适合在平台、渠道、合同、财务隔离都成熟后尝试；未做主权和资产隔离前不宜重资产押注。",
        }
    if "peer_wealth" in flags or "peer_wealth_combo" in flags:
        return {
            "base": f"这张盘的钱有机会做出来，但败点也常在“朋友、合伙、分利、退出”。喜用{useful_text}要落成冷静风控、契约主权和现金隔离，而不是只谈增长故事。",
            "million": "百万级可以靠项目、客户、产品化和高客单价打开，但一开始就要写清客户归属、收款账户、分账比例和退出条款。",
            "five": "500万级看组织和制度，不看单人冲劲；没有股权、税务、财务和交付主权时，规模越大纠纷越大。",
            "ten": "千万级不是不能看，但必须先做到资产隔离、合同死锁、团队分权和现金流审计。",
        }
    if "金" in useful or "水" in useful:
        return {
            "base": f"这张盘搞钱不适合靠一时热度硬冲，更适合把{useful_text}落成定价、合同、复盘、账期和客户筛选。金水到位时，钱往往来自专业判断、信息差、规则能力和长期客户。",
            "million": f"百万级更像主线盘：日主{day_stem}{day_element}需要先把专业与交付标准稳住，靠客户复购、口碑、合同和现金流纪律逐步放大。",
            "five": "500万级需要从个人能力升级为系统能力：报价模板、交付团队、渠道、产品化方案和财务风控要同时成型。",
            "ten": "千万级不是完全没有机会，但不能靠单人状态和情绪冲刺，需要团队、资本、供应链或平台型资源共同承接。",
        }
    if "木" in useful or strong_element == "木":
        return {
            "base": f"这张盘的财运更依赖生长曲线：内容、教育、产品迭代、长期人脉和持续输出会比短线爆发更稳。喜用{useful_text}时，先种长期资产，再谈规模。",
            "million": "百万级来自稳定作品、课程/咨询/产品线、长期客户池和个人品牌信任感。",
            "five": "500万级要看内容或服务能否产品化，是否能从个人交付变成团队交付、渠道交付。",
            "ten": "千万级需要更大市场、平台分发或资本化能力；若只靠个人表达，容易累但不一定放大。",
        }
    if "火" in useful:
        return {
            "base": f"这张盘的财运需要曝光、表达、销售和品牌势能，但火旺也容易带来冲动承诺。喜用{useful_text}时，要让热度服务于成交，而不是让情绪带着现金流跑。",
            "million": "百万级来自可持续曝光、清晰定位、稳定销售漏斗和可交付的服务/产品。",
            "five": "500万级需要品牌、渠道、团队销售和复购系统，否则容易高开低走。",
            "ten": "千万级必须有强分发、强团队和强风控，不能只靠个人热度。",
        }
    return {
        "base": f"这张盘的财运更看承接能力：流程、组织、库存、信用、账务和长期稳定。喜用{useful_text}时，越能把事情落到制度里，越容易把钱留住。",
        "million": "百万级来自稳定客户、稳定项目、清楚账务和可靠交付，不宜靠高风险投机。",
        "five": "500万级需要组织化和资产化，把人、货、钱、流程和责任边界全部稳住。",
        "ten": "千万级需要平台、供应链、资本或重资产协同，同时对库存、债务和合规要求更高。",
    }


def income_probabilities(strength: int, useful: list[str], data: dict, ec, profile: dict, context: dict | None = None) -> list[list[str]]:
    if context is None:
        context = {"group_scores": {key: 0 for key in GROUP_LABEL}}
    has_income = 1 if data.get("income") else 0
    wealth_force = context["group_scores"].get("wealth", 0)
    output_force = context["group_scores"].get("output", 0)
    officer_force = context["group_scores"].get("officer", 0)
    peer_force = context["group_scores"].get("peer", 0)
    capacity = 6 if 48 <= strength <= 68 else (3 if strength > 68 else -4)
    structure_bonus = min(10, wealth_force * 2 + output_force + officer_force + capacity)
    peer_penalty = max(0, peer_force - wealth_force) * 2
    million = max(42, min(76, 52 + has_income * 5 + structure_bonus - peer_penalty))
    five_million = max(16, min(42, 24 + wealth_force + output_force + max(0, strength - 55) // 4 - peer_penalty // 2))
    ten_million = max(4, min(22, 100 - million - five_million))
    overflow = million + five_million + ten_million - 100
    if overflow > 0:
        reduce_five = min(overflow, five_million - 18)
        five_million -= reduce_five
        overflow -= reduce_five
        million -= overflow
    elif overflow < 0:
        million += abs(overflow)
    million = int(round(million))
    five_million = int(round(five_million))
    ten_million = max(0, 100 - million - five_million)

    def pct(value: int) -> str:
        return f"{value}%"
    tone = wealth_tone(strength, useful, ec, profile, context)
    return [
        ["百万级", pct(million), "RMB 100万-500万/年", f"{tone['million']} 置信度约68%。"],
        ["500万级", pct(five_million), "RMB 500万-1000万/年", f"{tone['five']} 置信度约58%。"],
        ["千万级", pct(ten_million), "RMB 1000万以上/年", f"{tone['ten']} 置信度约45%。"],
    ]


def annual_rows(selected_ganzhi: str, useful: list[str], context: dict | None = None) -> list[list[str]]:
    if context:
        rows = []
        for offset, ganzhi in enumerate(GANZHI_2026_2036):
            year = str(2026 + offset)
            read = analyze_luck_pillar(context, ganzhi, "year")
            rows.append([
                year,
                ganzhi,
                selected_ganzhi or "未识别",
                str(read["career"]),
                str(read["wealth"]),
                str(read["relationship"]),
                str(read["stress"]),
                str(read["loss"]),
                str(read["family"]),
                str(read["compliance"]),
                read["note"],
            ])
        return rows
    useful_text = "、".join(useful) or "规则与节奏"
    years = [
        ("2026", "丙午", 4, 3, 6, 8, 7, 4, 8, f"丙午火势很旺，容易把行动、表达和承诺一起点燃；本盘喜用{useful_text}，这一年要先控现金流、库存、杠杆和口头合伙。"),
        ("2027", "丁未", 5, 4, 5, 7, 6, 5, 6, "丁火透出、未土承接，适合整理产品、团队和交付流程；不宜在规则没成型前扩大固定成本。"),
        ("2028", "戊申", 7, 7, 5, 5, 4, 4, 5, f"申金出现，财星、客户、合同和定价能力被激活；若喜用含{useful_text}，适合谈长期客户、收账和标准化报价。"),
        ("2029", "己酉", 7, 8, 7, 5, 5, 4, 8, "酉金财气更明显，钱、关系、分成和股权容易同场出现；所有合作要写清比例、退出、税务和账期。"),
        ("2030", "庚戌", 7, 7, 5, 6, 4, 5, 6, "庚金透出利商业化、定价和资产化；戌土带承接也带规则成本，适合把经验沉淀成产品或制度。"),
        ("2031", "辛亥", 7, 7, 6, 5, 4, 5, 5, "辛金与亥水并见，利合同、沟通、跨城/跨境、数据和长期资源；关系上更看边界与现实承诺。"),
        ("2032", "壬子", 7, 7, 6, 6, 4, 5, 5, "壬子水势强，压力、流动性、制度和学习要求上升；适合证照、系统化、跨境流通，但要管住焦虑和过劳。"),
        ("2033", "癸丑", 6, 6, 5, 5, 4, 5, 5, "癸水落丑土，适合预算、结算、库存和稳定合作；这年重点不是冲规模，而是把账、货、人和合同收拢。"),
        ("2034", "甲寅", 6, 5, 5, 6, 5, 4, 5, "甲寅木气生发，利学习、内容、教育、产品迭代和新方向；财务兑现偏后置，避免为新故事提前重投入。"),
        ("2035", "乙卯", 5, 5, 7, 6, 6, 5, 8, "乙卯木旺带人际、合作和关系调整，卯木容易触发边界议题；合规、口碑、情绪承诺和合同条款要提前稳住。"),
        ("2036", "丙辰", 5, 4, 5, 7, 6, 5, 6, "丙火再起、辰土收束，像一次复盘与重整；不要重复 2026 的冲动扩张，要用预算、复盘和退出条件先框住机会。"),
    ]
    return [[year, pillar, selected_ganzhi or "未识别", str(career), str(wealth), str(relation), str(stress), str(loss), str(family), str(compliance), trigger] for year, pillar, career, wealth, relation, stress, loss, family, compliance, trigger in years]


def ten_god_for(day_stem: str, target_stem: str) -> str:
    day_element = STEM_ELEMENT.get(day_stem)
    target_element = STEM_ELEMENT.get(target_stem)
    if not day_element or not target_element:
        return "未知"
    same_polarity = STEM_POLARITY.get(day_stem) == STEM_POLARITY.get(target_stem)
    if day_element == target_element:
        return "比肩" if same_polarity else "劫财"
    if GENERATES.get(day_element) == target_element:
        return "食神" if same_polarity else "伤官"
    if CONTROLS.get(day_element) == target_element:
        return "偏财" if same_polarity else "正财"
    if CONTROLS.get(target_element) == day_element:
        return "七杀" if same_polarity else "正官"
    if GENERATES.get(target_element) == day_element:
        return "偏印" if same_polarity else "正印"
    return "未知"


def group_for_ten_god(ten_god: str) -> str:
    return TEN_GOD_GROUP.get(ten_god, "other")


def primary_hidden_stem(branch: str) -> str:
    hidden = HIDDEN_WEIGHT.get(branch, [])
    return hidden[0][0] if hidden else ""


def stem_for_element(element: str) -> str:
    for stem, item in STEM_ELEMENT.items():
        if item == element:
            return stem
    return ""


def relationship_star_group(gender: str) -> str:
    return "wealth" if gender == "男" else "officer"


def relation_labels_with(branches: list[str], flow_branch: str) -> list[str]:
    labels = []
    for branch in branches:
        if not flow_branch or not branch:
            continue
        if branch == flow_branch:
            labels.append(f"{branch}{flow_branch}伏吟")
        key = branch_pair_key(branch, flow_branch)
        for mapping in (LIU_HE, LIU_CHONG, LIU_HAI, LIU_PO, PAIR_XING):
            if key in mapping:
                labels.append(mapping[key])
    joined = set(branches + [flow_branch])
    for combo, label in SAN_HE.items():
        if combo.issubset(joined):
            labels.append(label)
    for raw, label in SAN_HE_HALVES.items():
        if raw[0] in joined and raw[1] in joined:
            labels.append(label)
    return unique(labels)


def risk_flags_for_context(context: dict) -> list[dict[str, str]]:
    flags = []
    scores = context["group_scores"]
    relation_text = context["relation_text"]
    stems = context["stems"]
    day_element = context["day_element"]
    useful_text = "、".join(context["useful"]) or "资源"
    officer_heavy = scores.get("officer", 0) >= 1.8
    wealth_visible = scores.get("wealth", 0) >= 1.2
    peer_visible = scores.get("peer", 0) >= 1.2
    output_visible = scores.get("output", 0) >= 1.0

    if context["strength"] <= 45 and officer_heavy:
        flags.append({
            "key": "weak_officer",
            "title": "身弱官杀旺",
            "severity": "high",
            "text": f"日主偏弱而官杀压力重，优先取{useful_text}补根与通关；财星、官杀、火土类动作不能只因缺失就加码。",
        })
    if peer_visible and wealth_visible:
        flags.append({
            "key": "peer_wealth",
            "title": "比劫夺财/合伙分利",
            "severity": "high",
            "text": "比劫与财星同场，赚钱机会容易和朋友、合伙、分账、客户归属、股权退出绑定；合同和主权边界必须前置。",
        })
    for i, stem_a in enumerate(stems):
        for stem_b in stems[i + 1:]:
            combo = GAN_HE.get(stem_a + stem_b) or GAN_HE.get(stem_b + stem_a)
            if not combo:
                continue
            group_a = group_for_ten_god(ten_god_for(context["day_stem"], stem_a))
            group_b = group_for_ten_god(ten_god_for(context["day_stem"], stem_b))
            if {group_a, group_b} == {"peer", "wealth"}:
                flags.append({
                    "key": "peer_wealth_combo",
                    "title": f"{combo}引动分利",
                    "severity": "high",
                    "text": f"天干见{combo}且落在比劫/财星关系上，钱越做大，越要防后端分钱、股权、所有权和客户归属争议。",
                })
    if output_visible and officer_heavy:
        flags.append({
            "key": "output_officer",
            "title": "食伤制杀/伤官见官双面结构",
            "severity": "medium",
            "text": "食伤能破局、做表达和产品化，但碰到官杀也会带来规则、合同、平台、法务和公开沟通压力。",
        })
    if any(word in relation_text for word in ["刑", "破", "冲", "害"]) and officer_heavy:
        flags.append({
            "key": "legal_collision",
            "title": "刑冲官杀合规风险",
            "severity": "high",
            "text": f"原局有{relation_text or '合冲刑害'}且官杀较重，事业推进必须把合同、交付、宣传、税务和平台规则先写清。",
        })
    if context["strength"] >= 70 and peer_visible:
        flags.append({
            "key": "strong_peer",
            "title": "身强比劫过旺",
            "severity": "medium",
            "text": "主观能量和竞争心较强，越到机会放大时越要防冲动扩张、过度承诺和合伙边界混乱。",
        })
    if not flags:
        flags.append({
            "key": "standard",
            "title": "标准风险",
            "severity": "normal",
            "text": f"当前未触发重型报警，仍需按月令{context['month_structure']}、大运流年和喜用{useful_text}做节奏管理。",
        })
    return flags


def analysis_context(data: dict, computed: dict, strength: int, useful: list[str]) -> dict:
    ec = computed["ec"]
    diagnostic = day_master_diagnostics(ec, computed.get("profile", {}))
    day_stem = ec.getDayGan()
    day_branch = ec.getDayZhi()
    pillars = computed.get("chart", {}).get("pillars", [])
    branches = [pillar.get("branch", "") for pillar in pillars]
    stems = [pillar.get("stem", "") for pillar in pillars]
    group_scores = {key: 0.0 for key in GROUP_LABEL}
    ten_god_counts = {}
    visible_ten_gods = []
    hidden_ten_gods = []
    for pillar in pillars:
        gan_shen = pillar.get("gan_shen") or "日主"
        if gan_shen != "日主":
            visible_ten_gods.append(gan_shen)
            ten_god_counts[gan_shen] = ten_god_counts.get(gan_shen, 0) + 1
            group = group_for_ten_god(gan_shen)
            if group in group_scores:
                group_scores[group] += 1.4
        for shen in pillar.get("zhi_shen", []):
            hidden_ten_gods.append(shen)
            ten_god_counts[shen] = ten_god_counts.get(shen, 0) + 1
            group = group_for_ten_god(shen)
            if group in group_scores:
                group_scores[group] += 0.65
    month_branch = ec.getMonthZhi()
    month_main_stem = primary_hidden_stem(month_branch)
    month_structure = ten_god_for(day_stem, month_main_stem) if month_main_stem else "未识别"
    spouse_group = relationship_star_group(data.get("gender", ""))
    spouse_stars = ["正财", "偏财"] if spouse_group == "wealth" else ["正官", "七杀"]
    spouse_visible = [tg for tg in visible_ten_gods if tg in spouse_stars]
    spouse_hidden = [tg for tg in hidden_ten_gods if tg in spouse_stars]
    relation_text = "；".join(computed.get("chart", {}).get("relations") or [])
    context = {
        "data": data,
        "ec": ec,
        "day_stem": day_stem,
        "day_element": STEM_ELEMENT.get(day_stem, ""),
        "day_branch": day_branch,
        "month_branch": month_branch,
        "month_structure": month_structure,
        "month_main_stem": month_main_stem,
        "branches": branches,
        "stems": stems,
        "strength": strength,
        "useful": useful,
        "diagnostic": diagnostic,
        "useful_groups": diagnostic["useful_groups"],
        "profile": computed.get("profile", {}),
        "group_scores": group_scores,
        "ten_god_counts": ten_god_counts,
        "spouse_group": spouse_group,
        "spouse_stars": spouse_stars,
        "spouse_visible": spouse_visible,
        "spouse_hidden": spouse_hidden,
        "relation_text": relation_text,
    }
    context["risk_flags"] = risk_flags_for_context(context)
    context["review_required"] = any(flag["severity"] == "high" for flag in context["risk_flags"])
    return context


def interaction_note(labels: list[str], context: dict) -> tuple[str, bool, bool]:
    if not labels:
        return "未见强冲合，主要看十神和喜忌承接。", False, False
    day_hit = any(context["day_branch"] in label for label in labels)
    month_hit = any(context["month_branch"] in label for label in labels)
    note = "、".join(labels[:3])
    if day_hit:
        note += "，触发日支/关系宫。"
    elif month_hit:
        note += "，触发月令/事业宫。"
    else:
        note += "，作为背景触发。"
    return note, day_hit, month_hit


def analyze_luck_pillar(context: dict, ganzhi: str, scope: str) -> dict:
    stem, branch = split_ganzhi(ganzhi)
    stem_tg = ten_god_for(context["day_stem"], stem)
    branch_main = ten_god_for(context["day_stem"], primary_hidden_stem(branch))
    hidden_groups = [group_for_ten_god(ten_god_for(context["day_stem"], item[0])) for item in HIDDEN_WEIGHT.get(branch, [])]
    stem_group = group_for_ten_god(stem_tg)
    branch_group = group_for_ten_god(branch_main)
    element_hits = [STEM_ELEMENT.get(stem, ""), BRANCH_ELEMENT.get(branch, "")]
    useful_hit = any(element in context["useful"] for element in element_hits)
    weak_officer_alert = any(flag["key"] == "weak_officer" for flag in context.get("risk_flags", []))
    peer_wealth_alert = any(flag["key"] in {"peer_wealth", "peer_wealth_combo"} for flag in context.get("risk_flags", []))
    output_officer_alert = any(flag["key"] == "output_officer" for flag in context.get("risk_flags", []))
    labels = relation_labels_with(context["branches"], branch)
    relation_note, day_hit, month_hit = interaction_note(labels, context)
    career = 5
    wealth = 5
    relationship = 5
    stress = 5
    loss = 4
    family = 4
    compliance = 5
    reasons = []
    priority_reasons = []

    for group in [stem_group, branch_group] + hidden_groups[:2]:
        if group == "output":
            career += 1
            wealth += 1
            reasons.append("食伤被引动，利表达、产品、销售与作品输出")
        elif group == "wealth":
            wealth += 2
            career += 1
            relationship += 1 if context["spouse_group"] == "wealth" else 0
            reasons.append("财星被引动，客户、现金流、定价和现实交易变重")
        elif group == "officer":
            career += 1
            stress += 1
            compliance += 1
            relationship += 1 if context["spouse_group"] == "officer" else 0
            reasons.append("官杀被引动，责任、规则、岗位压力和名分议题上升")
        elif group == "resource":
            career += 1
            stress -= 1
            reasons.append("印星被引动，利学习、资质、方法论和系统支持")
        elif group == "peer":
            career += 1
            loss += 1
            reasons.append("比劫被引动，竞争、合伙、分利和现金流波动要先管住")

    if useful_hit:
        career += 1
        wealth += 1
        stress -= 1
        reasons.append("流年/月带到本盘可用之气，机会更容易落地")
    else:
        stress += 1
    if context["strength"] < 46 and (stem_group in {"wealth", "officer"} or branch_group in {"wealth", "officer"}):
        stress += 2
        loss += 1
        wealth -= 1
        priority_reasons.append("身弱遇财官，机会背后成本、合规和承压同步上升")
    if weak_officer_alert and (stem_group in {"resource", "peer"} or branch_group in {"resource", "peer"}):
        career += 1
        stress -= 1
        reasons.append("印比到位，能补根、补专业和缓冲官杀压力")
    if weak_officer_alert and (stem_group in {"wealth", "officer"} or branch_group in {"wealth", "officer"}):
        compliance += 2
        loss += 1
        priority_reasons.append("身弱官杀旺盘忌硬接财官，合同、平台规则和责任边界要先审")
    if weak_officer_alert and (stem_group == "output" or branch_group == "output") and output_officer_alert:
        career += 2
        wealth += 1
        stress += 1
        compliance += 1
        priority_reasons.append("食伤可制杀破局，利线上表达和产品化，但不能越过规则")
    if context["strength"] > 68 and stem_group == "peer":
        loss += 2
        reasons.append("身强再逢比劫，最怕合伙分利和冲动扩张")
    if day_hit:
        relationship += 2 if any("合" in label for label in labels) else -1
        stress += 1
        family += 2
        reasons.append("日支被触发，亲密关系、合作绑定和居住安排需要明说")
    if month_hit:
        career += 1
        compliance += 1
        reasons.append("月令被触发，事业环境、上级客户和执行规则会更显眼")
    if any("冲" in label or "刑" in label or "害" in label or "破" in label for label in labels):
        stress += 2
        loss += 1
        compliance += 1
    if stem_tg == "伤官" and context["group_scores"].get("officer", 0) >= 1.0:
        compliance += 2
        stress += 1
        reasons.append("伤官碰到原局官杀，公开表达、规则冲突和合规风险要控")
    if stem_tg in context["spouse_stars"] or branch_main in context["spouse_stars"] or day_hit:
        relationship += 1
    if stem_tg in {"正财", "偏财"} and context["group_scores"].get("peer", 0) > 1.5:
        loss += 1
        priority_reasons.append("财星出现但原局比劫也有力，合作分账和客户归属要写清")
    if peer_wealth_alert and (stem_group in {"peer", "wealth"} or branch_group in {"peer", "wealth"}):
        loss += 2
        compliance += 1
        priority_reasons.append("比劫夺财被流年/月引动，朋友合伙、分账退出和客户归属必须死锁")

    note_parts = unique(priority_reasons + reasons)[:4]
    if not note_parts:
        note_parts = [f"{stem_tg}/{branch_main}被引动，先看其与月令、日支和大运是否形成承接"]
    note = f"{ganzhi}：{relation_note}{' '.join(note_parts)}。"
    if scope == "month":
        note = f"{ganzhi}月：{relation_note}{' '.join(note_parts)}。"
    return {
        "stem_tg": stem_tg,
        "branch_tg": branch_main,
        "relations": labels,
        "career": max(2, min(9, career)),
        "wealth": max(2, min(9, wealth)),
        "relationship": max(2, min(9, relationship)),
        "stress": max(2, min(9, stress)),
        "loss": max(2, min(9, loss)),
        "family": max(2, min(9, family)),
        "compliance": max(2, min(9, compliance)),
        "note": note,
    }


def split_ganzhi(ganzhi: str) -> tuple[str, str]:
    text = str(ganzhi or "").strip()
    if len(text) < 2:
        return "", ""
    return text[0], text[1]


def hidden_texts(branch: str) -> list[str]:
    return [f"{stem}·{STEM_ELEMENT.get(stem, '')}" for stem, _ in HIDDEN_WEIGHT.get(branch, [])]


def hidden_ten_gods(day_stem: str, branch: str) -> list[str]:
    return [ten_god_for(day_stem, stem) for stem, _ in HIDDEN_WEIGHT.get(branch, [])]


def flow_pillar(day_stem: str, day_branch: str, ganzhi: str, label: str) -> dict:
    stem, branch = split_ganzhi(ganzhi)
    xunkong = LunarUtil.getXunKong(ganzhi) if stem and branch else ""
    return {
        "label": label,
        "gan_shen": ten_god_for(day_stem, stem) if stem else "未识别",
        "stem": stem or "未识别",
        "branch": branch or "未识别",
        "hidden": hidden_texts(branch),
        "zhi_shen": hidden_ten_gods(day_stem, branch),
        "nayin": LunarUtil.NAYIN.get(ganzhi, "未识别") if stem and branch else "未识别",
        "kongwang": xunkong,
        "dishi": "随流盘触发",
        "shen_sha": calculate_shensha(day_stem, day_branch, branch, xunkong) if branch else [],
    }


def flow_chart_model(computed: dict, gender: str, useful: list[str], context: dict | None = None) -> dict:
    ec = computed["ec"]
    now = datetime.now()
    flow_ec = Solar.fromYmdHms(now.year, now.month, now.day, now.hour, now.minute, 0).getLunar().getEightChar()
    yun, selected, dayun_rows = current_dayun(ec, gender, now.year)
    day_stem = ec.getDayGan()
    day_branch = ec.getDayZhi()
    natal = [dict(pillar, label=label) for label, pillar in zip(PILLAR_LABELS, computed["chart"]["pillars"])]
    flow_columns = natal + [
        flow_pillar(day_stem, day_branch, selected.getGanZhi() if selected else "", "大运"),
        flow_pillar(day_stem, day_branch, flow_ec.getYear(), "流年"),
        flow_pillar(day_stem, day_branch, flow_ec.getMonth(), "流月"),
    ]
    rows = []
    row_specs = [
        ("主星/干神", lambda p: p.get("gan_shen") or "日主"),
        ("天干", lambda p: p.get("stem", "")),
        ("地支", lambda p: p.get("branch", "")),
        ("藏干", lambda p: " / ".join(p.get("hidden") or ["无"])),
        ("支神", lambda p: " / ".join(p.get("zhi_shen") or ["无"])),
        ("纳音", lambda p: p.get("nayin", "未识别")),
        ("空亡", lambda p: p.get("kongwang", "未识别")),
        ("地势", lambda p: p.get("dishi", "随流盘触发")),
        ("神煞", lambda p: "、".join(p.get("shen_sha") or ["无明显主星"])),
    ]
    for name, getter in row_specs:
        rows.append([name] + [getter(pillar) for pillar in flow_columns])
    dayun_strip = []
    for dy in yun.getDaYun():
        ganzhi = dy.getGanZhi()
        if not ganzhi:
            continue
        status = "当前大运" if selected and dy.getStartYear() <= now.year <= dy.getEndYear() else ""
        dayun_strip.append([f"{dy.getStartAge()}-{dy.getEndAge()}岁", str(dy.getStartYear()), ganzhi, status])
    annual_strip = []
    for row in annual_rows(selected.getGanZhi() if selected else "", useful, context):
        annual_strip.append([row[0], row[1], row[3], row[4], row[5], row[6], row[10]])
    month_strip = [[row[0], row[1], row[2], row[3], row[4], row[6], row[7]] for row in monthly_rows(context)]
    return {
        "reference": now.strftime("%Y-%m-%d %H:%M"),
        "selected_dayun": selected.getGanZhi() if selected else "未识别",
        "flow_year": flow_ec.getYear(),
        "flow_month": flow_ec.getMonth(),
        "headers": ["项目", "年柱", "月柱", "日柱", "时柱", "大运", "流年", "流月"],
        "rows": rows,
        "dayun_strip": dayun_strip[:10],
        "annual_strip": annual_strip,
        "month_strip": month_strip,
    }


def income_stage_rows(useful: list[str], strength: int, annual: list[list[str]] | None = None) -> list[list[str]]:
    useful_text = "、".join(useful) or "节奏"
    annual = annual or []
    ranges = [("2026-2027", annual[:2]), ("2028-2029", annual[2:4]), ("2030-2033", annual[4:8]), ("2034-2036", annual[8:11])]
    rows = []
    for label, items in ranges:
        if not items:
            continue
        avg_wealth = round(sum(int(row[4]) for row in items) / len(items), 1)
        avg_risk = round(sum(int(row[6]) + int(row[7]) + int(row[9]) for row in items) / len(items), 1)
        best = max(items, key=lambda row: int(row[4]))
        risky = max(items, key=lambda row: int(row[6]) + int(row[7]) + int(row[9]))
        if avg_wealth >= 7:
            judgment = f"财务打开期，重点年份 {best[0]}{best[1]}"
            condition = f"用{useful_text}把客户、定价、合同、复购和交付边界接住。"
        elif avg_wealth >= 5.5:
            judgment = f"稳步积累期，重点看 {best[0]}{best[1]}"
            condition = "适合把个人能力沉淀为产品、内容、渠道或长期客户池。"
        else:
            judgment = "筛选与防守期"
            condition = "不宜重资产押注，先守现金流、合同、库存和关键客户。"
        if avg_risk >= 18:
            risk = f"高风险点在 {risky[0]}{risky[1]}：{risky[10]}"
        else:
            risk = f"风险可控，但 {risky[0]}{risky[1]} 仍需按预算和退出条件推进。"
        if strength < 48:
            risk += " 身弱盘先补资源与支持系统，不宜硬扛。"
        elif strength > 68:
            risk += " 身强盘最怕动作过大，先定边界再放量。"
        rows.append([label, judgment, condition, risk])
    return rows


def career_rows(data: dict, model: dict) -> list[list[str]]:
    industry = data.get("industry") or "未填写"
    role = data.get("role") or "未填写"
    useful_text = "、".join(model["useful_elements"]) or "节奏与边界"
    context = model["analysis_context"]
    scores = context["group_scores"]
    top_group = max(scores, key=scores.get)
    structure = context["month_structure"]
    group_path = {
        "wealth": "客户、定价、交易、资源整合、商业化和现金流管理",
        "output": "内容、产品、表达、销售、技术输出、咨询交付和方法论沉淀",
        "officer": "平台、制度、管理、合规、项目责任、专业资质和组织内上升",
        "resource": "研究、教育、知识产品、资质、系统建设、咨询方法论和长期学习",
        "peer": "创业、合伙、个人品牌、社群、竞争型赛道和资源置换",
    }.get(top_group, "可沉淀、可复盘、可定价的专业路径")
    fit = "匹配度偏高" if any(word in (industry + role) for word in ["咨询", "品牌", "运营", "产品", "金融", "数据", "法务", "技术", "教育", "供应链", "研究", "管理", "销售"]) else "需要主动改造成可沉淀、可定价、可复盘的部分"
    risk = []
    if scores.get("peer", 0) >= 2:
        risk.append("合伙分利")
    if scores.get("officer", 0) >= 2:
        risk.append("权责合规")
    if scores.get("output", 0) >= 2 and scores.get("officer", 0) >= 1:
        risk.append("表达与规则冲突")
    if scores.get("wealth", 0) >= 2:
        risk.append("账期和现金流")
    risk_text = "、".join(risk) or "节奏失控"
    flags = [flag for flag in context.get("risk_flags", []) if flag["key"] != "standard"]
    review = "；".join(flag["title"] for flag in flags[:3]) or "未触发重型报警"
    review_action = "此盘建议进入 Atelier Review 人工复核队列，先核喜用神、合伙结构和法务/财务红线。" if context.get("review_required") else "自动版可交付，但关键合作和资金动作仍建议人工复核。"
    return [
        ["事业主轴", f"月令主气取{structure}，全盘较强的事业驱动力落在{GROUP_LABEL.get(top_group, '主轴')}。", f"按子平先看月令、再看十神成败；本盘适合围绕{group_path}建立职业路径。"],
        ["适合行业", group_path, f"依据不是单看喜用神，而是月令{structure}、十神分布、日主{model['day_strength_label']}与喜用{useful_text}共同判断。"],
        ["当前基线", f"{industry} / {role}", f"当前方向{fit}；如果行业不能积累客户、流程、合同、数据或作品，就要主动改造成可复用资产。"],
        ["发展模式", "先定结构，再放大机会。", "先做报价、合同、SOP、复盘、客户筛选和交付边界；再考虑规模、团队或投放。"],
        ["风险节点", risk_text, "这些风险来自本命十神与地支关系，不是泛泛提醒；遇到对应流年流月时，要先降杠杆、缩周期、留书面记录。"],
        ["复核等级", review, review_action],
    ]


def crisis_rows(context: dict) -> list[list[str]]:
    scores = context["group_scores"]
    rows = []
    for flag in context.get("risk_flags", []):
        if flag["key"] == "weak_officer":
            rows.append([flag["title"], flag["text"], "先补专业/信息/资质/支持系统，再谈财务放大；重大合同、平台规则和法律责任必须人工复核。"])
        elif flag["key"] in {"peer_wealth", "peer_wealth_combo"}:
            rows.append([flag["title"], flag["text"], "从第一天写清股权、收款账户、客户归属、IP/代码/数据所有权、退出条款和违约责任。"])
        elif flag["key"] == "output_officer":
            rows.append([flag["title"], flag["text"], "可做线上表达和产品化破局，但发布、营销、合同承诺、交付边界要先过复核。"])
        elif flag["key"] == "legal_collision":
            rows.append([flag["title"], flag["text"], "所有合作先走书面流程，避免口头承诺、模糊分成、代持和没有退出条款的项目。"])
    if scores.get("peer", 0) >= 2.0 and scores.get("wealth", 0) >= 1.0:
        rows.append(["分利与现金流危机", "比劫与财星同时有力，机会容易和合伙、分账、客户归属绑在一起。", "报价、客户归属、账期、股权/分成、退出条件必须先写清。"])
    if scores.get("officer", 0) >= 2.0 and context["strength"] < 55:
        rows.append(["压力与权责危机", "官杀较重而日主承压，容易遇到规则、上级、平台、合规或强势客户压力。", "先确认责任边界、交付标准和法务财务口径，避免口头承诺。"])
    if scores.get("output", 0) >= 1.6 and scores.get("officer", 0) >= 1.4:
        rows.append(["表达与规则冲突", "食伤与官杀并见，适合靠表达和产品突破，但也容易挑战规则或公开争执。", "公开发布、合同承诺、宣传文案、客户沟通要留复核机制。"])
    if "冲" in context["relation_text"] or "刑" in context["relation_text"] or "害" in context["relation_text"]:
        rows.append(["合冲刑害触发", f"原局地支关系为：{context['relation_text']}。这会让事业节奏、关系边界或居住/合作安排更容易被流年触发。", "遇到相关流年流月先降杠杆、缩周期、用书面确认替代情绪判断。"])
    if context["spouse_visible"] or context["spouse_hidden"]:
        rows.append(["关系与现实责任", f"伴侣星线索为：{'、'.join(unique(context['spouse_visible'] + context['spouse_hidden']))}。关系不会只停在感觉，容易牵涉现实责任、钱、时间和未来安排。", "谈关系时同步谈城市、消费观、工作节奏、家庭责任，不要只靠情绪维持。"])
    if not rows:
        rows.append(["核心限制", f"月令主气为{context['month_structure']}，盘面没有单一压倒性危机，重点是让{GROUP_BEHAVIOR.get(group_for_ten_god(context['month_structure']), '主要结构')}走清楚。", "不追求一次性定终局，先用阶段目标、预算、复盘和退出条件做控制。"])
    rows.append(["压力管理", "命理只能提示压力形态，不能替代医疗、法律、投资意见。", "出现持续身体症状、法律/税务/投资重大事项时，必须找专业人士复核。"])
    return rows[:5]


def shensha_balance_text(label: str, rows: list[list[str]]) -> str:
    stars = [row[1] for row in rows]
    support = [s for s in stars if s in {"天乙贵人", "文昌贵人", "学堂", "国印", "福星贵人", "太极贵人"}]
    risk = [s for s in stars if s in {"羊刃", "空亡", "灾煞", "童子"}]
    if support and risk:
        return f"{label}神煞制衡关系：{ '、'.join(support) }能提供制度、学习、贵人或专业缓冲，但{ '、'.join(risk) }提示兑现不稳或冲突压力；必须用规则、合同和复盘承接。"
    if support:
        return f"{label}神煞制衡关系：{ '、'.join(support) }偏向支持学习、资质、制度和专业表达；它能加分，但仍需大运流年触发。"
    if risk:
        return f"{label}神煞制衡关系：{ '、'.join(risk) }提示该柱主题有延迟、冲突或不稳定，不能单独断凶，应回到十神、地支关系和现实行为控制。"
    return f"{label}神煞制衡关系：未见强神煞制衡，不硬凑，以月令、十神、大运流年为主。"


def cross_shensha_balance(rows_by_group: dict[str, list[list[str]]]) -> str:
    all_stars = [row[1] for rows in rows_by_group.values() for row in rows]
    helpers = [s for s in all_stars if s in {"天乙贵人", "文昌贵人", "学堂", "国印", "福星贵人", "太极贵人"}]
    risks = [s for s in all_stars if s in {"羊刃", "空亡", "灾煞", "童子"}]
    if helpers and risks:
        return f"跨柱神煞制衡关系：{ '、'.join(unique(helpers)) }可以缓冲{ '、'.join(unique(risks)) }，但前提是走制度、专业、合同、长辈/机构支持，而不是靠情绪硬扛。"
    if helpers:
        return f"跨柱神煞制衡关系：{ '、'.join(unique(helpers)) }重复出现时，说明学习、文书、制度和贵人资源可作为长期支点。"
    if risks:
        return f"跨柱神煞制衡关系：{ '、'.join(unique(risks)) }偏风险提示，需用地支关系、大运流年和现实风险控制复核，不能单凭神煞定凶。"
    return "跨柱神煞制衡关系：无明显强制衡关系，神煞仅作辅助修正。"


def june_2026_detail(context: dict | None = None) -> str:
    if not context:
        return "2026 年 6 月甲午是全年高风险月：午火叠加全年丙午，容易把表达、投资、情绪承诺、业务扩张和现金流压力同时点燃。"
    read = analyze_luck_pillar(context, "甲午", "month")
    line = f"2026 年 6 月甲午：{read['note']}事业 {read['career']}/9，财运 {read['wealth']}/9，关系 {read['relationship']}/9，风险 {read['stress']}/9。"
    if read["stress"] >= 7 or read["loss"] >= 7:
        line += " 这一月不宜重库存、高杠杆、模糊分成和情绪化承诺，重大付款和签约建议延迟复核。"
    elif read["wealth"] >= 7:
        line += " 这一月可以推进销售、发布和客户沟通，但要先设交付边界和收款节点。"
    else:
        line += " 这一月更适合试运行、收反馈和做复盘，不要把所有资源押在单点突破上。"
    return line


def monthly_rows(context: dict | None = None) -> list[list[str]]:
    if not context:
        data = [
            ("2026-02", "庚寅", "立春-惊蛰", 6, 6, 5, 6, "寅木启动计划，适合小样本验证。"),
            ("2026-03", "辛卯", "惊蛰-清明", 6, 6, 7, 7, "卯木带来关系和合作波动，签约要慢。"),
            ("2026-04", "壬辰", "清明-立夏", 7, 7, 5, 5, "辰土收束，适合谈规则、账期和合同。"),
            ("2026-05", "癸巳", "立夏-芒种", 6, 5, 6, 7, "巳火加热，推进快但压力上升。"),
            ("2026-06", "甲午", "芒种-小暑", 4, 3, 8, 9, "全年高风险月，禁高杠杆、重库存、冲动承诺和情绪摊牌。"),
        ]
        return [[m, gz, period, str(c), str(w), str(r), str(risk), note] for m, gz, period, c, w, r, risk, note in data]
    rows = []
    for month, ganzhi, period in MONTHS_2026:
        read = analyze_luck_pillar(context, ganzhi, "month")
        rows.append([month, ganzhi, period, str(read["career"]), str(read["wealth"]), str(read["relationship"]), str(max(read["stress"], read["loss"])), read["note"]])
    return rows


def relationship_profile(data: dict, useful: list[str], context: dict | None = None, annual: list[list[str]] | None = None) -> list[list[str]]:
    if context:
        annual = annual or []
        good_years = [row for row in annual if int(row[5]) >= 7 and int(row[6]) <= 7]
        risk_years = [row for row in annual if int(row[5]) >= 7 and int(row[6]) >= 8]
        window = "、".join(f"{row[0]}{row[1]}" for row in good_years[:4]) or "需人工结合事件校准"
        meet = f"{good_years[0][0]}{good_years[0][1]}" if good_years else "无法提供判断"
        star_text = "、".join(unique(context["spouse_visible"] + context["spouse_hidden"])) or "未明显透出"
        spouse_element = BRANCH_ELEMENT.get(context["day_branch"], "")
        trait = {
            "金": "边界感强、专业、重规则或金融/数据/法务/技术气质",
            "水": "沟通强、流动性高、跨城/跨境/内容信息气质",
            "木": "成长型、教育/内容/设计/咨询气质，重长期发展",
            "火": "表达强、外向、品牌/销售/传播气质，节奏较快",
            "土": "稳定务实、运营/管理/地产/供应链气质，重现实承接",
        }.get(spouse_element, "偏稳定和专业感")
        relation_level = "中等偏高" if good_years else "需谨慎观察"
        risk_note = "；".join(f"{row[0]}{row[1]}压力高" for row in risk_years[:2]) or "主要风险来自现实责任没有谈清"
        return [
            ["未来关系波动", relation_level, f"伴侣星线索：{star_text}；夫妻宫为{context['day_branch']}，流年若合冲日支会明显触发关系。"],
            ["适合恋爱窗口", window, "按流年与日支、伴侣星、压力分数综合筛选，不是固定年份。"],
            ["最可能遇到时间", meet, "这是自动模型窗口；若客户提供恋爱/分手/结婚节点，可进一步校准。"],
            ["身高/体型", "无法提供判断", "自动版不硬编外貌；这类细节需人工结合全盘与事件复核。"],
            ["外貌气质", trait, f"由日支五行、伴侣星和喜用{''.join(useful)}综合取象，置信度中低。"],
            ["从事行业/角色", trait, "这是象意推断，不是硬性条件。"],
            ["不适配对象", "承诺模糊、财务边界混乱、强情绪控制或长期不给行动的人", risk_note],
            ["结婚成熟窗口", window if meet != "无法提供判断" else "无法提供判断", "重点不是单一年份，而是对象、城市、钱、家庭责任是否同步成熟。"],
        ]
    return [
        ["未来关系波动", "中等偏高", "事业节奏、现金流和现实承诺会直接影响关系稳定，置信度约62%。"],
        ["适合恋爱窗口", "2026-12 至 2027-01、2028-2029、2031-2033", "优先选金水较足、规则感更强的月份/年份。"],
        ["最可能遇到时间", "需结合大运流年细推；当前模型以 2028-2033 为较优窗口", "若问卷事件不足，年份细节置信度降低。"],
        ["身高/体型", "无法提供判断", "自动版不硬编外貌；需人工结合财官、日支与流年复核。"],
        ["外貌气质", "偏清爽、有边界、稳定或专业感更适配", f"与喜用{''.join(useful)}的气质相近，低到中置信度。"],
        ["从事行业/角色", "金融、数据、法务、运营、咨询、技术、供应链等规则型角色更适配", "这是象意推断，不是硬性条件。"],
        ["不适配对象", "高情绪、高消费、高控制、无边界或承诺模糊的人", "会放大财务、时间和情绪消耗。"],
        ["运势互补对象", "能补流程、账务、沟通和冷静判断的人", "互补重点是行为系统，不是只看生肖或星座。"],
    ]


def event_calibration_rows(events: str, model: dict) -> list[list[str]]:
    if not events.strip():
        return []
    parts = [item.strip(" ；;。") for item in re.split(r"[\n；;]+", events) if item.strip(" ；;。")]
    rows = []
    useful_text = "、".join(model["useful_elements"]) or "节奏"
    for item in parts[:5]:
        year_match = re.search(r"(19|20)\d{2}", item)
        year = year_match.group(0) if year_match else "未标年份"
        if any(word in item for word in ["换", "转型", "城市", "迁", "工作"]):
            signal = "变动、职业环境和现实赛道被触发，重点看月柱/大运对事业节奏的牵引。"
            impact = "支持报告中“先立规则再放大机会”的判断，置信度小幅上调。"
        elif any(word in item for word in ["收入", "财", "副业", "投资", "产品", "创业"]):
            signal = "财星、食伤输出和现金流承接被触发，重点看客户、定价、账期和交付系统。"
            impact = f"支持喜用{useful_text}要落到合同、复盘、现金流规则上的判断。"
        elif any(word in item for word in ["感情", "结婚", "分手", "关系", "恋爱"]):
            signal = "日支/关系宫与现实承诺被触发，重点看关系边界、城市选择和金钱责任。"
            impact = "支持报告中关系需要现实规则和节奏管理的判断。"
        else:
            signal = "作为背景事件保留，自动版不强行过拟合到单一年份。"
            impact = "对核心结构影响中性，后续人工复核可进一步细分。"
        rows.append([year, item, signal, impact])
    return rows


def report_model(data: dict, computed: dict) -> dict:
    ec = computed["ec"]
    profile = computed["profile"]
    chart = computed["chart"]
    label, strength, useful_text, strength_reason = day_master_assessment(ec, profile)
    useful = useful_elements(ec, profile)
    yun, selected, dayun_rows = current_dayun(ec, data.get("gender", "男"))
    events = (data.get("events") or "").strip()
    calibration_title = "事件校准" if events else "置信度校准"
    dominant = "、".join(f"{k}{v}%" for k, v in sorted(profile.items(), key=lambda item: item[1], reverse=True))
    shensha = shensha_rows(computed)
    context = analysis_context(data, computed, strength, useful)
    annual = annual_rows(selected.getGanZhi() if selected else "", useful, context)
    monthly = monthly_rows(context)
    model = {
        "ec": ec,
        "chart": chart,
        "profile": profile,
        "analysis_context": context,
        "day_strength_label": label,
        "day_strength": strength,
        "useful_text": useful_text,
        "strength_reason": strength_reason,
        "useful_elements": useful,
        "dominant": dominant,
        "selected_dayun": selected.getGanZhi() if selected else "未识别",
        "dayun_rows": dayun_rows,
        "ten_god_rows": ten_god_rows(computed),
        "shensha_rows": shensha,
        "shensha_balance": {label: shensha_balance_text(label, rows) for label, rows in shensha.items()},
        "cross_shensha_balance": cross_shensha_balance(shensha),
        "branch_relation_rows": branch_relation_rows(computed),
        "wealth_tone": wealth_tone(strength, useful, ec, profile, context),
        "income_rows": income_probabilities(strength, useful, data, ec, profile, context),
        "income_stage_rows": income_stage_rows(useful, strength, annual),
        "annual_rows": annual,
        "monthly_rows": monthly,
        "flow_chart": flow_chart_model(computed, data.get("gender", "男"), useful, context),
        "relationship_rows": relationship_profile(data, useful, context, annual),
        "calibration_title": calibration_title,
        "calibration_lines": [
            f"出生时间来源：{data.get('timeSource') or '未填写'}；准确度：{data.get('timeAccuracy') or '未填写'}；真太阳时：{data.get('trueSolarTime') or '未填写'}。",
            f"出生地/当前城市：{data.get('birthPlace') or '未填写'} / {data.get('currentCity') or '未填写'}。",
            "已提供关键年份事件，以下只作为轻校准，不会覆盖命局、大运、流年结构。" if events else "未提供具体事件，因此不做事件校准，改用排盘边界与置信度校准。",
            "当前自动标准版以盘面、大运、流年为主，现实事件只作校准；若事件与盘面冲突，会在人工复核阶段下调相应结论置信度。",
        ],
    }
    model["career_rows"] = career_rows(data, model)
    model["crisis_rows"] = crisis_rows(context)
    model["june_2026_detail"] = june_2026_detail(context)
    model["event_calibration_rows"] = event_calibration_rows(events, model)
    return model


def load_font(size: int, bold: bool = False):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_standard_visuals(run_id: str, elements: list[str]) -> tuple[Path, Path]:
    colors_map = {"金": "#d8b35f", "水": "#73a9d8", "木": "#76b978", "火": "#d96b4d", "土": "#b89362"}
    useful_path = GENERATED / f"{run_id}-useful-gods.png"
    crystal_path = GENERATED / f"{run_id}-crystals.png"
    font_big = load_font(120, True)
    font_mid = load_font(34)
    font_small = load_font(24)

    def center_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill: str) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2), text, font=font, fill=fill)

    img = PILImage.new("RGB", (1600, 920), "#080604")
    draw = ImageDraw.Draw(img)
    draw.rectangle((28, 28, 1572, 892), outline="#c7963f", width=4)
    draw.rectangle((58, 58, 1542, 862), outline="#3c2c12", width=2)
    draw.text((88, 82), "Ming Atelier · 喜用神", font=font_mid, fill="#f0c47a")
    draw.text((88, 132), "Five-element remedy sigils", font=font_small, fill="#8d7b58")
    for i, element in enumerate(elements[:2] or ["金", "水"]):
        cx = 450 + i * 700
        cy = 485
        color = colors_map.get(element, "#d8b35f")
        draw.ellipse((cx - 210, cy - 210, cx + 210, cy + 210), outline=color, width=5)
        draw.ellipse((cx - 140, cy - 140, cx + 140, cy + 140), outline=color, width=3)
        draw.line((cx, cy - 260, cx, cy + 260), fill=color, width=2)
        draw.arc((cx - 290, cy - 255, cx + 290, cy + 255), 22, 338, fill=color, width=3)
        draw.arc((cx - 260, cy - 290, cx + 260, cy + 290), 202, 158, fill=color, width=2)
        if element == "水":
            for offset in (-42, 0, 42):
                draw.arc((cx - 105, cy + offset, cx + 105, cy + 100 + offset), 190, 350, fill=color, width=4)
        elif element == "木":
            draw.line((cx, cy + 120, cx, cy - 125), fill=color, width=5)
            draw.line((cx, cy - 40, cx - 95, cy - 115), fill=color, width=4)
            draw.line((cx, cy - 15, cx + 95, cy - 95), fill=color, width=4)
        elif element == "火":
            draw.polygon([(cx, cy - 155), (cx - 88, cy + 105), (cx + 88, cy + 105)], outline=color)
            draw.line((cx, cy - 155, cx, cy + 120), fill=color, width=3)
        elif element == "土":
            draw.rectangle((cx - 112, cy - 112, cx + 112, cy + 112), outline=color, width=4)
            draw.line((cx - 145, cy + 130, cx + 145, cy + 130), fill=color, width=5)
        else:
            draw.line((cx - 125, cy - 125, cx + 125, cy + 125), fill=color, width=4)
            draw.line((cx + 125, cy - 125, cx - 125, cy + 125), fill=color, width=4)
        center_text(draw, (cx, cy), element, font_big, color)
        center_text(draw, (cx, 760), f"{element} · 五行补足", font_mid, "#f0c47a")
    img.save(useful_path)
    crystal = PILImage.new("RGB", (1600, 920), "#0b0906")
    draw = ImageDraw.Draw(crystal)
    draw.rectangle((28, 28, 1572, 892), outline="#c7963f", width=4)
    draw.rectangle((58, 58, 1542, 862), outline="#3c2c12", width=2)
    draw.text((88, 82), "Ming Atelier · 适配水晶", font=font_mid, fill="#f0c47a")
    draw.text((88, 132), "Crystal anchors for daily reminders", font=font_small, fill="#8d7b58")
    for i, row in enumerate(crystal_rows(elements[:2] or ["金", "水"])):
        element, name, fit, _ = row
        x = 160 + i * 700
        color = colors_map.get(element, "#d8b35f")
        draw.polygon([(x + 245, 260), (x + 390, 360), (x + 340, 620), (x + 150, 620), (x + 100, 360)], outline=color, fill="#151209")
        draw.line((x + 245, 260, x + 245, 620), fill=color, width=2)
        draw.line((x + 100, 360, x + 390, 360), fill=color, width=2)
        center_text(draw, (x + 245, 455), element, font_big, color)
        draw.text((x + 60, 690), f"{element}｜{name}", font=font_mid, fill=color)
        draw.text((x + 60, 740), fit[:18], font=font_small, fill="#e8d7b4")
    crystal.save(crystal_path)
    return useful_path, crystal_path


def pdf_table(rows, widths, font_name, font_size=7.2):
    wrapped = []
    cell_style = ParagraphStyle("tableCell", fontName=font_name, fontSize=font_size, leading=font_size + 3, wordWrap="CJK")
    header_style = ParagraphStyle("tableHead", parent=cell_style, textColor=colors.HexColor("#2b2111"))
    for index, row in enumerate(rows):
        style = header_style if index == 0 else cell_style
        wrapped.append([paragraph(cell, style) for cell in row])
    return table(wrapped, widths, font_name, font_size=font_size)


def html_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def html_detail_cards(rows_by_group: dict[str, list[list[str]]]) -> str:
    cards = []
    for group, rows in rows_by_group.items():
        items = "".join(
            f"<details class='star-detail'><summary>{html.escape(row[1])}<span>{html.escape(row[2])}</span></summary>"
            f"<p>{html.escape(row[3])}</p><p>{html.escape(row[4])}</p></details>"
            for row in rows
        )
        cards.append(f"<article class='card fade'><h3>{html.escape(group)}</h3>{items}</article>")
    return "<div class='grid two'>" + "".join(cards) + "</div>"


def html_shensha_tables(model: dict) -> str:
    parts = []
    for group, rows in model["shensha_rows"].items():
        detail = "".join(
            f"<details class='star-detail'><summary>{html.escape(row[1])}<span>{html.escape(row[2])}</span></summary>"
            f"<p>{html.escape(row[3])}</p><p>{html.escape(row[4])}</p></details>"
            for row in rows
        )
        parts.append(
            f"<article class='card shensha-block'><h3>{html.escape(group)}神煞</h3>"
            f"{html_table(['排名','神煞','强度','通用解释','在该柱代表什么'], rows)}"
            f"<p class='balance'>{html.escape(model['shensha_balance'][group])}</p>{detail}</article>"
        )
    parts.append(f"<article class='card'><h3>跨柱神煞制衡关系</h3><p>{html.escape(model['cross_shensha_balance'])}</p></article>")
    return "".join(parts)


def html_income_cards(model: dict) -> str:
    cards = []
    for tier, probability, amount, condition in model["income_rows"]:
        width = re.sub(r"\D", "", probability) or "0"
        cards.append(
            f"<article class='card income-band'><b>{html.escape(tier)}</b><strong>{html.escape(probability)}</strong>"
            f"<div class='bar-track'><span class='bar' style='--w:{width}%'></span></div>"
            f"<p>{html.escape(amount)}</p><p>{html.escape(condition)}</p></article>"
        )
    return "<div class='grid three'>" + "".join(cards) + "</div>"


def html_flow_chart(model: dict) -> str:
    flow = model["flow_chart"]
    intro = (
        f"<div class='card liupan-note'><b>流盘参照</b>"
        f"<p>生成时间：{html.escape(flow['reference'])}。当前大运为 {html.escape(flow['selected_dayun'])}，"
        f"流年为 {html.escape(flow['flow_year'])}，流月为 {html.escape(flow['flow_month'])}。"
        "MVP 版先用来观察本命四柱与大运、流年、流月的叠加关系；后续可继续扩展为可切换年份、月份的完整流盘。</p></div>"
    )
    return (
        intro
        + html_table(flow["headers"], flow["rows"])
        + "<div class='grid two'><article class='card'><h3>大运轨道</h3>"
        + html_table(["年龄段", "起始年", "大运", "状态"], flow["dayun_strip"])
        + "</article><article class='card'><h3>流年轨道</h3>"
        + html_table(["年份", "流年", "事业", "财运", "关系", "压力", "触发提示"], flow["annual_strip"])
        + "</article></div>"
        + "<article class='card'><h3>2026 流月轨道</h3>"
        + html_table(["月份", "流月", "节气", "事业", "财运", "风险", "提示"], flow["month_strip"])
        + "</article>"
    )


def html_chart_console(model: dict, chart_url: str) -> str:
    flow = model["flow_chart"]
    return (
        "<div class='chart-console'>"
        "<div class='chart-tabs' role='tablist'>"
        "<button class='active' data-chart-tab='natal'>本命排盘</button>"
        "<button data-chart-tab='flow'>流盘叠加</button>"
        "<button data-chart-tab='dayun'>大运</button>"
        "<button data-chart-tab='annual'>流年</button>"
        "<button data-chart-tab='monthly'>2026流月</button>"
        "</div>"
        f"<div class='chart-panel active' data-chart-panel='natal'><div class='chart'><img src='{chart_url}' alt='黑金命盘图'></div></div>"
        f"<div class='chart-panel' data-chart-panel='flow'><div class='card liupan-note'><b>流盘参照</b><p>生成时间：{html.escape(flow['reference'])}。当前大运 {html.escape(flow['selected_dayun'])}，流年 {html.escape(flow['flow_year'])}，流月 {html.escape(flow['flow_month'])}。此处把本命盘与当前运势叠在同一排盘控制台里看。</p></div>{html_table(flow['headers'], flow['rows'])}</div>"
        f"<div class='chart-panel' data-chart-panel='dayun'>{html_table(['年龄段', '起始年', '大运', '状态'], flow['dayun_strip'])}</div>"
        f"<div class='chart-panel' data-chart-panel='annual'>{html_table(['年份', '流年', '事业', '财运', '关系', '压力', '触发提示'], flow['annual_strip'])}</div>"
        f"<div class='chart-panel' data-chart-panel='monthly'>{html_table(['月份', '流月', '节气', '事业', '财运', '风险', '提示'], flow['month_strip'])}</div>"
        "</div>"
    )


def html_card_table(rows: list[list[str]], title_key: str = "主题") -> str:
    return "<div class='grid two'>" + "".join(
        f"<article class='card'><b>{html.escape(row[0])}</b><p>{html.escape(row[1])}</p><small>{html.escape(row[2])}</small></article>"
        for row in rows
    ) + "</div>"


def plain_summary_paragraphs(data: dict, model: dict) -> list[str]:
    useful = "、".join(model["useful_elements"]) or "节奏与边界"
    name = data.get("name") or "这张盘"
    industry = data.get("industry") or "未填写行业"
    role = data.get("role") or "未填写角色"
    ten_gods = "、".join(unique([row[0] for row in model["ten_god_rows"] if row[0] != "日主"])[:4]) or "日主结构"
    shensha = "、".join(unique([row[1] for rows in model["shensha_rows"].values() for row in rows if row[1] != "无明显主星"])[:4]) or "神煞辅助信号"
    risk_years = [row for row in model["annual_rows"] if int(row[6]) >= 7 or int(row[7]) >= 6 or int(row[9]) >= 7]
    money_years = [row for row in model["annual_rows"] if int(row[4]) >= 7]
    relation_windows = next((row[1] for row in model["relationship_rows"] if row[0] == "适合恋爱窗口"), "2028-2033")
    meet_window = next((row[1] for row in model["relationship_rows"] if row[0] == "最可能遇到时间"), "需结合大运流年细推")
    risk_text = "、".join(f"{row[0]}{row[1]}" for row in risk_years[:3]) or "2026-2027"
    money_text = "、".join(f"{row[0]}{row[1]}" for row in money_years[:5]) or "2028-2033"
    career_fit = "匹配度偏高" if any(word in (industry + role) for word in ["咨询", "品牌", "运营", "产品", "金融", "数据", "法务", "技术", "教育", "供应链", "研究"]) else "可以做，但需要主动往可沉淀、可复盘、可定价的部分靠拢"
    flags = [flag for flag in model["analysis_context"].get("risk_flags", []) if flag["key"] != "standard"]
    flag_text = "；".join(flag["text"] for flag in flags[:2])
    if flag_text:
        flag_text = f" 这张盘还触发了关键风控：{flag_text}"
    return [
        f"{name}这张盘的主题，不是被命盘推着走，而是要学会读懂自己的节奏，再决定怎么行动、怎么取舍、怎么顺势。日主判断为{model['day_strength_label']} {model['day_strength']}%，喜用落在{useful}。这里的喜用不是看五行缺什么就补什么，而是按月令、根气、透干、藏干、十神压力和大运触发共同判断。{flag_text} 所以人生里真正能托住你的，不是一次情绪很满的爆发，而是稳定的规则、稳定的专业、稳定的现金流，以及在关键时刻能让自己慢半拍的判断力。",
        f"性格上，十神里比较值得看的信号包括{ten_gods}，神煞里可参考{shensha}。这类组合通常不是“轻松躺赢”的类型，而是对环境、承诺、关系和资源质量很敏感：别人一句话可能会让你想很多，一个机会也容易让你同时看到希望和风险。好处是你不适合粗糙地活，只要方法论建立起来，就能把敏感变成洞察，把压力变成执行力；难处是不要总把所有责任先扛到自己身上，尤其在合作、感情和金钱问题上，要先看边界，再谈投入。",
        f"事业上，你现在填写的是“{industry} / {role}”，从命盘看当前方向{career_fit}。适合你的行业不是单纯热闹的赛道，而是能把经验沉淀为专业、流程、产品、咨询、运营、内容、数据、金融/法务/技术、供应链、教育训练或品牌方法论的路径。想增加机会，重点不是盲目扩大，而是把报价、合同、交付、复盘、客户筛选和现金流规则做出来；想规避风险，就要避开无账期、无退出、无责任人的合作，也不要为了证明自己能扛而接下过大的承诺。",
        f"财运上，{model['wealth_tone']['base']} 未来十年里，比较适合努力搞钱的窗口集中在{money_text}，这些年份更适合谈客户、提价、收账、做产品化、做长期合作；风险较高的年份要重点看{risk_text}，尤其是合冲刑害、财官压力、比劫分利或现金流压力被引动的阶段，容易先答应、后核算，或者因为情面、面子、兴奋感而扩大成本。你不是不能冲，而是每一次冲之前都要有预算、合同、复盘和止损线。",
        f"感情上，适合恋爱或关系推进的窗口可优先看{relation_windows}；最可能遇到或明显推进的阶段，目前自动模型给到的是{meet_window}。这不是说其他时间没有缘分，而是这些窗口更容易出现能谈现实、谈规则、谈未来安排的人。比较适合你的关系，不是强刺激、强拉扯、强消耗，而是对方能尊重你的节奏，也愿意一起把钱、时间、城市、家庭责任讲清楚。若要看结婚，建议优先观察 2028-2033 之间能否出现稳定对象与现实条件同步成熟；如果关系长期只给情绪不给行动，就不要用等待消耗自己的运势。",
    ]


def report_plain_summary(data: dict, model: dict) -> str:
    return "\n\n".join(plain_summary_paragraphs(data, model))


def deep_report_pdf(data: dict, computed: dict, chart_png: Path, output: Path) -> None:
    model = report_model(data, computed)
    useful_img, crystal_img = generate_standard_visuals(output.stem, model["useful_elements"])
    font = register_font()
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("deepTitle", parent=base["Title"], fontName=font, fontSize=23, leading=31, alignment=1, wordWrap="CJK"),
        "sub": ParagraphStyle("deepSub", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=14, alignment=1, textColor=colors.HexColor("#666666"), wordWrap="CJK"),
        "h1": ParagraphStyle("deepH1", parent=base["Heading1"], fontName=font, fontSize=14.5, leading=21, spaceBefore=12, spaceAfter=8, wordWrap="CJK"),
        "body": ParagraphStyle("deepBody", parent=base["BodyText"], fontName=font, fontSize=9, leading=14, spaceAfter=5, wordWrap="CJK"),
        "note": ParagraphStyle("deepNote", parent=base["BodyText"], fontName=font, fontSize=8.2, leading=12, backColor=colors.HexColor("#fff6df"), borderColor=colors.HexColor("#ead69d"), borderWidth=0.4, borderPadding=6, textColor=colors.HexColor("#6d541d"), wordWrap="CJK"),
    }
    ec = model["ec"]
    pillars = f"{ec.getYear()} 年｜{ec.getMonth()} 月｜{ec.getDay()} 日｜{ec.getTime()} 时"
    story = [
        paragraph(f"{data.get('name') or '匿名'}命理报告", styles["title"]),
        paragraph(f"{data.get('calendar', '阳历')} {data.get('birthDate')} {data.get('birthTime')}｜{data.get('birthPlace', '')}｜{data.get('gender', '')}", styles["sub"]),
        Spacer(1, 8),
        paragraph("本报告按 Ming Atelier 标准化结构生成：以原始盘、大运流年、十神、神煞、地支关系和现实问卷为基础，输出可复核的命理阅读。自动版用于客测交付，后续可叠加人工校准。", styles["note"]),
        Spacer(1, 10),
        Image(str(chart_png), width=135 * mm, height=205 * mm),
        PageBreak(),
    ]
    story.extend([
        paragraph("一、原始盘信息", styles["h1"]),
        pdf_table([
            ["项目", "内容"],
            ["四柱", pillars],
            ["日主", f"{ec.getDayGan()}｜{model['day_strength_label']}｜{model['day_strength']}%"],
            ["当前/2026大运", model["selected_dayun"]],
            ["五行估计", model["dominant"]],
            ["地支关系", "；".join(computed["chart"].get("relations") or [])],
        ], [35 * mm, 135 * mm], font),
        paragraph("二、分析：格局与用神体系", styles["h1"]),
        paragraph(model["strength_reason"], styles["body"]),
        paragraph(model["useful_text"], styles["body"]),
        pdf_table([["喜用", "行为落地"]] + [[e, element_behavior(e)] for e in model["useful_elements"]], [28 * mm, 142 * mm], font),
        paragraph("三、事业发展", styles["h1"]),
        pdf_table([["主题", "判断", "依据"]] + model["career_rows"], [30 * mm, 70 * mm, 70 * mm], font, 6.8),
        paragraph("四、未来十年财运与收入层级", styles["h1"]),
        paragraph(model["wealth_tone"]["base"], styles["body"]),
        pdf_table([["层级", "概率", "金额", "条件"]] + model["income_rows"], [24 * mm, 18 * mm, 38 * mm, 90 * mm], font, 6.8),
        pdf_table([["阶段", "收入判断", "关键条件", "风险"]] + model["income_stage_rows"], [26 * mm, 38 * mm, 58 * mm, 48 * mm], font, 6.6),
        pdf_table([["年份", "流年", "大运", "事业", "财运", "感情", "健康/压力", "破财", "家宅", "合规", "触发与行动规则"]] + model["annual_rows"], [12 * mm, 14 * mm, 16 * mm, 8 * mm, 8 * mm, 8 * mm, 13 * mm, 8 * mm, 8 * mm, 8 * mm, 75 * mm], font, 5.2),
        paragraph("五、感情运势", styles["h1"]),
        pdf_table([["主题", "判断", "说明"]] + model["relationship_rows"], [35 * mm, 48 * mm, 87 * mm], font, 6.8),
        paragraph("六、2026 年单独流月拆解", styles["h1"]),
        paragraph(model["june_2026_detail"], styles["note"]),
        pdf_table([["月份", "月柱", "节气", "事业", "财运", "关系", "风险", "行动建议"]] + model["monthly_rows"], [18 * mm, 16 * mm, 28 * mm, 13 * mm, 13 * mm, 13 * mm, 13 * mm, 56 * mm], font, 6.0),
        paragraph("七、核心限制与潜在危机", styles["h1"]),
        pdf_table([["风险", "表现", "控制方式"]] + model["crisis_rows"], [28 * mm, 72 * mm, 70 * mm], font, 6.8),
        paragraph("八、大白话总结", styles["h1"]),
    ])
    for item in plain_summary_paragraphs(data, model):
        story.append(paragraph(item, styles["body"]))
    story.extend([
        paragraph("九、十神分析", styles["h1"]),
        pdf_table([["十神", "柱(干/支)", "通用解释", "判断"]] + model["ten_god_rows"], [22 * mm, 34 * mm, 52 * mm, 62 * mm], font, 6.8),
        paragraph("十神制衡关系：外显天干决定可见行为，地支藏干决定暗线动机。判断时不能只看一个十神，要看它在年、月、日、时四个位置分别作用于圈层、事业、自我关系和长期项目。", styles["body"]),
        paragraph("地支关系制衡", styles["body"]),
        pdf_table([["关系", "结构提示", "可能影响", "现实制化"]] + model["branch_relation_rows"], [34 * mm, 43 * mm, 48 * mm, 45 * mm], font, 6.8),
        paragraph("十、神煞体系", styles["h1"]),
    ])
    for group, rows in model["shensha_rows"].items():
        story.append(paragraph(group, styles["body"]))
        story.append(pdf_table([["排名", "神煞", "强度", "通用解释", "在该柱代表什么"]] + rows, [14 * mm, 24 * mm, 18 * mm, 58 * mm, 56 * mm], font, 6.6))
        story.append(paragraph(model["shensha_balance"][group], styles["body"]))
        story.append(Spacer(1, 5))
    story.extend([
        paragraph(model["cross_shensha_balance"], styles["body"]),
        paragraph("十一、喜用神与五行补足", styles["h1"]),
        Image(str(useful_img), width=170 * mm, height=96 * mm),
        paragraph("十二、适配水晶建议", styles["h1"]),
        Image(str(crystal_img), width=170 * mm, height=96 * mm),
        pdf_table([["五行", "建议", "适配点", "使用方式"]] + crystal_rows(model["useful_elements"]), [18 * mm, 38 * mm, 54 * mm, 60 * mm], font, 6.8),
    ])
    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    doc.build(story)


def deep_report_html(data: dict, computed: dict, chart_png: Path, output: Path) -> None:
    model = report_model(data, computed)
    useful_img, crystal_img = generate_standard_visuals(output.stem, model["useful_elements"])
    ec = model["ec"]
    raw_title = f"{data.get('name') or '匿名'}命理报告"
    title = html.escape(raw_title)
    chart_url = f"/generated/{chart_png.name}"
    useful_url = f"/generated/{useful_img.name}"
    crystal_url = f"/generated/{crystal_img.name}"
    sections = [
        ("raw", "原始盘信息"),
        ("pattern", "格局与用神"),
        ("career", "事业发展"),
        ("wealth", "未来十年财运"),
        ("relationship", "感情运势"),
        ("monthly", "2026流月"),
        ("crisis", "核心危机"),
        ("summary", "大白话总结"),
        ("ten-god", "十神分析"),
        ("shensha", "神煞体系"),
        ("elements", "喜用神"),
        ("crystals", "适配水晶"),
    ]
    nav = "".join(f"<a href='#{sid}'>{html.escape(label)}</a>" for sid, label in sections)
    relation_text = "；".join(computed["chart"].get("relations") or [])
    risk_year = max(model["annual_rows"], key=lambda row: int(row[6]) + int(row[7]) + int(row[9]))
    useful_text = "、".join(model["useful_elements"]) or "节奏"
    kpis = [
        ["身强估计", f"{model['day_strength_label']} {model['day_strength']}%", model["strength_reason"]],
        ["核心喜用", useful_text, model["useful_text"]],
        ["当前大运", model["selected_dayun"], "以 2026 所在大运为基准，所有流年判断均需与大运叠加。"],
        ["风险最高年", f"{risk_year[0]} {risk_year[1]}", risk_year[10]],
    ]
    kpi_html = "".join(f"<div class='kpi'><span>{html.escape(k[0])}</span><b>{html.escape(k[1])}</b><p>{html.escape(k[2])}</p></div>" for k in kpis)
    monthly_html = "".join(
        f"<article class='month'><i></i><b>{html.escape(row[0])}｜{html.escape(row[1])}</b><em>{html.escape(row[2])}</em>"
        f"<p>{html.escape(row[7])}</p><small>事业 {row[3]} / 财运 {row[4]} / 关系 {row[5]} / 风险 {row[6]}</small></article>"
        for row in model["monthly_rows"]
    )
    chart_console = html_chart_console(model, chart_url)
    summary_html = "".join(f"<p>{html.escape(item)}</p>" for item in plain_summary_paragraphs(data, model))
    output.write_text(f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><link rel="stylesheet" href="/pages.css">
<style>
	body{{background:#080604;color:#f7ead2}}.scroll-progress{{position:fixed;top:0;left:0;height:3px;background:#d8b35f;z-index:80;width:0}}.report-nav{{position:sticky;top:70px;z-index:20;background:rgba(8,6,4,.9);backdrop-filter:blur(12px);border-block:1px solid rgba(216,179,95,.22);overflow:auto;white-space:nowrap}}.report-nav .shell{{display:flex;gap:18px;padding:12px 20px}}.report-nav a{{color:#e8d7b4;text-decoration:none;font-size:13px}}.hero{{min-height:82vh;display:grid;align-items:center;padding:98px 0 56px;background:radial-gradient(circle at 50% 18%,rgba(216,179,95,.24),transparent 34%),linear-gradient(180deg,#0d0905,#080604);position:relative;overflow:hidden}}.hero:before{{content:"命";position:absolute;right:7vw;top:10vh;font-size:34vw;line-height:1;color:rgba(216,179,95,.07);animation:breathe 6s ease-in-out infinite}}.hero h1{{font-size:56px;line-height:1.08;max-width:760px;color:#f7ead2}}.lead{{max-width:760px;color:#e8d7b4}}.hero-actions{{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}}.print-btn{{border:1px solid rgba(216,179,95,.5);background:#d8b35f;color:#090604;border-radius:6px;padding:12px 18px;text-decoration:none;font-weight:700;cursor:pointer}}.panel{{max-width:1160px;margin:0 auto;padding:46px 20px;border-top:1px solid rgba(216,179,95,.2)}}.panel h2{{color:#f0c47a;font-size:28px}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}.grid.two{{grid-template-columns:repeat(2,minmax(0,1fr))}}.grid.three{{grid-template-columns:repeat(3,minmax(0,1fr))}}.card,.kpi{{border:1px solid rgba(216,179,95,.28);background:rgba(20,15,8,.72);border-radius:8px;padding:18px;box-shadow:0 18px 44px rgba(0,0,0,.18);transition:transform .25s ease,border-color .25s ease}}.card:hover,.kpi:hover{{transform:translateY(-3px);border-color:rgba(240,196,122,.58)}}.kpi b{{display:block;color:#f0c47a;font-size:25px;line-height:1.2;margin:8px 0}}.kpi p,.card small{{color:#cdbb98}}.chart-console{{margin-top:22px;border:1px solid rgba(216,179,95,.3);border-radius:8px;background:rgba(12,9,5,.82);padding:14px}}.chart-tabs{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}}.chart-tabs button{{border:1px solid rgba(216,179,95,.35);background:rgba(216,179,95,.08);color:#e8d7b4;border-radius:6px;padding:9px 12px;cursor:pointer;font:inherit;white-space:nowrap}}.chart-tabs button.active{{background:#d8b35f;color:#090604}}.chart-panel{{display:none}}.chart-panel.active{{display:block}}.table-wrap{{overflow:auto;border:1px solid rgba(216,179,95,.22);border-radius:8px;margin-top:14px}}table{{border-collapse:collapse;width:100%;min-width:850px}}th,td{{border-bottom:1px solid rgba(216,179,95,.16);padding:11px 12px;text-align:left;vertical-align:top}}th{{color:#f0c47a;background:rgba(216,179,95,.08)}}td{{color:#ead9b7}}tr:hover td{{background:rgba(216,179,95,.05)}}.chart{{max-width:620px;margin:22px auto;animation:softGlow 4s ease-in-out infinite}}.chart img,.god-art img{{width:100%;height:auto;object-fit:contain;border:1px solid rgba(216,179,95,.35);border-radius:8px}}.god-art{{animation:lineDrift 5s ease-in-out infinite}}.bar-track{{height:10px;border-radius:99px;background:rgba(216,179,95,.13);overflow:hidden;margin:12px 0}}.bar{{display:block;height:100%;width:var(--w);border-radius:99px;background:linear-gradient(90deg,#d8b35f,#8f6a2a);animation:barGrow 1.2s ease both}}.income-band b,.warning b{{color:#f0c47a}}.income-band strong{{display:block;font-size:28px;color:#f7ead2;margin-top:8px}}.balance{{color:#dcc796}}details.star-detail{{border-top:1px solid rgba(216,179,95,.18);padding:10px 0}}details.star-detail summary{{cursor:pointer;color:#f0c47a}}details.star-detail summary span{{float:right;color:#d8b35f}}.timeline{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}.month{{position:relative;border:1px solid rgba(216,179,95,.22);border-radius:8px;padding:16px 16px 16px 42px;background:rgba(20,15,8,.65)}}.month i{{position:absolute;left:16px;top:22px;width:10px;height:10px;border-radius:50%;background:#d8b35f;box-shadow:0 0 0 0 rgba(216,179,95,.5);animation:pulse 2.2s infinite}}.month b,.month em{{display:block;color:#f0c47a;font-style:normal}}.fade{{opacity:0;transform:translateY(18px);transition:opacity .7s ease,transform .7s ease}}.fade.show{{opacity:1;transform:none}}footer{{padding:34px 20px;color:#9f8d6b}}@keyframes breathe{{50%{{transform:scale(1.04);opacity:.8}}}}@keyframes softGlow{{50%{{filter:drop-shadow(0 0 22px rgba(216,179,95,.26))}}}}@keyframes barGrow{{from{{width:0}}to{{width:var(--w)}}}}@keyframes pulse{{70%{{box-shadow:0 0 0 12px rgba(216,179,95,0)}}100%{{box-shadow:0 0 0 0 rgba(216,179,95,0)}}}}@keyframes lineDrift{{50%{{transform:translateY(-7px)}}}}@media(max-width:760px){{.hero h1{{font-size:38px}}.grid,.grid.two,.grid.three,.timeline{{grid-template-columns:1fr}}.report-nav{{top:64px}}table{{min-width:760px}}.chart-tabs button{{flex:1 1 31%;font-size:13px}}}}
	</style></head>
		<body><header class="top"><nav class="shell nav"><a class="brand" href="/"><img src="/assets/ming-four-pillars-mark.png"><span>Ming Atelier<small>命理工坊</small></span></a><div class="links"><a href="/">首页</a><a href="/questionnaire.html">问卷</a><a href="/divination.html">起卦</a></div></nav></header>
		<div class="scroll-progress" id="scrollProgress"></div><main>
	<section class="hero"><div class="shell fade"><p class="eyebrow">Ming Atelier · Eastern Destiny Readings</p><h1>{title}</h1><p class="lead">以八字四柱为底图，读性格、节奏、选择与关系。关于你如何行动、如何取舍、如何顺势。</p><div class="hero-actions"><button class="print-btn" onclick="window.print()">保存 PDF</button><a class="print-btn" href="/">回到主页</a></div></div></section><nav class="report-nav"><div class="shell">{nav}</div></nav>
	<section class="panel fade" id="raw"><h2>原始盘信息</h2><div class="grid">{kpi_html}</div>{chart_console}{html_table(["项目","内容"], [["四柱", f"{ec.getYear()} 年｜{ec.getMonth()} 月｜{ec.getDay()} 日｜{ec.getTime()} 时"], ["五行估计", model["dominant"]], ["地支关系", relation_text]])}</section>
	<section class="panel fade" id="pattern"><h2>格局与用神体系</h2><div class="card"><p>{html.escape(model["strength_reason"])}</p><p>{html.escape(model["useful_text"])}</p></div>{html_table(["喜用","行为落地"], [[e, element_behavior(e)] for e in model["useful_elements"]])}</section>
	<section class="panel fade" id="career"><h2>事业发展</h2>{html_card_table(model["career_rows"])}</section>
	<section class="panel fade" id="wealth"><h2>未来十年财运与收入层级</h2><div class="card"><p>{html.escape(model["wealth_tone"]["base"])}</p></div>{html_income_cards(model)}{html_table(["阶段","收入判断","关键条件","风险"], model["income_stage_rows"])}{html_table(["年份","流年","大运","事业","财运","感情","健康/压力","破财","家宅","合规","触发与行动规则"], model["annual_rows"])}</section>
	<section class="panel fade" id="relationship"><h2>感情运势</h2>{html_table(["主题","判断","说明"], model["relationship_rows"])}</section>
	<section class="panel fade" id="monthly"><h2>2026 年单独流月拆解</h2><div class="card warning"><b>6 月甲午重点提示</b><p>{html.escape(model["june_2026_detail"])}</p></div><div class="timeline">{monthly_html}</div></section>
	<section class="panel fade" id="crisis"><h2>核心限制与潜在危机</h2>{html_card_table(model["crisis_rows"])}</section>
	<section class="panel fade" id="summary"><h2>大白话总结</h2><div class="card">{summary_html}</div></section>
	<section class="panel fade" id="ten-god"><h2>十神分析</h2>{html_table(["十神","柱(干/支)","通用解释","判断"], model["ten_god_rows"])}<div class="grid two"><article class="card"><b>十神制衡关系</b><p>外显天干决定可见行为，地支藏干决定暗线动机。判断时不能只看一个十神，要看它在年、月、日、时四个位置分别作用于圈层、事业、自我关系和长期项目。</p></article><article class="card"><b>地支合冲与大盘制化</b>{html_table(["关系","盘面含义","对大盘影响","制化/化解方式"], model["branch_relation_rows"])}</article></div></section>
	<section class="panel fade" id="shensha"><h2>神煞体系</h2>{html_shensha_tables(model)}</section>
	<section class="panel fade elements" id="elements"><h2>喜用神</h2><div class="god-art"><img src="{useful_url}" alt="喜用神图"></div>{html_table(["喜用","行为落地"], [[e, element_behavior(e)] for e in model["useful_elements"]])}</section>
	<section class="panel fade" id="crystals"><h2>适配水晶建议</h2><div class="god-art"><img src="{crystal_url}" alt="适配水晶图"></div>{html_table(["五行","建议","适配点","使用方式"], crystal_rows(model["useful_elements"]))}</section></main>
	<footer class="shell">Ming Atelier｜命理工坊。自动标准版用于客测交付，关键人生决策建议叠加人工复核。</footer><script>const p=document.getElementById('scrollProgress');addEventListener('scroll',()=>{{const h=document.documentElement; p.style.width=((h.scrollTop)/(h.scrollHeight-h.clientHeight)*100)+'%';}});const io=new IntersectionObserver(es=>es.forEach(e=>e.isIntersecting&&e.target.classList.add('show')),{{threshold:.14}});document.querySelectorAll('.fade').forEach(el=>io.observe(el));document.querySelectorAll('[data-chart-tab]').forEach(btn=>btn.addEventListener('click',()=>{{const target=btn.dataset.chartTab;document.querySelectorAll('[data-chart-tab]').forEach(b=>b.classList.toggle('active',b===btn));document.querySelectorAll('[data-chart-panel]').forEach(panel=>panel.classList.toggle('active',panel.dataset.chartPanel===target));}}));</script></body></html>""", encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    def content_type_for(self, target: Path) -> str:
        return {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml; charset=utf-8",
        }.get(target.suffix.lower(), "application/octet-stream")

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/api/health":
            self.send_json({"ok": True, "service": "ming-atelier-mvp"})
            return
        if path == "/api/history":
            self.send_error(404)
            return
        if path == "/":
            target = STATIC / "index.html"
        elif path.startswith("/generated/"):
            target = GENERATED / path.removeprefix("/generated/")
        else:
            target = STATIC / path.lstrip("/")
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        content_type = self.content_type_for(target)
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/":
            target = STATIC / "index.html"
        elif path.startswith("/generated/"):
            target = GENERATED / path.removeprefix("/generated/")
        else:
            target = STATIC / path.lstrip("/")
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        content_type = self.content_type_for(target)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()

    def do_POST(self) -> None:
        if self.path not in {"/api/report", "/api/deep-report", "/api/divination"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/divination":
                result = build_divination(data)
                record_id = uuid.uuid4().hex[:10]
                append_record({
                    "id": record_id,
                    "type": "divination",
                    "createdAt": now_text(),
                    "title": data.get("question", "起卦"),
                    "input": data,
                    "result": result,
                })
                self.send_json({"ok": True, "recordId": record_id, "result": result})
                return
            required = ["gender", "birthDate", "birthTime", "birthPlace"]
            missing = [key for key in required if not data.get(key)]
            if missing:
                self.send_json({"error": f"缺少字段：{', '.join(missing)}"}, 400)
                return
            run_id = f"{safe_name(data.get('name') or 'anonymous')}-{uuid.uuid4().hex[:8]}"
            computed, chart_png = build_chart(data, run_id)
            if self.path == "/api/deep-report":
                report_slug = safe_name(f"{data.get('name') or '匿名'}命理报告")
                pdf_path = GENERATED / f"{report_slug}-{uuid.uuid4().hex[:6]}.pdf"
                html_path = GENERATED / f"{report_slug}-互动版-{uuid.uuid4().hex[:6]}.html"
                deep_report_pdf(data, computed, chart_png, pdf_path)
                deep_report_html(data, computed, chart_png, html_path)
                pdf_url = f"/generated/{pdf_path.name}"
                html_url = f"/generated/{html_path.name}"
                chart_url = f"/generated/{chart_png.name}"
                append_record({
                    "id": run_id,
                    "type": "deep-bazi",
                    "createdAt": now_text(),
                    "title": f"{data.get('name') or '匿名'}命理报告",
                    "input": data,
                    "pdfUrl": pdf_url,
                    "htmlUrl": html_url,
                    "chartUrl": chart_url,
                })
                self.send_json({"ok": True, "recordId": run_id, "pdfUrl": pdf_url, "htmlUrl": html_url, "chartUrl": chart_url})
                return
            pdf_path = GENERATED / f"{run_id}.pdf"
            report_pdf(data, computed, chart_png, pdf_path)
            pdf_url = f"/generated/{pdf_path.name}"
            chart_url = f"/generated/{chart_png.name}"
            append_record({
                "id": run_id,
                "type": "bazi",
                "createdAt": now_text(),
                "title": f"{data.get('name') or '匿名'}命理报告",
                "input": data,
                "pdfUrl": pdf_url,
                "chartUrl": chart_url,
            })
            self.send_json({"ok": True, "recordId": run_id, "pdfUrl": pdf_url, "chartUrl": chart_url})
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)


def main() -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    STATIC.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
