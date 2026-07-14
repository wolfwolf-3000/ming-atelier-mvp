from __future__ import annotations

import copy
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
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import parse_qs, unquote, urlparse

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
    "申子辰": {"桃花": "酉", "驿马": "寅", "华盖": "辰", "将星": "子", "劫煞": "巳", "灾煞": "午", "亡神": "亥"},
    "寅午戌": {"桃花": "卯", "驿马": "申", "华盖": "戌", "将星": "午", "劫煞": "亥", "灾煞": "子", "亡神": "巳"},
    "巳酉丑": {"桃花": "午", "驿马": "亥", "华盖": "丑", "将星": "酉", "劫煞": "寅", "灾煞": "卯", "亡神": "申"},
    "亥卯未": {"桃花": "子", "驿马": "巳", "华盖": "未", "将星": "卯", "劫煞": "申", "灾煞": "酉", "亡神": "寅"},
}
HONG_LUAN = {"子": "卯", "丑": "寅", "寅": "丑", "卯": "子", "辰": "亥", "巳": "戌", "午": "酉", "未": "申", "申": "未", "酉": "午", "戌": "巳", "亥": "辰"}
TIAN_XI = {"子": "酉", "丑": "申", "寅": "未", "卯": "午", "辰": "巳", "巳": "辰", "午": "卯", "未": "寅", "申": "丑", "酉": "子", "戌": "亥", "亥": "戌"}
GU_CHEN_GUA_SU = {
    "亥子丑": {"孤辰": "寅", "寡宿": "戌"},
    "寅卯辰": {"孤辰": "巳", "寡宿": "丑"},
    "巳午未": {"孤辰": "申", "寡宿": "辰"},
    "申酉戌": {"孤辰": "亥", "寡宿": "未"},
}
TIAN_YI_MONTH = {"寅": "丑", "卯": "寅", "辰": "卯", "巳": "辰", "午": "巳", "未": "午", "申": "未", "酉": "申", "戌": "酉", "亥": "戌", "子": "亥", "丑": "子"}
YUE_DE = {"寅": "丙", "午": "丙", "戌": "丙", "申": "壬", "子": "壬", "辰": "壬", "亥": "甲", "卯": "甲", "未": "甲", "巳": "庚", "酉": "庚", "丑": "庚"}
TIAN_DE = {"寅": "丁", "卯": "申", "辰": "壬", "巳": "辛", "午": "亥", "未": "甲", "申": "癸", "酉": "寅", "戌": "丙", "亥": "乙", "子": "巳", "丑": "庚"}
TEN_SPIRIT_DAYS = {"甲辰", "乙亥", "丙辰", "丁酉", "戊午", "庚戌", "庚寅", "辛亥", "壬寅", "癸未"}
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
GAN_CHONG = {"甲庚": "甲庚冲", "乙辛": "乙辛冲", "丙壬": "丙壬冲", "丁癸": "丁癸冲"}
SAN_HUI = {
    frozenset("亥子丑"): "亥子丑三会水局",
    frozenset("寅卯辰"): "寅卯辰三会木局",
    frozenset("巳午未"): "巳午未三会火局",
    frozenset("申酉戌"): "申酉戌三会金局",
}
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


def branch_group_mapping(branch: str, mapping: dict[str, dict[str, str]]) -> dict[str, str]:
    for group, items in mapping.items():
        if branch in group:
            return items
    return {}


def calculate_shensha(day_stem: str, day_branch: str, stem: str, branch: str, xunkong: str, year_branch: str, month_branch: str, day_ganzhi: str, pillar_label: str) -> list[str]:
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
    if branch == HONG_LUAN.get(year_branch):
        stars.append("红鸾")
    if branch == TIAN_XI.get(year_branch):
        stars.append("天喜")
    for star_name, star_branch in branch_group_mapping(year_branch, GU_CHEN_GUA_SU).items():
        if branch == star_branch:
            stars.append(star_name)
    if branch == TIAN_YI_MONTH.get(month_branch):
        stars.append("天医")
    if stem == YUE_DE.get(month_branch):
        stars.append("月德贵人")
    tian_de = TIAN_DE.get(month_branch)
    if stem == tian_de or branch == tian_de:
        stars.append("天德贵人")
    if pillar_label == "日柱" and day_ganzhi in TEN_SPIRIT_DAYS:
        stars.append("十灵日")
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
        personality = "思考偏理性，重效率、信息、规则和边界，遇到问题会先判断逻辑是否成立，再决定要不要投入。优势是能把复杂事情拆成流程，适合处理标准、数据、系统、资源调度和高压决策；需要留意的是，压力大时容易显得冷、慢热或过度自我保护。"
        industries = "数据分析、金融风控、供应链、跨境贸易、运营管理、咨询、技术产品、研究型岗位。"
    elif day_element in {"木", "火"}:
        personality = "表达和成长动能更明显，容易被目标、作品、曝光和人与人的互动推动。优势是有生命力、学习快、愿意尝试，也更容易靠表达、审美、影响力或行动速度打开局面；需要留意的是，情绪和节奏被外界牵动时，容易一时兴起投入过多。"
        industries = "教育培训、内容传播、品牌营销、产品增长、设计创意、管理培训、咨询服务。"
    else:
        personality = "稳定性和承接力较强，重现实结果、资源整合和长期积累。优势是能扛事、能落地，也愿意为长期目标投入时间；需要留意的是，有时会因为顾全大局而忽略自己的真实感受，或者在关系和责任里承担过多。"
        industries = "地产空间、项目管理、供应链、财务运营、人力行政、组织管理、传统行业升级。"
    return (
        f"这张命盘的日主是{day_stem}{day_element}，五行里目前以{dominant_text}最显眼。性格上不是单纯外放或单纯内向，"
        f"而是会先观察环境是否可靠、事情是否有结构、关系是否有边界，再决定要投入多少。{personality}"
        f"事业上，你当前填写的行业/角色是“{industry} / {role}”，从五行气质看，比较适合往{industries}"
        f"如果要做得更顺，关键不是追热点，而是把自己的专业、流程、交付标准和现金流规则固定下来。"
        f"感情上，{gender or '此盘'}看{spouse_logic}与日支状态，关系里最需要的是边界、节奏和现实责任感；"
        "如果一段关系长期让你在钱、时间、承诺或城市选择上反复消耗，就不适合硬拖。"
        "免费版只做排盘后的基础阅读，不展开大运、流年、正缘年份和深度风险细断。"
    )


def is_english(data: dict) -> bool:
    return str(data.get("lang") or data.get("language") or "").strip().lower() in {"en", "english"}


ELEMENT_EN = {"金": "Metal", "木": "Wood", "水": "Water", "火": "Fire", "土": "Earth"}
ELEMENT_COLOR = {"金": "#d8ad55", "木": "#78b46d", "水": "#6fa8dc", "火": "#d95642", "土": "#b88a4d"}
TEN_GOD_EN = {
    "比肩": "Peer / Self (比肩)",
    "劫财": "Rob Wealth / Competition (劫财)",
    "食神": "Eating God / Stable Output (食神)",
    "伤官": "Hurting Officer / Breakthrough Output (伤官)",
    "正财": "Direct Wealth / Stable Money (正财)",
    "偏财": "Indirect Wealth / Opportunity Money (偏财)",
    "正官": "Direct Officer / Rules and Status (正官)",
    "七杀": "Seven Killing / Pressure and Execution (七杀)",
    "正印": "Direct Resource / Learning and Protection (正印)",
    "偏印": "Indirect Resource / Insight and Models (偏印)",
    "日主": "Day Master (日主)",
}
TEN_GOD_TEXT_EN = {
    "比肩": "selfhood, peers, independence, and competitive awareness",
    "劫财": "shared resources, split interests, peer competition, and cash-flow volatility",
    "食神": "stable output, service quality, expression, and long-term reputation",
    "伤官": "rule-breaking expression, innovation, sales, visibility, and challenging authority",
    "正财": "stable income, clients, transactions, practical resources, and partner symbolism",
    "偏财": "opportunity money, resource integration, market sense, and project-based gains",
    "正官": "rules, responsibility, status, formal commitment, and partner symbolism",
    "七杀": "pressure, speed, competition, external constraint, risk, and execution",
    "正印": "learning, credentials, protection, institutional support, and recovery capacity",
    "偏印": "insight, models, unconventional knowledge, research, intuition, and solitude",
    "日主": "the central self, decision core, and action axis",
}
PILLAR_EN = {"年柱": "Year Pillar", "月柱": "Month Pillar", "日柱": "Day Pillar", "时柱": "Hour Pillar"}
PILLAR_SCENE_EN = {
    "年柱": "background, early environment, social field, and distant resources",
    "月柱": "career base, real-world field, supervisors, parents, and execution environment",
    "日柱": "self, spouse palace, intimate relationships, close resources, and personal decisions",
    "时柱": "long-term plans, future projects, children/subordinates, side ventures, and later development",
}
SHENSHA_TEXT_EN = {
    "天乙贵人": "Noble-person support: key helpers, institutions, professional resources, or protective support.",
    "天德贵人": "Virtue star: softens conflict consequences, but does not cancel practical risk.",
    "月德贵人": "Monthly virtue: repair, mediation, and damage control.",
    "文昌贵人": "Writing and learning star: documents, exams, contracts, expression, and professional communication.",
    "桃花": "Peach Blossom: attraction, social visibility, charm, emotional movement, and relationship activation.",
    "学堂": "Formal learning, training, credentials, and verifiable skill.",
    "国印": "Institutional authority, official process, credentials, and formal identity.",
    "福星贵人": "Resource buffer, ease, support, and life comfort.",
    "太极贵人": "Pattern recognition, metaphysics/philosophy, abstract thinking, and system study.",
    "将星": "Leadership, command, management, and execution.",
    "红鸾": "Romantic activation, closeness, social warmth, and relationship opportunity.",
    "天喜": "Joy, relationship movement, emotional warmth, and pleasant cooperation.",
    "十灵日": "Sensitivity, intuition, quick perception, expression, and creative responsiveness.",
    "羊刃": "Sharp execution, competition, conflict potential, and the need for clear rules.",
    "禄神": "Stable income, position resources, skill base, and sustainable support.",
    "驿马": "Movement, travel, relocation, logistics, market mobility, and expansion.",
    "华盖": "Research, art, metaphysics, aesthetics, solitude, and professional depth.",
    "金舆": "Comfort, resources, vehicles, social presentation, and quality of life.",
    "天医": "Repair, care, health awareness, healing resources, and problem recovery.",
    "孤辰": "Independence, distance, self-processing, and slower relationship rhythm.",
    "寡宿": "Emotional reserve, solitude, slower intimacy, and distance in closeness.",
    "劫煞": "Sudden competition, resource interruption, external shock, and volatility.",
    "亡神": "Hidden pressure, unseen consumption, judgment gaps, and implicit constraints.",
    "空亡": "Emptiness, delay, reduced fulfillment, or unstable delivery.",
    "灾煞": "Obstruction, disruption, external interference, and caution signal.",
    "童子": "Sensitivity, distance, unconventional preference, or unusual relationship rhythm; read conservatively.",
}
STEM_EN = {
    "甲": "Jia Wood", "乙": "Yi Wood", "丙": "Bing Fire", "丁": "Ding Fire", "戊": "Wu Earth",
    "己": "Ji Earth", "庚": "Geng Metal", "辛": "Xin Metal", "壬": "Ren Water", "癸": "Gui Water",
}
BRANCH_EN = {
    "子": "Zi Water", "丑": "Chou Earth", "寅": "Yin Wood", "卯": "Mao Wood", "辰": "Chen Earth", "巳": "Si Fire",
    "午": "Wu Fire", "未": "Wei Earth", "申": "Shen Metal", "酉": "You Metal", "戌": "Xu Earth", "亥": "Hai Water",
}
BRANCH_STAGE_EN = {
    "长生": "Growth", "沐浴": "Bath", "冠带": "Crowning", "临官": "Official", "帝旺": "Peak",
    "衰": "Decline", "病": "Illness", "死": "Death", "墓": "Tomb", "绝": "Severance", "胎": "Conception", "养": "Nurture",
}
SOLAR_TERM_EN = {
    "立春-惊蛰": "Start of Spring - Awakening of Insects",
    "惊蛰-清明": "Awakening of Insects - Clear and Bright",
    "清明-立夏": "Clear and Bright - Start of Summer",
    "立夏-芒种": "Start of Summer - Grain in Ear",
    "芒种-小暑": "Grain in Ear - Minor Heat",
    "小暑-立秋": "Minor Heat - Start of Autumn",
    "立秋-白露": "Start of Autumn - White Dew",
    "白露-寒露": "White Dew - Cold Dew",
    "寒露-立冬": "Cold Dew - Start of Winter",
    "立冬-大雪": "Start of Winter - Major Snow",
    "大雪-小寒": "Major Snow - Minor Cold",
    "小寒-立春": "Minor Cold - Start of Spring",
}
NAYIN_EN = {
    "海中金": "Metal in the Sea", "炉中火": "Fire in the Furnace", "大林木": "Great Forest Wood", "路旁土": "Roadside Earth", "剑锋金": "Sword-Edge Metal",
    "山头火": "Fire on the Mountain", "涧下水": "Stream Water", "城头土": "City Wall Earth", "白蜡金": "White Wax Metal", "杨柳木": "Willow Wood",
    "泉中水": "Spring Water", "屋上土": "Roof Earth", "霹雳火": "Thunder Fire", "松柏木": "Pine-Cypress Wood", "长流水": "Long Flowing Water",
    "砂中金": "Sand Metal", "沙中金": "Sand Metal", "山下火": "Fire Below Mountain", "平地木": "Flatland Wood", "壁上土": "Wall Earth", "金箔金": "Gold Foil Metal",
    "佛灯火": "Lamp Fire", "覆灯火": "Covered Lamp Fire", "天河水": "Milky Way Water", "大驿土": "Post Station Earth", "钗钏金": "Hairpin Metal", "桑柘木": "Mulberry Wood",
    "大溪水": "Great Creek Water", "沙中土": "Sand Earth", "天上火": "Heavenly Fire", "石榴木": "Pomegranate Wood", "大海水": "Great Sea Water",
}
GENDER_EN = {"男": "male", "女": "female"}
TIME_SOURCE_EN = {
    "服务器当前时间": "server current time",
    "用户本地时间": "user local time",
    "浏览器起念时间": "browser-captured question time",
}
TRIGRAM_EN = {
    "乾": "Qian", "兑": "Dui", "离": "Li", "震": "Zhen",
    "巽": "Xun", "坎": "Kan", "艮": "Gen", "坤": "Kun",
}


def element_en(value: str) -> str:
    return ELEMENT_EN.get(value, value or "")


def solar_term_en(value: str) -> str:
    return SOLAR_TERM_EN.get(value, value or "")


def ganzhi_en(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] in STEM_EN and text[1] in BRANCH_EN:
        return f"{STEM_EN[text[0]]} / {BRANCH_EN[text[1]]}"
    return ""


def bilingual_ganzhi(value: str) -> str:
    text = str(value or "").strip()
    en = ganzhi_en(text)
    if en:
        return f"{text}\n{en}"
    if text == "未识别":
        return "未识别\nNot identified"
    return text


def bilingual_branch_set(value: str) -> str:
    text = str(value or "").strip()
    if not text or text in {"None", "无", "未识别"}:
        return {"None": "None", "无": "无\nNone", "未识别": "未识别\nNot identified"}.get(text, text)
    translated = []
    for char in text:
        if char in BRANCH_EN:
            translated.append(BRANCH_EN[char])
    return f"{text}\n{' / '.join(translated)}" if translated else text


def bilingual_pillars(ec) -> str:
    parts = [
        ("Year", ec.getYear()),
        ("Month", ec.getMonth()),
        ("Day", ec.getDay()),
        ("Hour", ec.getTime()),
    ]
    return " | ".join(f"{value} {label}\n{ganzhi_en(value)}" for label, value in parts)


def branch_relation_en(text: str) -> str:
    relation_words = {"冲": "clash", "刑": "punishment", "害": "harm", "破": "break", "合": "combination", "伏吟": "repetition"}
    source = str(text or "").replace("地支冲刑害破：", "").replace("Branch interactions:", "").strip()
    if not source:
        return ""
    translated = []
    for item in re.split(r"[；;、,\s]+", source):
        if not item:
            continue
        branches = [BRANCH_EN.get(char, char) for char in item if char in BRANCH_EN]
        relation = next((en for cn, en in relation_words.items() if cn in item), "")
        if branches or relation:
            translated.append(" ".join(branches + ([relation] if relation else [])))
    return "; ".join(translated)


def bilingual_branch_relation_text(text: str) -> str:
    text = str(text or "")
    en = branch_relation_en(text)
    return f"{text}\n{en}" if en else text


def hidden_bilingual_plain(items: list[str] | str) -> str:
    if isinstance(items, str):
        items = [part.strip() for part in re.split(r"[/|、,]+", items) if part.strip()]
    cn_parts = []
    en_parts = []
    for item in items:
        stem, _, element = str(item).partition("·")
        cn_parts.append(str(item))
        en_parts.append(" / ".join(part for part in [STEM_EN.get(stem, ""), ELEMENT_EN.get(element, element if element else "")] if part))
    return f"{' / '.join(cn_parts)}\n{' / '.join(part for part in en_parts if part)}" if cn_parts else "None"


def bilingual_term_list(items: list[str] | str, mapping: dict[str, str], separator: str = " / ") -> str:
    if isinstance(items, str):
        items = [part.strip() for part in re.split(r"[、,|/]+", items) if part.strip()]
    if not items:
        return "None"
    cn = separator.join(str(item) for item in items)
    en = separator.join(short_en_name(str(item), mapping) for item in items if mapping.get(str(item)))
    return f"{cn}\n{en}" if en else cn


def bilingual_chart_cell(row_label: str, cell: str) -> str:
    text = str(cell or "")
    if text in {"None", "No dominant ShenSha", "Activated by timing overlay", "Not identified"}:
        return text
    if row_label == "Heavenly Stem" and text in STEM_EN:
        return f"{text}\n{STEM_EN[text]}"
    if row_label == "Earthly Branch" and text in BRANCH_EN:
        return f"{text}\n{BRANCH_EN[text]}"
    if row_label == "Hidden Stems":
        return hidden_bilingual_plain(text)
    if row_label in {"Main Star / Stem Ten-God", "Branch Ten-Gods"}:
        return bilingual_term_list(text, TEN_GOD_EN)
    if row_label == "NaYin":
        return bilingual_term_list([text], NAYIN_EN)
    if row_label == "Void Branches":
        return bilingual_branch_set(text)
    if row_label == "Growth Stage":
        return bilingual_term_list([text], BRANCH_STAGE_EN)
    if row_label == "ShenSha":
        return bilingual_term_list(text, SHENSHA_TEXT_EN)
    if len(text) >= 2 and text[0] in STEM_EN and text[1] in BRANCH_EN:
        return bilingual_ganzhi(text)
    return text


def element_behavior_en(element: str) -> str:
    return {
        "金": "boundaries, contracts, pricing, finance, audit, review, and asset awareness.",
        "水": "calm judgment, communication, data, mobility, pressure management, and cross-border flow.",
        "木": "learning, growth, content, education, product iteration, long-term planning, and network development.",
        "火": "expression, visibility, branding, sales, speed, warmth, and public influence.",
        "土": "execution, process, inventory, organization, risk control, trust, and long-term stability.",
    }.get(element, "rhythm, boundaries, and real-world calibration.")


def branch_relations_text_en(relations: list[str]) -> str:
    if not relations:
        return "No major branch interaction detected."
    text = "; ".join(relations)
    return text.replace("地支冲刑害破：", "Branch interactions: ").replace("无明显合冲刑害破", "No major combination/clash/punishment/harm/break detected").replace("；", "; ")


def crystal_rows_en(elements: list[str]) -> list[list[str]]:
    mapping = {
        "金": ["Clear Quartz / White Phantom", "clarity, pricing, contracts, review, and asset awareness", "Keep it near your desk, contracts, or accounting files as a reminder to calculate before deciding."],
        "水": ["Obsidian / Aquamarine", "cooling the mind, emotional regulation, communication, boundaries, and stress control", "Useful for negotiations or high-pressure conversations: pause before agreeing."],
        "木": ["Green Phantom / Aventurine", "learning, growth, long-term plans, recovery, and sustainable output", "Place it in a study or planning area to reinforce iteration over impulse."],
        "火": ["Red Agate / Garnet", "expression, visibility, action, sales, and ignition", "Use for presentations, interviews, launches, and communication; avoid emotional overdrive."],
        "土": ["Citrine / Tiger's Eye", "execution, organization, cash flow, inventory, and practical grounding", "Place it near finance, inventory, or project-management areas: rules before expansion."],
    }
    return [[element_en(e)] + mapping.get(e, ["Clear Quartz", "clarity and stability", "Use it as a daily action anchor."]) for e in elements]


def free_report_summary_en(data: dict, computed: dict) -> str:
    ec = computed["ec"]
    profile = computed["profile"]
    day_stem = ec.getDayGan()
    day_element = STEM_ELEMENT.get(day_stem, "")
    dominant = sorted(profile.items(), key=lambda item: item[1], reverse=True)[:2]
    dominant_text = ", ".join(f"{element_en(k)} {v}%" for k, v in dominant)
    industry = data.get("industry") or data.get("role") or "not specified"
    role = data.get("role") or "not specified"
    gender = data.get("gender", "")
    spouse_logic = "wealth star" if gender == "男" else "officer/killing star"
    if day_element in {"金", "水"}:
        personality = (
            "Your temperament leans rational, observant, and boundary-aware. You usually need a situation to make sense "
            "before you invest trust, money, or emotion. The advantage is strong judgment under pressure; the caution is "
            "that you may appear distant or overly self-protective when stressed."
        )
        industries = "data, finance, risk control, operations, consulting, technology products, research, compliance, and cross-border systems"
    elif day_element in {"木", "火"}:
        personality = (
            "Your chart carries more growth and expression drive. You are moved by goals, visibility, people, creative output, "
            "and momentum. The advantage is learning speed and initiative; the caution is that emotion or excitement can make "
            "you commit too much too early."
        )
        industries = "education, content, branding, marketing, product growth, design, management training, and advisory services"
    else:
        personality = (
            "Your chart shows stronger endurance and practical carrying capacity. You are suited to building things slowly, "
            "organizing resources, and staying with long cycles. The caution is taking on too much responsibility before your "
            "own needs are clearly protected."
        )
        industries = "project management, supply chain, finance operations, real estate, organizational management, HR, and traditional-industry upgrades"
    return (
        f"Your Day Master is {day_stem} ({STEM_EN.get(day_stem, day_element)}), with the most visible element balance around {dominant_text}. "
        f"{personality} Based on the industry and role you entered ({industry} / {role}), fields related to {industries} are generally easier "
        "to make productive, especially when your work has clear standards, repeatable delivery, and disciplined cash-flow rules. "
        f"In relationships, this chart reads through the {spouse_logic} and the spouse palace rather than a simple zodiac match. "
        "The key is rhythm, boundaries, and real responsibility. If a relationship repeatedly drains your time, money, promises, or location decisions, "
        "it should not be forced forward only because the attraction is strong. This free reading gives a first-layer personality, career, and relationship view; "
        "major luck cycles, year-by-year timing, soulmate windows, and deeper risk analysis belong in the deep report."
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
    year_branch = ec.getYearZhi()
    month_branch = ec.getMonthZhi()
    day_ganzhi = ec.getDay()
    pillars = []
    for label, prefix in zip(PILLAR_LABELS, ["Year", "Month", "Day", "Time"]):
        hidden = getattr(ec, f"get{prefix}HideGan")()
        shen = getattr(ec, f"get{prefix}ShiShenZhi")()
        stem = getattr(ec, f"get{prefix}Gan")()
        branch = getattr(ec, f"get{prefix}Zhi")()
        xunkong = getattr(ec, f"get{prefix}XunKong")()
        pillars.append(
            {
                "gan_shen": getattr(ec, f"get{prefix}ShiShenGan")(),
                "stem": stem,
                "branch": branch,
                "hidden": [f"{g}·{STEM_ELEMENT.get(g, '')}" for g in hidden],
                "zhi_shen": shen,
                "nayin": getattr(ec, f"get{prefix}NaYin")(),
                "kongwang": xunkong,
                "dishi": getattr(ec, f"get{prefix}DiShi")(),
                "zi_zuo": getattr(ec, f"get{prefix}DiShi")(),
                "shen_sha": calculate_shensha(day_stem, day_branch, stem, branch, xunkong, year_branch, month_branch, day_ganzhi, label),
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


def dayun_for_year(dayun_rows: list[list[str]], year: int | str, fallback: str = "未识别") -> str:
    try:
        target = int(year)
    except (TypeError, ValueError):
        return fallback
    for row in dayun_rows:
        if len(row) < 2 or "-" not in row[1]:
            continue
        start, end = row[1].split("-", 1)
        try:
            if int(start) <= target <= int(end):
                return row[0]
        except ValueError:
            continue
    return fallback


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


def clamp_int(value: int | float, low: int, high: int) -> int:
    return max(low, min(high, int(round(value))))


def normalize_local_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second or 0))


def divination_datetime(data: dict) -> tuple[datetime, str, str]:
    timezone_name = str(data.get("timezone") or data.get("timeZone") or "").strip()
    if data.get("divinationDate") and data.get("divinationTime"):
        data["divinationTime"] = normalize_time(data["divinationTime"])
        return datetime.fromisoformat(data["divinationDate"] + "T" + data["divinationTime"]), timezone_name, "用户填写时间"
    for key in ("divinationLocal", "clientLocalTime", "localTime"):
        parsed = normalize_local_datetime(data.get(key, ""))
        if parsed:
            return parsed, timezone_name, "浏览器起念时间"
    return datetime.now(), timezone_name, "服务器当前时间"


def divination_topic(question: str, background: str) -> str:
    text = question + " " + background
    text_lower = text.lower()
    topics = [
        ("健康/安全", ["健康", "身体", "手术", "病", "安全", "危险", "事故", "health", "surgery", "illness", "safety", "danger", "accident"]),
        ("感情/关系", ["感情", "恋爱", "复合", "分手", "结婚", "对象", "关系", "伴侣", "relationship", "dating", "love", "breakup", "marriage", "partner", "romantic"]),
        ("财务/投资", ["投资", "买", "卖", "钱", "收入", "财", "股票", "房", "资产", "investment", "invest", "money", "income", "stock", "asset", "property", "cash"]),
        ("事业/工作", ["工作", "跳槽", "面试", "升职", "老板", "公司", "事业", "职业", "offer", "岗位", "career", "job", "work", "interview", "promotion", "company", "role"]),
        ("学业/考试", ["考试", "申请", "学校", "学业", "录取", "论文", "证书", "exam", "school", "application", "admission", "thesis", "certificate"]),
        ("出行/迁移", ["出行", "旅行", "搬家", "搬迁", "出国", "签证", "航班", "迁移", "travel", "move", "relocation", "visa", "flight", "migration"]),
        ("合作/副业", ["合作", "合伙", "副业", "项目", "客户", "合同", "报价", "分账", "股权", "交付", "partnership", "partner", "side business", "side project", "project", "client", "contract", "equity", "delivery"]),
    ]
    best_label = "具体事项"
    best_score = 0
    for label, words in topics:
        score = sum(1 for word in words if word in text or word in text_lower)
        if score > best_score:
            best_label = label
            best_score = score
    return best_label


def has_any(text: str, words: list[str]) -> bool:
    return any(word and word in text for word in words)


def topic_score_adjustment(topic: str, relation: str, phase: str, question: str, background: str, omen: str) -> tuple[int, int, int, list[str]]:
    text = f"{question} {background}".lower()
    relation_scores = {
        "合作/副业": {"用生体": 6, "体克用": 4, "体用同气": 2, "体生用": -8, "用克体": -13},
        "感情/关系": {"用生体": 7, "体用同气": 3, "体克用": -3, "体生用": -7, "用克体": -11},
        "事业/工作": {"用生体": 7, "体克用": 5, "体用同气": 2, "体生用": -4, "用克体": -10},
        "财务/投资": {"用生体": 4, "体克用": 2, "体用同气": 0, "体生用": -10, "用克体": -15},
        "学业/考试": {"用生体": 6, "体克用": 4, "体用同气": 2, "体生用": -5, "用克体": -9},
        "出行/迁移": {"用生体": 5, "体克用": 2, "体用同气": 1, "体生用": -6, "用克体": -12},
        "健康/安全": {"用生体": 2, "体克用": -2, "体用同气": -1, "体生用": -8, "用克体": -16},
    }
    phase_scores = {
        "合作/副业": {"初段": 3, "中段": -5, "后段": -1},
        "感情/关系": {"初段": 1, "中段": -6, "后段": -3},
        "事业/工作": {"初段": 3, "中段": -3, "后段": 1},
        "财务/投资": {"初段": 0, "中段": -7, "后段": -2},
        "学业/考试": {"初段": 2, "中段": -2, "后段": 2},
        "出行/迁移": {"初段": 2, "中段": -5, "后段": -1},
        "健康/安全": {"初段": -2, "中段": -8, "后段": -4},
    }
    notes = []
    score = relation_scores.get(topic, {}).get(relation, -1) + phase_scores.get(topic, {}).get(phase, 0)
    risk = 0
    confidence = 0

    positive = ["明确", "已确认", "已签", "通过", "愿意", "稳定", "有预算", "已付款", "offer", "录取", "见过", "正在推进"]
    negative = ["没谈清", "不清楚", "拖延", "冷淡", "断联", "争吵", "隐瞒", "借钱", "高杠杆", "冲动", "临时", "反复"]
    if has_any(text, positive):
        score += 5
        confidence += 3
        notes.append("背景里已有明确推进信号，达成度上调")
    if has_any(text, negative):
        score -= 6
        risk += 1
        confidence += 2
        notes.append("背景里已有现实阻力，风险上调")

    if topic == "合作/副业":
        if has_any(text, ["口头", "资源很多", "没合同", "分账", "股权", "退出"]):
            score -= 5
            risk += 1
            notes.append("合作边界不清，先按高摩擦处理")
        if has_any(text, ["合同", "付款", "责任人", "交付范围", "试运行"]):
            score += 4
            notes.append("合作条件有落点，可小步验证")
    elif topic == "感情/关系":
        if has_any(text, ["断联", "冷淡", "分手", "暧昧", "不回复"]):
            score -= 6
            risk += 1
            notes.append("关系回应不足，不能只按情绪推进")
        if has_any(text, ["见面", "稳定", "承诺", "确定关系", "家人"]):
            score += 4
            notes.append("关系有现实承接点")
    elif topic == "事业/工作":
        if has_any(text, ["薪资", "汇报线", "岗位", "资源支持", "offer"]):
            score += 4
            notes.append("事业问题已有可核验条件")
        if has_any(text, ["裸辞", "不明确", "画饼", "试用", "裁员"]):
            score -= 5
            risk += 1
            notes.append("职业承诺与现实资源需复核")
    elif topic == "财务/投资":
        if has_any(text, ["借钱", "杠杆", "重仓", "短线", "保本", "高收益"]):
            score -= 9
            risk += 2
            notes.append("财务问题出现高风险关键词")
        if has_any(text, ["小额", "分批", "止损", "现金流", "退出"]):
            score += 4
            notes.append("已有风控设计，风险略降")
    elif topic == "健康/安全":
        risk += 2
        score -= 5
        notes.append("健康安全类问题不按高达成度处理，必须现实复核")

    omen_text = str(omen or "").strip()
    if omen_text and omen_text not in {"无", "没有", "none", "None"}:
        confidence += 4
        if has_any(omen_text, ["亮", "光", "金", "顺", "开", "喜", "清"]):
            score += 3
            notes.append("外应偏顺，作为小幅助力")
        if has_any(omen_text, ["碎", "黑", "堵", "吵", "破", "掉", "暗", "痛"]):
            score -= 3
            risk += 1
            notes.append("外应偏阻，作为小幅风险提示")

    return score, risk, confidence, notes[:4]


def divination_contextual_reading(topic: str, question: str, background: str, verdict: str, relation: str, phase: str) -> tuple[str, list[str], list[str]]:
    relation_hint = {
        "用生体": "外部条件有助力，但助力是否能落地，取决于对方承诺是否具体。",
        "体生用": "你会比较主动付出资源和精力，容易先投入、后等回报。",
        "体克用": "你有主动掌控空间，但也容易因为控制太急而让对方退缩。",
        "用克体": "外部压力压到自己身上，推进时要先判断成本是否已经超过收益。",
        "体用同气": "双方节奏相近，成败更取决于细节、时机和执行纪律。",
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
        risks = ["承诺内容和实际资源不匹配。", "上级或客户临时改需求，导致你承担额外成本。", "职业重大选择仍需结合现实 offer 和长期规划。"]
    elif topic == "财务/投资":
        reading = f"这卦落在财务/投资上，要先看风险暴露，而不是只看收益想象。{relation_hint}{phase_hint} 当前更适合小额验证、分批进入或先做尽调，不适合因为一时机会感而重仓。"
        advice = ["先设最大亏损线，不到条件不加码。", "确认流动性、退出方式和最坏情况。", "任何高收益承诺都要反向验证风险。"]
        risks = ["不要把卦象当投资建议或收益保证。", "高杠杆、借钱投入、短线追涨都应回避。", "重大金额必须做专业财务和法律核查。"]
    else:
        reading = f"这卦需要贴着你的问题看：{relation_hint}{phase_hint} 当前最重要的不是抽象判断吉凶，而是把问题拆成一个可验证动作，看对方/环境是否给出明确反馈。"
        advice = ["把问题缩小成一个具体动作和一个明确期限。", "先验证信息，再扩大投入。", "保留退出条件，不要把所有选择押在一次判断上。"]
        risks = ["问题越模糊，卦象可用度越低。", "现实反馈和卦象不一致时，以现实证据为先。", "重大事项需要专业意见和更多信息。"]
    return reading, advice, risks


def llm_divination_prompt(result: dict) -> list[dict[str, str]]:
    schema_note = {
        "reviewedVerdict": "可选。若原始判断与问题明显不匹配，可返回 吉/小吉/平/凶 之一。",
        "reviewedSuccess": "可选。0-100 的整数，原则上只在原始达成度上下 12 分内修正。",
        "reviewedRisk": "可选。1-10 的整数，原则上只在原始风险上下 2 分内修正。",
        "reviewedConfidence": "可选。0-100 的整数，按信息完整度修正。",
        "questionReading": "围绕用户具体问题写一段客户可读解读，必须引用本卦/互卦/变卦、体用关系、动爻阶段、达成度和风险。",
        "advice": ["3-5 条具体行动建议，每条都要能落地"],
        "riskPoints": ["3-5 条风险提醒，必须贴合用户问题、背景、合同/关系/金钱/时间等现实变量"],
        "actionWindow": "具体行动窗口和观察期限",
        "summary": "一段大白话结论，直接回答这件事该进、该缓、还是先观察。",
    }
    system = (
        "你是 Ming Atelier 的梅花易数起卦复核与解释层。你不重新起卦，必须保留输入中的本卦、互卦、变卦、体用和动爻。"
        "你可以复核达成度、风险、置信度和吉凶是否贴合用户问题；若要修正，必须克制，通常达成度不超过上下12分，风险不超过上下2分。"
        "输出风格对标高端私人咨询：20% 技术依据，80% 针对用户问题的现实判断。"
        "必须把卦象和用户的具体问题连起来，不要写泛泛的吉凶话术。"
        "如果是合作/副业，重点写合同、分工、付款、交付、试运行和退出条件；"
        "如果是感情，重点写承诺、沟通、时机、互相投入和边界；"
        "如果是事业/财务，重点写权责、收益、成本、现金流、备选方案和风控。"
        "如果是健康、安全、法律、投资保证类问题，必须强调现实复核和专业意见，不能给确定性承诺。"
        "语言要直接、克制、有同理心，不恐吓，不许诺。输出必须是合法 JSON，不要 Markdown。"
    )
    user = (
        "请按以下 JSON schema 返回："
        f"{json.dumps(schema_note, ensure_ascii=False)}\n\n"
        "起卦结构化结果如下：\n"
        f"{json.dumps(result, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def percent_int(value: str | int | float | None) -> int | None:
    match = re.search(r"\d{1,3}", str(value or ""))
    if not match:
        return None
    return clamp_int(int(match.group(0)), 0, 100)


def enrich_divination_with_llm(result: dict) -> dict:
    result["llmStatus"] = "disabled"
    if not llm_report_enabled():
        return result
    llm = call_llm_json(llm_divination_prompt(result))
    if not isinstance(llm, dict):
        result["llmStatus"] = "fallback"
        return result
    changed = False
    original_success = percent_int(result.get("success"))
    original_risk = percent_int(result.get("risk"))
    verdict = str(llm.get("reviewedVerdict", "")).strip()
    if verdict in {"吉", "小吉", "平", "凶"}:
        result["verdict"] = verdict
        _, verdict_tone, verdict_text = verdict_from_score(percent_int(llm.get("reviewedSuccess")) or original_success or 50)
        result["verdictTone"] = verdict_tone
        result["verdictText"] = verdict_text
        changed = True
    reviewed_success = percent_int(llm.get("reviewedSuccess"))
    if reviewed_success is not None and original_success is not None:
        bounded = clamp_int(reviewed_success, original_success - 12, original_success + 12)
        result["success"] = f"{bounded}%"
        if not verdict:
            result["verdict"], result["verdictTone"], result["verdictText"] = verdict_from_score(bounded)
        changed = True
    reviewed_risk = percent_int(llm.get("reviewedRisk"))
    if reviewed_risk is not None and original_risk is not None:
        bounded = clamp_int(reviewed_risk, original_risk - 2, original_risk + 2)
        result["risk"] = f"{clamp_int(bounded, 1, 10)}/10"
        changed = True
    reviewed_confidence = percent_int(llm.get("reviewedConfidence"))
    if reviewed_confidence is not None:
        result["confidence"] = f"{clamp_int(reviewed_confidence, 45, 82)}%"
        changed = True
    for key, min_len in [("questionReading", 60), ("summary", 45), ("actionWindow", 12)]:
        value = llm.get(key)
        if isinstance(value, str) and len(value.strip()) >= min_len:
            result[key] = value.strip()
            changed = True
    for key in ["advice", "riskPoints"]:
        value = llm.get(key)
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if isinstance(item, str) and len(str(item).strip()) >= 10]
            if 3 <= len(cleaned) <= 6:
                result[key] = cleaned
                changed = True
    result["llmStatus"] = "applied" if changed else "fallback"
    return result


def divination_result_en(result: dict) -> dict:
    verdict_map = {"吉": "Favorable", "小吉": "Mildly favorable", "平": "Mixed / neutral", "凶": "Unfavorable"}
    tone_map = {
        "顺势可进": "favorable; move with timing",
        "可进，但要控风险": "can move forward with risk control",
        "先观察，再小步推进": "observe first, then move in small steps",
        "条件未稳，宜缓": "conditions are not stable; slow down",
        "不宜硬推": "do not force it now",
    }
    topic = result.get("topic", "")
    topic_en = {
        "合作/副业": "partnership / side project",
        "感情/关系": "relationship",
        "事业/工作": "career / work",
        "财务/投资": "finance / investment",
        "健康/安全": "health / safety",
    }.get(topic, "general decision")
    relation = result.get("relation", "")
    relation_en = {
        "用生体": "the external side supports you",
        "体生用": "you are investing more energy into the matter",
        "体克用": "you have room to take control",
        "用克体": "the external pressure is pressing back on you",
        "体用同气": "both sides are moving with similar energy",
    }.get(relation, relation)
    phase = result.get("phase", "")
    phase_en = {"初段": "early stage", "中段": "middle stage", "late stage": "late stage", "后段": "late stage"}.get(phase, phase)
    question = result.get("question", "")
    success = result.get("success", "")
    risk = result.get("risk", "")
    confidence = result.get("confidence", "")
    body_match = re.search(r"(.+?)卦（(.+?)）", str(result.get("body", "")))
    use_match = re.search(r"(.+?)卦（(.+?)）", str(result.get("use", "")))
    if body_match:
        trigram, element = body_match.groups()
        result["body"] = f"{TRIGRAM_EN.get(trigram, trigram)} trigram ({element_en(element)})"
    if use_match:
        trigram, element = use_match.groups()
        result["use"] = f"{TRIGRAM_EN.get(trigram, trigram)} trigram ({element_en(element)})"
    result["timeSource"] = TIME_SOURCE_EN.get(result.get("timeSource"), result.get("timeSource", "time source not identified"))
    if result.get("timezone") == "未识别":
        result["timezone"] = "not identified"
    if str(result.get("location", "")).startswith("未填"):
        result["location"] = "not provided; cast by current local time"
    if result.get("background") == "未填":
        result["background"] = "not provided"
    if result.get("omen") in {"无", "没有"}:
        result["omen"] = "none"
    result["lunarText"] = "Chinese lunar calendar and Four-Pillar time markers are used as the casting base."
    result["solarTerm"] = "solar-term signal used as supporting timing context"
    result["topic"] = topic_en
    result["verdict"] = verdict_map.get(result.get("verdict"), result.get("verdict"))
    result["verdictTone"] = tone_map.get(result.get("verdictTone"), result.get("verdictTone"))
    result["phase"] = phase_en
    result["relation"] = relation_en
    result["relationText"] = f"In this reading, {relation_en}. The moving line is in the {phase_en}, so the matter should be tested through concrete feedback rather than pushed by emotion."
    result["seasonText"] = "The chart was cast from the question time. Seasonal and day-branch energy are supporting signals, not a guarantee."
    result["energyText"] = "Body/use energy compares your own position with the outside condition. A gap means the matter needs verification before commitment."
    result["movementText"] = f"The moving line sits in the {phase_en}; read it as timing pressure, not a fixed fate."
    result["topicCalibration"] = f"The question is treated as {topic_en}. Background details adjust the reading only when they show concrete real-world risk."
    result["verdictText"] = f"This reads as {result['verdict']}: the answer depends on evidence, timing, boundaries, and whether the other side gives concrete action."
    result["questionReading"] = (
        f"For your question, “{question}”, the reading leans {result['verdict']} rather than a simple yes/no. "
        f"The success estimate is {success}, risk is {risk}, and confidence is {confidence}. "
        f"Because {relation_en} and the matter is in the {phase_en}, the practical move is to verify one clear condition first: "
        "who commits, by when, with what cost, and what happens if the answer changes."
    )
    if topic_en == "relationship":
        result["advice"] = [
            "Ask for one concrete next step instead of forcing an emotional conclusion.",
            "Keep money, living arrangements, and long-term promises separate until the relationship definition is clearer.",
            "If the other person only gives warmth but no action, lower your investment and observe.",
        ]
        result["riskPoints"] = [
            "The main risk is emotional ambiguity turning into self-consumption.",
            "Do not use pressure, testing, or silence as the main communication method.",
            "If there is control, safety risk, or harm, prioritize real-world support over divination.",
        ]
    elif topic_en == "partnership / side project":
        result["advice"] = [
            "Start with a written scope: responsibility, delivery, payment, ownership, and exit terms.",
            "Run a small trial before committing long-term resources.",
            "Delay any large financial or equity decision until the other party gives concrete obligations.",
        ]
        result["riskPoints"] = [
            "The main risk is vague resources turning into your extra work and cost.",
            "If payment, timeline, or ownership is unclear, the obstacle is already visible.",
            "For large money or legal exposure, use professional review.",
        ]
    else:
        result["advice"] = [
            "Turn the question into one verifiable action and one clear deadline.",
            "Test the response before increasing commitment.",
            "Keep an exit condition and do not put all options into one decision.",
        ]
        result["riskPoints"] = [
            "The more vague the question is, the lower the usable accuracy.",
            "If real-world evidence contradicts the reading, prioritize the evidence.",
            "Major legal, medical, or investment matters require professional review.",
        ]
    result["actionWindow"] = "Use the next 24-72 hours for the first signal; use the next 7-14 days to verify whether the condition can actually land."
    result["summary"] = f"Overall: {result['verdict']}. This is not a blank fortune label; for this specific question, the reading says to proceed only through verification, boundaries, and staged commitment."
    return result


def build_divination(data: dict) -> dict:
    question = data.get("question", "").strip()
    if not question:
        raise ValueError("请填写要问的具体事情")
    divination_time, timezone_name, time_source = divination_datetime(data)
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
    background = data.get("background", "").strip()
    omen = data.get("omen", "").strip() or "无"
    topic = divination_topic(question, background)
    topic_adjust, topic_risk, topic_confidence, topic_notes = topic_score_adjustment(topic, relation, phase, question, background, omen)
    success = clamp_int(58 + relation_score + body_score - max(0, use_score - body_score) // 2 + phase_score + topic_adjust, 24, 90)
    risk = 5 + (2 if success < 48 else 0) + (1 if moving_line in (3, 4) else 0) + (1 if relation == "用克体" else 0) - (1 if success >= 68 else 0)
    risk = clamp_int(risk + topic_risk, 1, 10)
    verdict, verdict_tone, verdict_text = verdict_from_score(success)
    confidence = 65
    confidence += 6 if time_source != "服务器当前时间" else -5
    confidence += 4 if timezone_name else -4
    confidence += 3 if data.get("location", "").strip() else -4
    confidence += 5 if background else -6
    confidence += 4 if omen not in {"无", "没有", "none", "None"} else -2
    confidence += topic_confidence
    if len(question) < 8:
        confidence -= 5
    confidence = clamp_int(confidence, 42, 82)
    action_window = {
        "初段": "先用 24-72 小时观察回应；若反馈顺，再推进下一步。",
        "中段": "未来 3-14 天是关键拉扯期，适合谈条件、补材料、看对方态度。",
        "后段": "未来 7-30 天看落地结果，重点放在确认、收尾和防反复。",
    }[phase]
    question_reading, advice, risk_points = divination_contextual_reading(topic, question, background, verdict, relation, phase)
    body_energy = clamp_int((0.55 + body_score / 30 + max(relation_score, -10) / 80) * 100, 20, 90)
    use_energy = clamp_int((0.55 + use_score / 30 - max(relation_score, -10) / 100) * 100, 20, 90)
    benefit_loss = "2:1" if success >= 70 and risk <= 5 else "1:1" if success >= 52 and risk <= 7 else "1:2" if risk <= 8 else "1:3"
    solar_term = ""
    try:
        solar_term = lunar.getJieQi() or f"{lunar.getPrevJieQi()}至{lunar.getNextJieQi()}之间"
    except Exception:
        solar_term = "节气未校准"
    result = {
        "question": question,
        "time": divination_time.strftime("%Y-%m-%d %H:%M"),
        "timeSource": time_source,
        "timezone": timezone_name or "未识别",
        "location": data.get("location", "").strip() or "未填，按当前本地时间起卦",
        "background": background or "未填",
        "topic": topic,
        "omen": omen,
        "lunarText": f"农历{lunar_month}月{lunar_day}日，{ec.getYear()}年 {ec.getMonth()}月 {ec.getDay()}日 {ec.getTime()}时",
        "solarTerm": solar_term,
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
        "energyText": f"体卦能量系数约 {body_energy / 100:.2f}，用卦/外部变量能量系数约 {use_energy / 100:.2f}。",
        "movementText": phase_text,
        "topicCalibration": "；".join(topic_notes) or "问题背景未出现强烈现实修正信号，主要按卦气与体用判断。",
        "verdict": verdict,
        "verdictTone": verdict_tone,
        "verdictText": verdict_text,
        "success": f"{success}%",
        "risk": f"{risk}/10",
        "confidence": f"{confidence}%",
        "actionWindow": action_window,
        "benefitLossRatio": benefit_loss,
        "questionReading": question_reading,
        "advice": advice,
        "riskPoints": risk_points,
        "summary": f"此卦判断为「{verdict}」，倾向是「{verdict_tone}」。对应你问的“{question}”，结论不是抽象吉凶，而是：{question_reading}",
    }
    result = enrich_divination_with_llm(result)
    if is_english(data):
        result = divination_result_en(result)
    return result


def relation_labels_between(a: str, b: str) -> list[str]:
    if not a or not b:
        return []
    labels = []
    if a == b:
        labels.append(f"{a}{b}伏吟")
        if a in SELF_XING:
            labels.append(SELF_XING[a])
    key = branch_pair_key(a, b)
    for mapping in (LIU_HE, LIU_CHONG, LIU_HAI, LIU_PO, PAIR_XING):
        if key in mapping:
            labels.append(mapping[key])
    return unique(labels)


def relation_weight(labels: list[str], pillar_weight: int = 1) -> int:
    score = 0
    for label in labels:
        if "六合" in label or "合" in label and "半合" not in label:
            score += 8
        if "半合" in label:
            score += 5
        if "三合" in label or "三会" in label:
            score += 9
        if "冲" in label:
            score -= 10
        if "刑" in label:
            score -= 9
        if "害" in label:
            score -= 7
        if "破" in label:
            score -= 6
        if "伏吟" in label:
            score -= 3
    return score * pillar_weight


def stem_relation_between(a: str, b: str) -> list[str]:
    if not a or not b:
        return []
    labels = []
    labels.append(GAN_HE.get(a + b) or GAN_HE.get(b + a) or "")
    labels.append(GAN_CHONG.get(a + b) or GAN_CHONG.get(b + a) or "")
    return unique([label for label in labels if label])


def compatibility_person(data: dict, computed: dict) -> dict:
    ec = computed["ec"]
    profile = computed["profile"]
    diag = day_master_diagnostics(ec, profile)
    useful = diag["useful"]
    context = analysis_context(data, computed, diag["strength"], useful)
    pillars = computed["chart"]["pillars"]
    hidden_stems = []
    for branch in [pillar["branch"] for pillar in pillars]:
        hidden_stems.extend([stem for stem, _ in HIDDEN_WEIGHT.get(branch, [])])
    return {
        "name": data.get("name") or "匿名",
        "gender": data.get("gender") or "",
        "ec": ec,
        "computed": computed,
        "profile": profile,
        "diagnostic": diag,
        "context": context,
        "useful": useful,
        "day_stem": ec.getDayGan(),
        "day_branch": ec.getDayZhi(),
        "day_element": STEM_ELEMENT.get(ec.getDayGan(), ""),
        "pillars": pillars,
        "stems": [pillar["stem"] for pillar in pillars],
        "branches": [pillar["branch"] for pillar in pillars],
        "hidden_stems": hidden_stems,
    }


def partner_star_hits(observer: dict, partner: dict) -> dict:
    spouse_stars = observer["context"]["spouse_stars"]
    partner_stems = partner["stems"] + partner["hidden_stems"]
    rows = []
    score = 0
    for stem in partner_stems:
        ten_god = ten_god_for(observer["day_stem"], stem)
        if ten_god in spouse_stars:
            score += 8 if stem in partner["stems"] else 4
            rows.append(f"{partner['name']}的{stem}对{observer['name']}是{ten_god}")
    day_ten_god = ten_god_for(observer["day_stem"], partner["day_stem"])
    if day_ten_god in spouse_stars:
        score += 12
        rows.insert(0, f"{partner['name']}日主{partner['day_stem']}直接触动{observer['name']}的{day_ten_god}")
    return {"score": min(score, 30), "rows": unique(rows[:5]), "dayTenGod": day_ten_god}


def useful_complement(observer: dict, partner: dict) -> dict:
    useful = observer["useful"]
    hits = sum(partner["profile"].get(element, 0) for element in useful)
    if hits >= 46:
        score = 18
        text = f"{partner['name']}五行里能给到{observer['name']}需要的{ '、'.join(useful) }，互补感明显。"
    elif hits >= 28:
        score = 11
        text = f"{partner['name']}对{observer['name']}的{ '、'.join(useful) }有一定补益，但还要看关系节奏和现实承接。"
    else:
        score = 4
        text = f"{partner['name']}对{observer['name']}的喜用补益不算强，更多要靠相处规则而不是自然互补。"
    return {"score": score, "text": text, "hitPercent": hits}


def cross_branch_matrix(a: dict, b: dict) -> list[dict]:
    labels = ["年柱", "月柱", "日柱", "时柱"]
    rows = []
    for i, a_branch in enumerate(a["branches"]):
        for j, b_branch in enumerate(b["branches"]):
            rels = relation_labels_between(a_branch, b_branch)
            if not rels:
                continue
            pillar_weight = 3 if i == 2 and j == 2 else 2 if i in {1, 2} or j in {1, 2} else 1
            weight = relation_weight(rels, pillar_weight)
            if weight > 0:
                meaning = "带来靠近、互相借力或关系黏合。"
            elif any("冲" in rel or "刑" in rel for rel in rels):
                meaning = "容易带来强触发、节奏拉扯、争执或现实压力。"
            else:
                meaning = "容易在细节、安全感、时间安排或边界上出现别扭。"
            rows.append({
                "aPillar": labels[i],
                "bPillar": labels[j],
                "aBranch": a_branch,
                "bBranch": b_branch,
                "relations": rels,
                "weight": weight,
                "meaning": meaning,
            })
    return sorted(rows, key=lambda item: abs(item["weight"]), reverse=True)


def combined_branch_sets(a: dict, b: dict) -> list[str]:
    branches = set(a["branches"] + b["branches"])
    labels = []
    for combo, label in SAN_HE.items():
        if combo.issubset(branches):
            labels.append(label)
    for combo, label in SAN_HUI.items():
        if combo.issubset(branches):
            labels.append(label)
    for raw, label in SAN_HE_HALVES.items():
        if raw[0] in branches and raw[1] in branches:
            labels.append(label)
    return unique(labels)


def cross_stem_matrix(a: dict, b: dict) -> list[dict]:
    labels = ["年干", "月干", "日干", "时干"]
    rows = []
    for i, a_stem in enumerate(a["stems"]):
        for j, b_stem in enumerate(b["stems"]):
            rels = stem_relation_between(a_stem, b_stem)
            if not rels:
                continue
            rows.append({
                "aPillar": labels[i],
                "bPillar": labels[j],
                "aStem": a_stem,
                "bStem": b_stem,
                "relations": rels,
                "meaning": "天干合冲更像表层态度、沟通方式、吸引点和合作方式的触发。",
            })
    return rows


PILLAR_SHORT_EN = {"年柱": "Year Pillar", "月柱": "Month Pillar", "日柱": "Day Pillar", "时柱": "Hour Pillar", "年干": "Year Stem", "月干": "Month Stem", "日干": "Day Stem", "时干": "Hour Stem"}


def compatibility_judgment_en(value: str) -> str:
    return {
        "适合推进": "Good window to move forward",
        "有吸引但波动大": "Attraction is strong, but volatility is high",
        "谨慎，不宜重绑定": "Be cautious; avoid heavy binding",
        "观察磨合": "Observe and test the rhythm",
    }.get(value, value)


def compatibility_branch_meaning_en(row: dict) -> str:
    weight = row.get("weight", 0)
    if weight > 0:
        return "This signal creates closeness, support, or a sense of being pulled together. It is useful, but still needs clear rhythm and boundaries."
    if weight < -7:
        return "This is a strong trigger point. It can show pace conflict, emotional friction, pressure around safety, or practical disagreement."
    if weight < 0:
        return "This can create small but repeated discomfort around details, security, timing, or boundaries."
    return "This relation is a secondary signal; read it together with attraction, useful-element complement, and real communication."


def localize_compatibility_model_en(model: dict) -> None:
    converted_windows = []
    for year, pillar, judgment, _note in model.get("windows", []):
        converted_windows.append([
            year,
            pillar,
            compatibility_judgment_en(judgment),
            (
                f"In {year} ({pillar}), read both charts together. This year is better used for pacing, boundary-setting, and checking whether attraction can become stable behavior. "
                "If attraction and stress both rise, avoid making emotional promises before money, time, and future plans are clear."
            ),
        ])
    model["windows"] = converted_windows
    for row in model.get("branchMatrix", []):
        row["aPillar"] = PILLAR_SHORT_EN.get(row.get("aPillar"), row.get("aPillar"))
        row["bPillar"] = PILLAR_SHORT_EN.get(row.get("bPillar"), row.get("bPillar"))
        row["meaning"] = compatibility_branch_meaning_en(row)
    for row in model.get("stemMatrix", []):
        row["aPillar"] = PILLAR_SHORT_EN.get(row.get("aPillar"), row.get("aPillar"))
        row["bPillar"] = PILLAR_SHORT_EN.get(row.get("bPillar"), row.get("bPillar"))
        row["meaning"] = "Heavenly-stem combinations and clashes describe visible attitude, communication style, attraction points, and cooperation style."


def compatibility_windows(a: dict, b: dict) -> list[list[str]]:
    rows = []
    reset_luck_phrase_counts(a["context"], "compat_a")
    reset_luck_phrase_counts(b["context"], "compat_b")
    for offset, ganzhi in enumerate(GANZHI_2026_2036):
        year = str(2026 + offset)
        a_read = analyze_luck_pillar(a["context"], ganzhi, "year")
        b_read = analyze_luck_pillar(b["context"], ganzhi, "year")
        branch = split_ganzhi(ganzhi)[1]
        a_rels = relation_labels_with(a["branches"], branch)
        b_rels = relation_labels_with(b["branches"], branch)
        heat = (a_read["relationship"] + b_read["relationship"]) / 2
        risk = max(a_read["stress"], b_read["stress"], a_read["loss"], b_read["loss"])
        if heat >= 7 and risk <= 6:
            judgment = "适合推进"
        elif heat >= 6 and risk >= 7:
            judgment = "有吸引但波动大"
        elif risk >= 8:
            judgment = "谨慎，不宜重绑定"
        else:
            judgment = "观察磨合"
        note = (
            f"{ganzhi}年，{a['name']}关系分{a_read['relationship']}/9、压力{a_read['stress']}/9；"
            f"{b['name']}关系分{b_read['relationship']}/9、压力{b_read['stress']}/9。"
            f"{'、'.join(unique(a_rels + b_rels)[:4]) or '未见强触发'}。"
        )
        rows.append([year, ganzhi, judgment, note])
    return rows


def deterministic_compatibility_text(model: dict) -> dict:
    a = model["a"]
    b = model["b"]
    a_to_b = model["attraction"]["aToB"]
    b_to_a = model["attraction"]["bToA"]
    complement = model["complement"]
    def relation_summary(rows: list[dict], limit: int) -> str:
        items = []
        seen = set()
        for row in rows:
            label = f"{row['aBranch']}{row['bBranch']}：{'、'.join(row['relations'])}"
            if label in seen:
                continue
            items.append(label)
            seen.add(label)
            if len(items) >= limit:
                break
        return "；".join(items)

    conflicts = [row for row in model["branchMatrix"] if row["weight"] < 0]
    bonds = [row for row in model["branchMatrix"] if row["weight"] > 0]
    conflict_text = relation_summary(conflicts, 4) or "强冲突不算多，主要看现实节奏。"
    bond_text = relation_summary(bonds, 3) or "显性合局不算强，吸引更多来自十神互相触动。"
    summary = (
        f"{a['name']}和{b['name']}这组合不是单纯好或坏，而是要看吸引、互补和触发能不能被现实规则接住。"
        f"{a['name']}日主{a['day_stem']}{a['day_element']}，喜用偏{'、'.join(a['useful']) or '未明'}；"
        f"{b['name']}日主{b['day_stem']}{b['day_element']}，喜用偏{'、'.join(b['useful']) or '未明'}。"
        f"{complement['aFromB']['text']}{complement['bFromA']['text']}"
        f"吸引力上，{';'.join(a_to_b['rows'][:2]) or '一方伴侣星触发不强'}；"
        f"{';'.join(b_to_a['rows'][:2]) or '另一方伴侣星触发不强'}。"
        f"稳定点在：{bond_text}。问题点在：{conflict_text}。"
        "所以这段关系适合先把关系定义、钱、时间安排和现实规划讲清楚，再看能否长期推进。"
    )
    return {
        "overall": summary,
        "attraction": "双方是否有感觉，主要看彼此是否触动对方的伴侣星、日主和夫妻宫。这个组合的吸引不是只靠生肖，而是命盘里确实有互相看见对方的信号。",
        "complement": "互补的重点是五行和行为系统：谁让谁冷静，谁给谁方向，谁提供规则，谁提供行动力。互补强时是彼此扶住，互补失衡时就会变成一方拉着另一方走。",
        "friction": f"主要摩擦来自：{conflict_text}。这些不是一定分开，而是说明关系里容易在安全感、节奏、钱、承诺或现实计划上有反复。",
        "timing": "年份窗口要同时看两个人的流年。关系分高但风险也高的年份，适合观察和谈规则；关系分高且风险较低的年份，更适合推进承诺。",
        "advice": [
            "先定义关系，不要长期暧昧或只靠感觉推进。",
            "钱、项目、资源和亲密关系分开处理，至少前期不要混在一起。",
            "遇到冲刑害破被触发的年份，先谈边界、节奏和现实安排，再谈情绪。",
            "如果要长期发展，双方都需要能把话说清楚，而不是用冷战或试探消耗对方。",
        ],
    }


def deterministic_compatibility_text_en(model: dict) -> dict:
    a = model["a"]
    b = model["b"]
    conflicts = [row for row in model["branchMatrix"] if row["weight"] < 0]
    bonds = [row for row in model["branchMatrix"] if row["weight"] > 0]

    def relation_summary(rows: list[dict], limit: int) -> str:
        items = []
        seen = set()
        for row in rows:
            label = f"{row['aBranch']} with {row['bBranch']}: {', '.join(row['relations'])}"
            if label in seen:
                continue
            items.append(label)
            seen.add(label)
            if len(items) >= limit:
                break
        return "; ".join(items)

    conflict_text = relation_summary(conflicts, 4) or "there are no dominant hard clashes; the relationship depends more on pace and real-life boundaries."
    bond_text = relation_summary(bonds, 3) or "the visible combination structure is not especially strong; attraction comes more from partner-star and Ten-God activation."
    a_useful = ", ".join(element_en(x) for x in a["useful"]) or "not clearly defined"
    b_useful = ", ".join(element_en(x) for x in b["useful"]) or "not clearly defined"
    summary = (
        f"{a['name']} and {b['name']} are not a simple good-or-bad match. The chart needs to be read through attraction, complement, friction, and whether the relationship can be held by real rules. "
        f"{a['name']}'s Day Master is {a['day_stem']} ({element_en(a['day_element'])}), with useful elements leaning toward {a_useful}. "
        f"{b['name']}'s Day Master is {b['day_stem']} ({element_en(b['day_element'])}), with useful elements leaning toward {b_useful}. "
        f"The stabilizing signals are: {bond_text}. The pressure points are: {conflict_text}. "
        "This means the relationship can have attraction and learning value, but it should not be left vague. Define the relationship, money boundaries, time rhythm, and future expectations before making heavy commitments."
    )
    return {
        "overall": summary,
        "attraction": "Attraction is read through whether each person activates the other's partner star, Day Master, and spouse palace. This is more precise than a zodiac-style match; it asks whether the other person actually appears inside your relationship symbols.",
        "complement": "Complement is not one person fixing the other. It shows whose elements and behavior system bring calm, direction, structure, initiative, or emotional steadiness to the other person.",
        "friction": f"The main friction signals are: {conflict_text}. These do not force separation, but they describe where safety, pace, money, commitment, and future planning may repeatedly trigger each other.",
        "timing": "Timing should be read by comparing both people's annual luck. Years with high attraction and high risk are better for observation and boundary-setting; years with high relationship score and lower risk are better for commitment.",
        "advice": [
            "Define the relationship early; do not stay in a long ambiguous state.",
            "Keep money, projects, resources, and intimacy separate in the early stage.",
            "When clash or punishment years are activated, discuss boundaries and practical plans before emotional conclusions.",
            "Long-term development requires direct communication rather than silence, testing, or assumption.",
        ],
        "shortVerdict": "Strong attraction; define boundaries before commitment.",
    }


def llm_compatibility_prompt(packet: dict, lang: str = "zh") -> list[dict[str, str]]:
    schema_note = {
        "overall": "整体合盘结论，300-600字，像私人咨询，不要模板。",
        "attraction": "互相吸引为什么成立或不成立，必须引用双方日主、伴侣星、夫妻宫或十神触发。",
        "complement": "互补关系，说明谁补谁什么、会带来什么现实效果。",
        "friction": "主要拉扯，不恐吓，解释情绪、安全感、钱、节奏、现实规划里的具体问题。",
        "timing": "2026-2036 的关系窗口总结，说明哪些年适合推进，哪些年不宜重绑定。",
        "advice": ["4-6条相处建议，必须具体"],
        "shortVerdict": "一句话结论，30字以内",
    }
    if lang == "en":
        system = (
            "You are Ming Atelier's BaZi compatibility interpretation layer. The deterministic chart facts are already locked. "
            "Do not change the Four Pillars, Day Masters, Five Elements, Ten Gods, branch relations, scores, or years. "
            "Your task is to write a premium client-facing relationship reading in English. "
            "Analysis weighting: 20% technical BaZi anchors, 80% practical relationship interpretation. "
            "Cover overall fit, mutual attraction, Five-Element complement, clashes/punishments/harms in real relationship behavior, 2026-2036 timing, and concrete advice. "
            "Do not promise marriage, do not frighten the client, and do not give legal/financial certainty. Return valid JSON only."
        )
        user = (
            "Write the customer-facing compatibility interpretation in English. Keep Chinese stems/branches/star names as technical symbols when needed, but explain them in plain English. "
            f"schema: {json.dumps(schema_note, ensure_ascii=False)}\n\n"
            f"Compatibility facts: {json.dumps(packet, ensure_ascii=False)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
    system = (
        "你是 Ming Atelier 的八字合盘解读层。确定性事实已经由程序排好，你不能改四柱、日主、五行、十神、冲合刑害、年份。"
        "你的任务是把合盘结果写成客户能读懂、愿意付费的关系报告。"
        "分析权重：20% 技术依据，80% 贴合双方关系的解释。"
        "必须覆盖：整体适配、互相吸引、五行互补、冲合刑害带来的相处问题、2026-2036窗口、相处建议。"
        "不要只说“适合/不适合”，要讲为什么、怎么相处、哪几年慢一点、哪些边界要先定。"
        "语言可参考：直接、细腻、有同理心、东方命理感，但不要恐吓，不保证结婚，不给法律/投资确定性建议。"
        "输出必须是合法 JSON，不要 Markdown，不要 JSON 之外的解释。"
    )
    user = (
        "请根据以下合盘事实输出客户可见文本。不要复用输入里的句子，组织成自然语言：\n"
        f"schema: {json.dumps(schema_note, ensure_ascii=False)}\n\n"
        f"合盘事实：{json.dumps(packet, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def apply_compatibility_llm(model: dict) -> None:
    model["llmStatus"] = "disabled"
    lang = model.get("lang", "zh")
    text = deterministic_compatibility_text_en(model) if lang == "en" else deterministic_compatibility_text(model)
    model["text"] = text
    if not llm_report_enabled():
        return
    packet = {
        "personA": {
            "name": model["a"]["name"],
            "gender": model["a"]["gender"],
            "pillars": {
                "year": model["a"]["ec"].getYear(),
                "month": model["a"]["ec"].getMonth(),
                "day": model["a"]["ec"].getDay(),
                "hour": model["a"]["ec"].getTime(),
            },
            "dayMaster": f"{model['a']['day_stem']}{model['a']['day_element']}",
            "strength": f"{model['a']['diagnostic']['label']} {model['a']['diagnostic']['strength']}%",
            "useful": model["a"]["useful"],
            "profile": model["a"]["profile"],
            "spouseStars": model["a"]["context"]["spouse_stars"],
            "riskFlags": model["a"]["context"]["risk_flags"],
        },
        "personB": {
            "name": model["b"]["name"],
            "gender": model["b"]["gender"],
            "pillars": {
                "year": model["b"]["ec"].getYear(),
                "month": model["b"]["ec"].getMonth(),
                "day": model["b"]["ec"].getDay(),
                "hour": model["b"]["ec"].getTime(),
            },
            "dayMaster": f"{model['b']['day_stem']}{model['b']['day_element']}",
            "strength": f"{model['b']['diagnostic']['label']} {model['b']['diagnostic']['strength']}%",
            "useful": model["b"]["useful"],
            "profile": model["b"]["profile"],
            "spouseStars": model["b"]["context"]["spouse_stars"],
            "riskFlags": model["b"]["context"]["risk_flags"],
        },
        "scores": model["scores"],
        "attraction": model["attraction"],
        "complement": model["complement"],
        "branchMatrix": model["branchMatrix"][:12],
        "stemMatrix": model["stemMatrix"][:10],
        "combinedSets": model["combinedSets"],
        "windows": model["windows"],
        "relationshipQuestion": model["question"],
        "currentStatus": model["status"],
    }
    llm = call_llm_json(llm_compatibility_prompt(packet, lang))
    if not isinstance(llm, dict):
        model["llmStatus"] = "fallback"
        return
    changed = False
    for key, min_len in [("overall", 120), ("attraction", 60), ("complement", 60), ("friction", 60), ("timing", 60), ("shortVerdict", 8)]:
        value = llm.get(key)
        if isinstance(value, str) and len(value.strip()) >= min_len:
            model["text"][key] = value.strip()
            changed = True
    advice = llm.get("advice")
    if isinstance(advice, list):
        cleaned = [str(item).strip() for item in advice if isinstance(item, str) and len(str(item).strip()) >= 10]
        if 3 <= len(cleaned) <= 7:
            model["text"]["advice"] = cleaned
            changed = True
    model["llmStatus"] = "applied" if changed else "fallback"


def build_compatibility(data: dict) -> tuple[dict, Path]:
    def person(prefix: str, fallback_name: str) -> dict:
        result = {
            "name": data.get(f"{prefix}Name") or fallback_name,
            "gender": data.get(f"{prefix}Gender") or "",
            "birthDate": data.get(f"{prefix}BirthDate") or "",
            "birthTime": data.get(f"{prefix}BirthTime") or "",
            "birthPlace": data.get(f"{prefix}BirthPlace") or "",
            "calendar": "阳历",
        }
        missing = [key for key in ("gender", "birthDate", "birthTime", "birthPlace") if not result.get(key)]
        if missing:
            raise ValueError(f"{fallback_name}缺少字段：{', '.join(missing)}")
        return result

    a_data = person("a", "你")
    b_data = person("b", "对方")
    run_id = f"compatibility-{safe_name(a_data['name'])}-{safe_name(b_data['name'])}-{uuid.uuid4().hex[:6]}"
    a_computed, _ = build_chart(a_data, run_id + "-a")
    b_computed, _ = build_chart(b_data, run_id + "-b")
    a = compatibility_person(a_data, a_computed)
    b = compatibility_person(b_data, b_computed)
    a_to_b = partner_star_hits(a, b)
    b_to_a = partner_star_hits(b, a)
    a_from_b = useful_complement(a, b)
    b_from_a = useful_complement(b, a)
    branch_matrix = cross_branch_matrix(a, b)
    stem_matrix = cross_stem_matrix(a, b)
    combined_sets = combined_branch_sets(a, b)
    aggregate_weights: dict[str, int] = {}
    for row in branch_matrix:
        for label in row["relations"]:
            current = aggregate_weights.get(label)
            if current is None or abs(row["weight"]) > abs(current):
                aggregate_weights[label] = row["weight"]
    branch_score = sum(weight for weight in aggregate_weights.values() if weight > 0)
    attraction = clamp_int(48 + a_to_b["score"] + b_to_a["score"] + min(18, max(0, branch_score // 2)), 20, 95)
    complement_score = clamp_int(42 + a_from_b["score"] + b_from_a["score"], 20, 95)
    friction_raw = abs(sum(weight for weight in aggregate_weights.values() if weight < 0))
    friction = clamp_int(32 + friction_raw, 10, 92)
    stability = clamp_int((attraction + complement_score + 100 - friction) / 3, 15, 92)
    overall = clamp_int(attraction * 0.34 + complement_score * 0.28 + stability * 0.25 + (100 - friction) * 0.13, 18, 94)
    model = {
        "a": a,
        "b": b,
        "lang": "en" if is_english(data) else "zh",
        "question": data.get("question") or "",
        "status": data.get("status") or "",
        "scores": {
            "overall": f"{overall}%",
            "attraction": f"{attraction}%",
            "complement": f"{complement_score}%",
            "friction": f"{friction}%",
            "stability": f"{stability}%",
        },
        "attraction": {"aToB": a_to_b, "bToA": b_to_a},
        "complement": {"aFromB": a_from_b, "bFromA": b_from_a},
        "branchMatrix": branch_matrix,
        "stemMatrix": stem_matrix,
        "combinedSets": combined_sets,
        "windows": compatibility_windows(a, b),
    }
    if model["lang"] == "en":
        localize_compatibility_model_en(model)
    apply_compatibility_llm(model)
    output = GENERATED / f"{run_id}.html"
    compatibility_report_html(model, output)
    return model, output


def compatibility_report_html(model: dict, output: Path) -> None:
    def e(value) -> str:
        return html.escape(str(value or ""))

    def score_card(label: str, value: str, text: str) -> str:
        pct = percent_int(value) or 0
        return f'<article class="kpi"><span>{e(label)}</span><b>{e(value)}</b><i><em style="width:{pct}%"></em></i><p>{e(text)}</p></article>'

    lang_en = model.get("lang") == "en"
    branch_rows = "".join(
        f"<tr><td>{e(row['aPillar'])} {e(row['aBranch'])}</td><td>{e(row['bPillar'])} {e(row['bBranch'])}</td><td>{e((', ' if lang_en else '、').join(row['relations']))}</td><td>{e(row['meaning'])}</td></tr>"
        for row in model["branchMatrix"][:16]
    ) or (('<tr><td colspan="4">No dominant hard clash or combination detected; focus on Ten-God activation and real-life rhythm.</td></tr>' if lang_en else '<tr><td colspan="4">未见强冲合刑害破，重点看十神与现实节奏。</td></tr>'))
    stem_rows = "".join(
        f"<tr><td>{e(row['aPillar'])} {e(row['aStem'])}</td><td>{e(row['bPillar'])} {e(row['bStem'])}</td><td>{e((', ' if lang_en else '、').join(row['relations']))}</td><td>{e(row['meaning'])}</td></tr>"
        for row in model["stemMatrix"][:12]
    ) or (('<tr><td colspan="4">No strong visible heavenly-stem combination or clash.</td></tr>' if lang_en else '<tr><td colspan="4">天干显性合冲不强。</td></tr>'))
    window_rows = "".join(f"<tr><td>{e(row[0])}</td><td>{e(row[1])}</td><td>{e(row[2])}</td><td>{e(row[3])}</td></tr>" for row in model["windows"])
    advice = "".join(f"<li>{e(item)}</li>" for item in model["text"]["advice"])
    a = model["a"]
    b = model["b"]
    page_lang = "en" if lang_en else "zh-CN"
    report_title = "Compatibility Report" if lang_en else "合盘报告"
    back_home = "Back Home" if lang_en else "回到主页"
    redo = "New Compatibility Reading" if lang_en else "重新合盘"
    overall_label = "Overall Reading" if lang_en else "整体判断"
    score_labels = (
        [("Overall Fit", "A blended score of attraction, complement, stability, and friction."),
         ("Attraction", "Whether both charts activate partner-star and spouse-palace signals."),
         ("Complement", "Whether each person supports the other's useful elements and behavior system."),
         ("Friction", "The intensity of clashes, punishments, harms, breaks, and real-life tension."),
         ("Stability", "Long-term landing capacity and relationship containment.")]
        if lang_en
        else [("整体适配", "综合吸引、互补、稳定与摩擦。"), ("吸引力", "彼此是否触动伴侣星和夫妻宫。"), ("互补度", "对方是否补到自己的喜用和行为系统。"), ("摩擦度", "冲刑害破和现实拉扯强度。"), ("稳定度", "长期承接和关系落地能力。")]
    )
    section_attraction = "Attraction & Complement" if lang_en else "吸引与互补"
    section_friction = "Main Friction" if lang_en else "主要拉扯"
    section_timing = "Timing Windows" if lang_en else "年份窗口"
    section_branch = "Branch Relationship Matrix" if lang_en else "地支关系矩阵"
    section_stem = "Heavenly Stem Relations" if lang_en else "天干合冲"
    footer_text = "Ming Atelier | Compatibility readings are cultural relationship analysis and do not replace real communication, legal, financial, or psychological advice." if lang_en else "Ming Atelier｜合盘属于传统文化关系阅读，不替代现实沟通、法律、财务或心理专业建议。"
    html_text = f"""<!doctype html>
<html lang="{page_lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(a['name'])} × {e(b['name'])} {report_title}｜Ming Atelier</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap');
*{{box-sizing:border-box}}body{{margin:0;background:#050302;color:#f6e8c8;font-family:"Songti SC","STSong","Noto Serif SC","Kaiti SC",serif;line-height:1.72}}a{{color:inherit}}.shell{{width:min(1180px,calc(100% - 36px));margin:0 auto}}.hero{{min-height:76vh;display:grid;align-items:center;position:relative;overflow:hidden;background:radial-gradient(circle at 72% 38%,rgba(216,173,85,.24),transparent 28%),linear-gradient(120deg,#070402,#130d05 52%,#050302)}}.hero:before{{content:"合";position:absolute;right:8vw;top:4vh;font-size:34vw;color:rgba(216,173,85,.06);line-height:1}}.hero:after{{content:"";position:absolute;inset:0;background:radial-gradient(circle at 24% 30%,rgba(247,217,142,.08),transparent 24%),linear-gradient(180deg,transparent,rgba(0,0,0,.5))}}.hero .shell{{position:relative;z-index:2}}.eyebrow{{color:#d8ad55;font-family:Optima,Arial,sans-serif;letter-spacing:.28em;font-size:12px;text-transform:uppercase}}h1{{font-family:"Instrument Serif",serif;font-size:clamp(54px,8vw,112px);line-height:.95;margin:10px 0;color:#ffe0a0;font-weight:400}}.lead{{max-width:860px;font-size:20px;color:#ead9b8}}.actions{{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}}.btn{{border:1px solid rgba(216,173,85,.62);padding:12px 18px;text-decoration:none;background:rgba(12,8,4,.7)}}section{{padding:58px 0;border-top:1px solid rgba(216,173,85,.18)}}h2{{font-size:34px;color:#f4c979;margin:0 0 18px}}.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}}.kpi,.card{{border:1px solid rgba(216,173,85,.34);background:rgba(18,13,7,.78);padding:18px;box-shadow:0 18px 42px rgba(0,0,0,.26)}}.kpi b{{display:block;color:#ffe0a0;font-size:30px;margin:8px 0}}.kpi i{{display:block;height:8px;background:rgba(216,173,85,.16);overflow:hidden}}.kpi em{{display:block;height:100%;background:linear-gradient(90deg,#d8ad55,#ffe0a0)}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}p{{color:#e2cfaa}}ul{{padding-left:20px}}li{{margin:8px 0;color:#ead9b8}}table{{width:100%;border-collapse:collapse;min-width:780px}}th,td{{border-bottom:1px solid rgba(216,173,85,.2);padding:11px;text-align:left;vertical-align:top}}th{{color:#f4c979;background:rgba(216,173,85,.08)}}.table{{overflow:auto;border:1px solid rgba(216,173,85,.25)}}.fade{{opacity:0;transform:translateY(16px);transition:.7s ease}}.fade.show{{opacity:1;transform:none}}@media(max-width:820px){{.grid,.two{{grid-template-columns:1fr}}h1{{font-size:52px}}}}
</style></head><body>
<main>
<section class="hero"><div class="shell"><p class="eyebrow">Ming Atelier · Compatibility Reading</p><h1>{e(a['name'])}<br>× {e(b['name'])}</h1><p class="lead">{e(model['text'].get('shortVerdict') or ('Strong attraction; define boundaries before commitment.' if lang_en else '强吸引、看边界、慢推进。'))}</p><div class="actions"><a class="btn" href="/{'?lang=en' if lang_en else ''}">{back_home}</a><a class="btn" href="/compatibility.html{'?lang=en' if lang_en else ''}">{redo}</a></div></div></section>
<section class="fade"><div class="shell"><h2>{overall_label}</h2><div class="grid">{score_card(score_labels[0][0],model['scores']['overall'],score_labels[0][1])}{score_card(score_labels[1][0],model['scores']['attraction'],score_labels[1][1])}{score_card(score_labels[2][0],model['scores']['complement'],score_labels[2][1])}{score_card(score_labels[3][0],model['scores']['friction'],score_labels[3][1])}{score_card(score_labels[4][0],model['scores']['stability'],score_labels[4][1])}</div><div class="card" style="margin-top:16px"><p>{e(model['text']['overall'])}</p></div></div></section>
<section class="fade"><div class="shell two"><article class="card"><h2>{section_attraction}</h2><p>{e(model['text']['attraction'])}</p><p>{e(model['text']['complement'])}</p></article><article class="card"><h2>{section_friction}</h2><p>{e(model['text']['friction'])}</p><ul>{advice}</ul></article></div></section>
<section class="fade"><div class="shell"><h2>{section_timing}</h2><p>{e(model['text']['timing'])}</p><div class="table"><table><thead><tr><th>{'Year' if lang_en else '年份'}</th><th>{'Annual Pillar' if lang_en else '流年'}</th><th>{'Judgment' if lang_en else '判断'}</th><th>{'Notes' if lang_en else '说明'}</th></tr></thead><tbody>{window_rows}</tbody></table></div></div></section>
<section class="fade"><div class="shell"><h2>{section_branch}</h2><div class="table"><table><thead><tr><th>{e(a['name'])}</th><th>{e(b['name'])}</th><th>{'Relation' if lang_en else '关系'}</th><th>{'Reading' if lang_en else '解读'}</th></tr></thead><tbody>{branch_rows}</tbody></table></div></div></section>
<section class="fade"><div class="shell"><h2>{section_stem}</h2><div class="table"><table><thead><tr><th>{e(a['name'])}</th><th>{e(b['name'])}</th><th>{'Relation' if lang_en else '关系'}</th><th>{'Reading' if lang_en else '解读'}</th></tr></thead><tbody>{stem_rows}</tbody></table></div></div></section>
</main><footer class="shell" style="padding:32px 0;color:#9f8a62">{footer_text}</footer>
<script>const io=new IntersectionObserver(es=>es.forEach(e=>{{if(e.isIntersecting)e.target.classList.add('show')}}),{{threshold:.12}});document.querySelectorAll('.fade').forEach(el=>io.observe(el));</script>
</body></html>"""
    output.write_text(html_text, encoding="utf-8")


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
    lang_en = is_english(data)
    summary = free_report_summary_en(data, computed) if lang_en else free_report_summary(data, computed)
    title_text = f"{data.get('name') or 'Anonymous'} Free BaZi Reading" if lang_en else f"{data.get('name') or '匿名'} 免费排盘报告"
    sub_text = (
        f"{data.get('calendar', 'Solar')} {data.get('birthDate')} {data.get('birthTime')} | {data.get('birthPlace', '')} | {GENDER_EN.get(data.get('gender', ''), data.get('gender', ''))}"
        if lang_en
        else f"{data.get('calendar', '阳历')} {data.get('birthDate')} {data.get('birthTime')}｜{data.get('birthPlace', '')}｜{data.get('gender', '')}｜金额单位：人民币 RMB"
    )
    note_text = (
        "Free version note: this report includes the birth chart and a first-layer plain-language reading. It does not expand major luck cycles, annual timing, soulmate windows, or deep risk analysis."
        if lang_en
        else "免费版说明：本报告只做排盘和一段基础大白话总结。命盘图保留神煞与地支关系，正文不展开深度格局、大运、流年和风险细断。"
    )
    raw_title = "1. Original Chart Information" if lang_en else "一、原始盘信息"
    summary_title = "2. Plain-Language Summary" if lang_en else "二、大白话总结"
    raw_rows = (
        [["Item", "Content"], ["Four Pillars", pillars], ["Day Master", ec.getDayGan()], ["Current / 2026 Luck Pillar", selected.getGanZhi() if selected else "Not identified"], ["Five Element Estimate", ", ".join(f"{element_en(k)} {v}%" for k, v in profile.items())]]
        if lang_en
        else [["项目", "内容"], ["四柱", pillars], ["日主", ec.getDayGan()], ["当前/2026大运", selected.getGanZhi() if selected else "未识别"], ["五行估计", "，".join(f"{k}{v}%" for k, v in profile.items())]]
    )
    story = [
        paragraph(title_text, styles["title"]),
        paragraph(sub_text, styles["sub"]),
        Spacer(1, 8),
        paragraph(note_text, styles["note"]),
        Spacer(1, 8),
        Image(str(chart_png), width=135 * mm, height=205 * mm),
        PageBreak(),
        paragraph(raw_title, styles["h1"]),
        table(raw_rows, [44 * mm, 126 * mm], font),
        paragraph(summary_title, styles["h1"]),
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
    "红鸾": "关系启动、喜庆、人际靠近和情感机会。",
    "天喜": "喜事、关系推进、合作愉悦感和情绪回暖。",
    "十灵日": "敏感、直觉、快速感知、表达或创造性灵气。",
    "羊刃": "竞争、锋芒、执行、冲突和伤损倾向，需要规则约束。",
    "禄神": "稳定收入、岗位资源、技能底盘和可持续供养。",
    "驿马": "迁移、出行、跨境、物流、市场流动和业务扩展。",
    "华盖": "研究、艺术、玄学、审美、独处和专业深度。",
    "金舆": "车辆、舒适、资源支持、体面感和生活质量。",
    "天医": "修复、照顾、健康意识、疗愈资源和问题补救。",
    "孤辰": "独立、疏离、自我消化压力和关系节奏偏慢。",
    "寡宿": "情感保留、独处感、慢热和亲密关系里的距离感。",
    "劫煞": "突发竞争、资源被截、临时变数和外部冲击。",
    "亡神": "暗线压力、隐藏消耗、判断偏差和不易明说的牵制。",
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
        gan_shen = pillar["gan_shen"] or "日主"
        rows.append([
            gan_shen,
            f"{label}天干 {pillar['stem']}",
            TEN_GOD_TEXT.get(gan_shen, "日主自身、行动中枢和判断核心。"),
            f"{gan_shen}落在{label}，会直接影响你的{meaning}。它不是孤立性格标签，而是你在这个人生场景里最容易使用的反应模式：遇到机会时怎么判断，遇到压力时怎么处理，遇到人和钱时怎么设边界。",
        ])
        for hidden, shen in zip(pillar.get("hidden", []), pillar.get("zhi_shen", [])):
            rows.append([
                shen,
                f"{label}地支 {pillar['branch']}藏{hidden.split('·')[0]}",
                TEN_GOD_TEXT.get(shen, "藏干提供支撑、潜在动机和暗线资源。"),
                f"{shen}藏在{pillar['branch']}里，说明这股力量不一定每天外显，但会在{meaning}相关的事情上被触发。它更像你的暗线动机：平时不一定说出口，关键时刻会影响选择、合作方式和风险承受度。",
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
                f"在{label}主要落到{meaning}。对客户来说，它更像一种具体体验：哪些场景容易遇到助力，哪些场景容易被情绪、关系、合同或资源牵动，需要和十神、大运一起看。",
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


def annual_rows(selected_ganzhi: str, useful: list[str], context: dict | None = None, dayun_rows: list[list[str]] | None = None) -> list[list[str]]:
    if context:
        reset_luck_phrase_counts(context, "year")
        rows = []
        for offset, ganzhi in enumerate(GANZHI_2026_2036):
            year = str(2026 + offset)
            read = analyze_luck_pillar(context, ganzhi, "year")
            rows.append([
                year,
                ganzhi,
                dayun_for_year(dayun_rows or [], year, selected_ganzhi or "未识别"),
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
    return [[year, pillar, dayun_for_year(dayun_rows or [], year, selected_ganzhi or "未识别"), str(career), str(wealth), str(relation), str(stress), str(loss), str(family), str(compliance), trigger] for year, pillar, career, wealth, relation, stress, loss, family, compliance, trigger in years]


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
        note += "，关系、合作绑定和贴身利益会更容易被推到台前。"
    elif month_hit:
        note += "，事业环境、客户要求和执行节奏会更明显。"
    else:
        note += "，作为这一阶段的背景压力或机会。"
    return note, day_hit, month_hit


def pick_variant(seed: str, options: list[str]) -> str:
    if not options:
        return ""
    return options[sum(ord(ch) for ch in seed) % len(options)]


def reset_luck_phrase_counts(context: dict | None, scope: str) -> None:
    if context is not None:
        context["_luck_phrase_scope"] = scope
        context["_luck_phrase_counts"] = {}


def scoped_luck_phrase(context: dict, scope: str, key: str, seed: str, first: list[str], later: list[str]) -> str:
    counts = context.setdefault("_luck_phrase_counts", {})
    count_key = f"{scope}:{key}"
    counts[count_key] = counts.get(count_key, 0) + 1
    if counts[count_key] == 1:
        options = first
        start = sum(ord(ch) for ch in f"{seed}{key}{scope}") % len(options) if options else 0
    else:
        options = later
        start = (counts[count_key] - 2) % len(options) if options else 0
    if not options:
        return ""
    used = context.setdefault("_used_luck_phrases", set())
    for offset in range(len(options)):
        phrase = options[(start + offset) % len(options)]
        if phrase not in used:
            used.add(phrase)
            return phrase
    return ""


def pick_unused_luck_phrase(context: dict, seed: str, options: list[str]) -> str:
    if not options:
        return ""
    used = context.setdefault("_used_luck_phrases", set())
    start = sum(ord(ch) for ch in seed) % len(options)
    for offset in range(len(options)):
        phrase = options[(start + offset) % len(options)]
        if phrase not in used:
            used.add(phrase)
            return phrase
    return ""


def group_luck_phrase(group: str, context: dict, scope: str, seed: str) -> str:
    useful_text = "、".join(context["useful"]) or "节奏"
    monthly = scope == "month"
    bank = {
        "output": [
            f"食伤露头，适合把想法做成内容、产品、报价页或交付样板；{'这个月' if monthly else '这一年'}先看作品能不能换来真实询盘。",
            f"食伤动起来时，优势在表达、销售、技术输出和方法论包装；别只追曝光，要把流量接到合同与收款节点。",
            f"输出星被引动，利发布、讲清价值、做产品化试验；成败关键在交付边界，而不是一时热度。",
        ],
        "wealth": [
            f"财星到场，客户、定价、账期和现金流会变成主线；{useful_text}要落到收款规则和客户筛选上。",
            f"财星被带动，不是单纯“有钱来”，而是交易条件变多；报价、回款、分成和税务要同步算清。",
            f"财气被激活，适合谈客户、提价或收账；若账期过长或合作条款模糊，机会会变成压力。",
        ],
        "officer": [
            "官杀被引动，外部规则、平台标准、上级/客户要求会变强；适合拿资质、定流程，也要防被责任压住。",
            "官杀到位时，事业会更像考试和验收：名分、合同、交付标准、合规口径都要摆到台面上。",
            "规则星上来，利职位、责任、专业背书和正式合作；不利模糊承诺和先做后补合同。",
        ],
        "resource": [
            "印星被引动，适合补方法论、证据链、资质和后台系统；先补底层能力，再承接更大的单。",
            "印星到位像给系统加缓冲，利学习、复盘、贵人/机构支持；这类机会慢一点反而更稳。",
            "资源星上来，重点不是猛冲，而是把知识、流程、文档、合同模板和复盘机制建起来。",
        ],
        "peer": [
            "比劫被引动，朋友、同业、合伙和竞争会变热；能带资源，也会带分利和权限问题。",
            "同类力量上来，适合组队、社群和资源互换，但客户、账户、股权和退出要有明确规则。",
            "比劫动时，人脉会更活跃；适合借势，不适合把核心资源交给临时关系托管。",
        ],
    }
    return pick_unused_luck_phrase(context, seed + group + scope, bank.get(group, []))


def special_luck_phrase(key: str, context: dict, scope: str, seed: str) -> str:
    scoped_bank = {
        "weak_finance": (
            [
                "身弱遇财官，表面是机会，背后是成本、责任和合规压力一起上升。",
                "财官压身时，不宜硬接大单或大责任；先看资源、团队、合同能不能托住。",
            ],
            [
                "先核交付能力和回款节点，再决定是否接下更大的责任。",
                "把责任上限、交付范围和付款节奏确认完，再谈扩张。",
                "大单可以看，但不能让账期、库存或人力先替客户垫底。",
                "先做资源清单：人手、时间、现金流不够时，宁可缩小承诺。",
                "客户条件越诱人，越要先拆成本结构和最坏回款周期。",
                "不要用未来收入覆盖当下成本，先让项目自己跑通闭环。",
                "适合谈条件，不适合先替别人垫资源、垫时间、垫信用。",
                "把付款节点和验收节点配对，避免只交付、不回款。",
            ],
        ),
        "weak_officer": (
            [
                "日主承压而规则星走强，合同、平台规则、交付责任和法律口径要先审。",
                "官杀压力重时，别用情绪硬扛规则；先补资质、证据链和专业支持。",
            ],
            [
                "平台规则、宣传口径和验收标准先过一遍，避免后补漏洞。",
                "遇到强势客户或机构要求，先确认责任边界和证据链。",
                "适合请专业支持把关，不适合凭经验硬扛。",
                "合同、税务、平台条款有疑点时，先停半步再推进。",
                "权责越正式，越要保留过程记录和验收证据。",
                "先把谁拍板、谁验收、谁承担延期责任讲清楚。",
                "对外承诺要降温，内部审核和交付清单要升温。",
                "规则压力上来时，专业背书比临场解释更有用。",
            ],
        ),
        "strong_peer": (
            [
                "身强再逢比劫，行动力很足，但要防冲动扩张和人情账。",
                "比劫过旺时，不缺胆子，缺的是边界；钱、账户和客户规则要冷处理。",
            ],
            [
                "新增伙伴只给阶段权限，不要一开始开放核心账户。",
                "可以组队试单，但先做短周期验收，不直接绑定长期分成。",
                "社群、人脉和资源互换可用，核心资产不要外放。",
            ],
        ),
        "peer_wealth": (
            [
                "财与比劫同场，钱能来，人也会来分；股权、税务、IP/数据归属要先定。",
                "比劫与财星一起动，合作价值会放大，也会考验收款账户、客户归属和退出条款。",
            ],
            [
                "本期合作先做小额试单，客户归属写进项目单。",
                "报价和回款节点先定，再谈资源互换或长期分成。",
                "新增渠道只给阶段权限，核心账户和数据不要混用。",
                "分成口径按项目结算，不把人情关系带进总账。",
            ],
        ),
        "wealth_peer": (
            [
                "客户与现金流被点亮时，同业/朋友也容易同场，不能让资源边界变糊。",
                "这不是单纯财运好坏，而是钱一动，人际和权责也会跟着动。",
            ],
            [
                "先收款、再交付，别让账期吞掉表面利润。",
                "客户来源、介绍费和续费归属要在报价前讲清。",
                "临时资源可以用，但核心客户池要单独管理。",
            ],
        ),
        "collision": (
            [
                "合冲刑害走到台前，节奏会变快也更容易出摩擦；重大决定要留书面确认。",
                "盘面互动变强，适合做调整，不适合把所有筹码压在一次承诺上。",
            ],
            [
                "把变更写进补充协议，别让新条件停在聊天记录里。",
                "缩短账期和交付周期，先用小闭环验证对方稳定性。",
                "当天情绪很满时，不做不可逆的付款、签约或分手决定。",
                "保留付款、验收和变更记录，给后续复盘留证据。",
                "计划变动时先重排优先级，不要同时追加预算和范围。",
                "冲刑被点动时，最适合拆小步骤，不适合一次定终局。",
                "遇到临时条件，先确认影响到的钱、时间和责任。",
                "有摩擦时先暂停扩大投入，把已发生的事实对齐。",
            ],
        ),
    }
    if key in scoped_bank:
        first, later = scoped_bank[key]
        return scoped_luck_phrase(context, scope, key, seed, first, later)
    bank = {
        "useful": [
            "流年/月带到可用之气，机会更容易落到可执行的规则、产品或现金流里。",
            "这一步有喜用配合，适合把优势做实，不要停在感觉好或机会多。",
            "可用元素被引动，推进可以更主动，但仍要用预算、合同和复盘接住。",
        ],
        "output_officer": [
            "食伤可制杀，利线上表达和产品破局，但发布、营销和承诺不能越过规则。",
            "输出能打开局面，也会碰到规则审查；越高调，越要留合同和证据。",
            "可以靠内容/产品冲开压力，但交付范围、宣传话术和合规底线要收紧。",
        ],
        "resource_buffer": [
            "印比到位，能补根、补专业和缓冲官杀压力。",
            "资源与同类力量能托住压力，适合补方法、补文档、补支持系统。",
            "这一步的关键不是硬冲，而是用学习、流程和可信伙伴把底盘垫厚。",
            "有支撑信号出现，适合把专业证据、复盘资料和协作机制补齐。",
        ],
        "day_hit": [
            "日支有动，关系、合作绑定、居住安排或贴身利益会被推到台前。",
            "触到关系宫时，很多事不只是业务问题，也会变成信任、承诺和边界问题。",
            "日支有动，适合把亲密关系与合作关系里的现实条件讲清楚。",
        ],
        "month_hit": [
            "月令主题走强，事业环境、客户要求、上级规则和执行节奏会更显眼。",
            "触到事业宫时，工作方法要升级；旧流程容易不够用。",
            "月柱主题被带动，适合整理业务结构，也要防项目节奏被外部牵着走。",
        ],
    }
    return pick_unused_luck_phrase(context, seed + key + scope, bank.get(key, []))


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
    career = 5.0
    wealth = 5.0
    relationship = 5.0
    stress = 5.0
    loss = 4.0
    family = 4.0
    compliance = 5.0
    reasons = []
    priority_reasons = []
    triggered_groups = unique([group for group in [stem_group, branch_group] + hidden_groups[:2] if group in GROUP_LABEL])

    for group in triggered_groups:
        if group == "output":
            career += 0.9
            wealth += 1.0
            reasons.append(group_luck_phrase(group, context, scope, ganzhi))
        elif group == "wealth":
            wealth += 1.6
            career += 0.4
            relationship += 0.7 if context["spouse_group"] == "wealth" else 0
            reasons.append(group_luck_phrase(group, context, scope, ganzhi))
        elif group == "officer":
            career += 0.5
            stress += 1.1
            compliance += 1.0
            relationship += 0.7 if context["spouse_group"] == "officer" else 0
            reasons.append(group_luck_phrase(group, context, scope, ganzhi))
        elif group == "resource":
            career += 0.4
            stress -= 0.6
            reasons.append(group_luck_phrase(group, context, scope, ganzhi))
        elif group == "peer":
            career -= 0.2 if context["strength"] >= 62 else 0
            loss += 1.1
            reasons.append(group_luck_phrase(group, context, scope, ganzhi))

    if useful_hit:
        career += 0.5
        wealth += 0.6
        stress -= 0.4
        reasons.append(special_luck_phrase("useful", context, scope, ganzhi))
    else:
        stress += 0.6
    if context["strength"] < 46 and (stem_group in {"wealth", "officer"} or branch_group in {"wealth", "officer"}):
        stress += 1.6
        loss += 0.9
        wealth -= 0.8
        priority_reasons.append(special_luck_phrase("weak_finance", context, scope, ganzhi))
    if weak_officer_alert and (stem_group in {"resource", "peer"} or branch_group in {"resource", "peer"}):
        career += 0.6
        stress -= 0.8
        reasons.append(special_luck_phrase("resource_buffer", context, scope, ganzhi))
    if weak_officer_alert and (stem_group in {"wealth", "officer"} or branch_group in {"wealth", "officer"}):
        compliance += 1.5
        loss += 0.8
        priority_reasons.append(special_luck_phrase("weak_officer", context, scope, ganzhi))
    if weak_officer_alert and (stem_group == "output" or branch_group == "output") and output_officer_alert:
        career += 1.1
        wealth += 0.8
        stress += 0.7
        compliance += 0.8
        priority_reasons.append(special_luck_phrase("output_officer", context, scope, ganzhi))
    if context["strength"] > 68 and stem_group == "peer":
        loss += 1.7
        career -= 0.4
        reasons.append(special_luck_phrase("strong_peer", context, scope, ganzhi))
    if day_hit:
        relationship += 1.2 if any("合" in label for label in labels) else -0.8
        stress += 0.8
        family += 1.3
        reasons.append(special_luck_phrase("day_hit", context, scope, ganzhi))
    if month_hit:
        career += 0.6
        compliance += 0.6
        reasons.append(special_luck_phrase("month_hit", context, scope, ganzhi))
    if any("冲" in label or "刑" in label or "害" in label or "破" in label for label in labels):
        stress += 1.4
        loss += 0.8
        compliance += 0.7
        priority_reasons.append(special_luck_phrase("collision", context, scope, ganzhi))
    if stem_tg == "伤官" and context["group_scores"].get("officer", 0) >= 1.0:
        compliance += 1.4
        stress += 0.8
        reasons.append("伤官碰到原局官杀，公开表达、规则冲突和合规风险要控")
    if stem_tg in context["spouse_stars"] or branch_main in context["spouse_stars"] or day_hit:
        relationship += 0.7
    if stem_tg in {"正财", "偏财"} and context["group_scores"].get("peer", 0) > 1.5:
        loss += 0.9
        priority_reasons.append(special_luck_phrase("wealth_peer", context, scope, ganzhi))
    if peer_wealth_alert and (stem_group in {"peer", "wealth"} or branch_group in {"peer", "wealth"}):
        loss += 1.5
        compliance += 0.8
        priority_reasons.append(special_luck_phrase("peer_wealth", context, scope, ganzhi))

    if stress >= 8 or loss >= 8 or compliance >= 8:
        career -= 0.7
    if wealth >= 8 and loss >= 8:
        wealth -= 0.5
    note_parts = [part.rstrip("。") for part in unique(priority_reasons + reasons) if part.strip()][:3]
    if not note_parts:
        note_parts = [f"{stem_tg}/{branch_main}被引动，先看其与月令、日支和大运是否形成承接"]
    note = f"{ganzhi}：{relation_note}{'；'.join(note_parts)}。"
    if scope == "month":
        note = f"{ganzhi}月：{relation_note}{'；'.join(note_parts)}。"
    return {
        "stem_tg": stem_tg,
        "branch_tg": branch_main,
        "relations": labels,
        "career": max(2, min(9, round(career))),
        "wealth": max(2, min(9, round(wealth))),
        "relationship": max(2, min(9, round(relationship))),
        "stress": max(2, min(9, round(stress))),
        "loss": max(2, min(9, round(loss))),
        "family": max(2, min(9, round(family))),
        "compliance": max(2, min(9, round(compliance))),
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
        "shen_sha": calculate_shensha(day_stem, day_branch, stem, branch, xunkong, "", "", "", label) if branch else [],
    }


def compact_flow_note(note: str) -> str:
    if not note:
        return ""
    if "。" not in note and "." in note:
        first = note.split(".", 1)[0].strip()
        return f"{first}." if first else note
    first = note.split("。", 1)[0].strip()
    return f"{first}。" if first else note


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
    for row in annual_rows(selected.getGanZhi() if selected else "", useful, context, dayun_rows):
        annual_strip.append([row[0], row[1], row[3], row[4], row[5], row[6], compact_flow_note(row[10])])
    month_strip = [[row[0], row[1], row[2], row[3], row[4], row[6], compact_flow_note(row[7])] for row in monthly_rows(context)]
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
        year_tag = f"{risky[0]}{risky[1]}"
        high_risk_lines = {
            "2026-2027": f"{label}里最需要慢下来的节点是{year_tag}。先确认收款、责任、交付顺序和退出条件，再决定要不要放大。",
            "2028-2029": f"{label}的钱和人都会更活，{year_tag}尤其要防合作边界变糊；报价、客户归属和分账口径要提前写清。",
            "2030-2033": f"{label}容易进入系统化考验，{year_tag}不适合靠临场反应解决问题；流程、合同、税务和团队责任要先定版。",
            "2034-2036": f"{label}像一次方向再筛选，{year_tag}要避免为了新机会提前透支；先看资源能不能长期承接。",
        }
        medium_risk_lines = {
            "2026-2027": f"{label}整体可推进，但{year_tag}容易让节奏变快。适合先做小范围验证，再扩预算或承诺。",
            "2028-2029": f"{label}有客户和现金流机会，{year_tag}适合谈条件，但不宜把账期、库存和交付压力全压到自己身上。",
            "2030-2033": f"{label}更适合把能力变成系统，{year_tag}要重视验收、回款和岗位责任，而不是只看表面规模。",
            "2034-2036": f"{label}可以观察新方向，{year_tag}先用低成本试错，别一开始就投入过重。",
        }
        low_risk_lines = {
            "2026-2027": f"{label}风险相对可控，但{year_tag}仍要保留预算、账期、合同和退出条件。",
            "2028-2029": f"{label}可用来扩大客户面，但{year_tag}要把复购、介绍费和客户池归属讲清。",
            "2030-2033": f"{label}适合沉淀制度和产品，{year_tag}重点是把账、货、人和流程收拢。",
            "2034-2036": f"{label}更适合复盘和调整，{year_tag}先稳住旧盘，再看新盘。",
        }
        if avg_risk >= 18:
            risk = high_risk_lines.get(label, f"{label}要在{year_tag}放慢确认。")
        elif avg_risk >= 14:
            risk = medium_risk_lines.get(label, f"{label}可推进，但{year_tag}要先验证。")
        else:
            risk = low_risk_lines.get(label, f"{label}风险可控，但{year_tag}要留复盘。")
        if strength < 48:
            risk += " 这类盘先补资源与支持系统，不宜靠硬扛换增长。"
        elif strength > 68:
            suffix = {
                "2026-2027": " 初期最忌一兴奋就把周期拉长。",
                "2028-2029": " 钱越容易动，越要守住账户和客户主权。",
                "2030-2033": " 规模越大，越要让制度先替你承压。",
                "2034-2036": " 新方向可以看，但先让旧系统稳住。",
            }.get(label, " 越顺的时候越要克制动作幅度。")
            risk += suffix
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
        elif flag["key"] == "peer_wealth":
            rows.append([flag["title"], flag["text"], "从第一天写清股权、收款账户、客户归属、IP/代码/数据所有权、退出条款和违约责任。"])
        elif flag["key"] == "peer_wealth_combo":
            rows.append([flag["title"], flag["text"], "项目做大前先定所有权、分账口径、客户池归属和退出估值方式。"])
        elif flag["key"] == "output_officer":
            rows.append([flag["title"], flag["text"], "可做线上表达和产品化破局，但发布、营销、合同承诺、交付边界要先过复核。"])
        elif flag["key"] == "legal_collision":
            rows.append([flag["title"], flag["text"], "所有合作先走书面流程，避免模糊分成、代持和没有退出条款的项目。"])
    if scores.get("peer", 0) >= 2.0 and scores.get("wealth", 0) >= 1.0:
        rows.append(["分利与现金流危机", "比劫与财星同时有力，机会容易和合伙、分账、客户归属绑在一起。", "报价、客户归属、账期、股权/分成、退出条件必须先写清。"])
    if scores.get("officer", 0) >= 2.0 and context["strength"] < 55:
        rows.append(["压力与权责危机", "官杀较重而日主承压，容易遇到规则、上级、平台、合规或强势客户压力。", "先确认责任边界、交付标准和法务财务口径，避免承诺先行、文件后补。"])
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
        return f"{label}神煞制衡关系：{ '、'.join(support) }偏向支持学习、资质、制度和专业表达；适合把贵人、文书、规则和专业能力变成现实支点。"
    if risk:
        return f"{label}神煞制衡关系：{ '、'.join(risk) }提示该柱主题容易有延迟、冲突或不稳定；需要提前用合同、节奏、复盘和现实边界承接。"
    return f"{label}神煞制衡关系：该柱神煞力量较轻，重点看月令、十神、大运流年如何把事情推到现实层面。"


def cross_shensha_balance(rows_by_group: dict[str, list[list[str]]]) -> str:
    all_stars = [row[1] for rows in rows_by_group.values() for row in rows]
    helpers = [s for s in all_stars if s in {"天乙贵人", "文昌贵人", "学堂", "国印", "福星贵人", "太极贵人"}]
    risks = [s for s in all_stars if s in {"羊刃", "空亡", "灾煞", "童子"}]
    if helpers and risks:
        return f"跨柱神煞制衡关系：{ '、'.join(unique(helpers)) }可以缓冲{ '、'.join(unique(risks)) }，但前提是走制度、专业、合同、长辈/机构支持，而不是靠情绪硬扛。"
    if helpers:
        return f"跨柱神煞制衡关系：{ '、'.join(unique(helpers)) }重复出现时，说明学习、文书、制度和贵人资源可作为长期支点。"
    if risks:
        return f"跨柱神煞制衡关系：{ '、'.join(unique(risks)) }偏风险提示，适合用地支关系、大运流年和现实风险控制一起复核。"
    return "跨柱神煞制衡关系：无明显强制衡关系，重点回到月令、十神、地支关系和现实选择。"


def june_2026_detail(context: dict | None = None) -> str:
    if not context:
        return "2026 年 6 月甲午是全年高风险月：午火叠加全年丙午，容易把表达、投资、情绪承诺、业务扩张和现金流压力同时点燃。"
    reset_luck_phrase_counts(context, "month_detail")
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
    reset_luck_phrase_counts(context, "month")
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
            "金": "外在更容易给人清爽、克制、有边界和专业感，不一定热络，但做事讲规则。",
            "水": "气质偏灵活、会沟通、信息感强，可能带一点跨城、跨文化或流动性的感觉。",
            "木": "气质偏成长型，重学习、审美、长期发展和精神连接，不太适合粗糙强压的相处。",
            "火": "气质更明亮、表达欲强、反应快，容易带来热度，也需要成熟的情绪节奏。",
            "土": "气质偏稳定务实，重生活秩序、责任感和现实承接，给人的安全感比较强。",
        }.get(spouse_element, "偏稳定和专业感")
        role_trait = {
            "金": "更可能出现在金融、数据、法务、技术、管理、审计、医疗器械或强规则行业。",
            "水": "更可能接触内容信息、咨询、贸易、跨境、互联网、传媒、流动型业务或沟通型岗位。",
            "木": "更可能与教育、内容、设计、咨询、产品、文化审美、成长型组织或长期项目相关。",
            "火": "更可能与品牌、传播、销售、市场、娱乐、培训、表达型岗位或曝光型业务有关。",
            "土": "更可能在运营、项目管理、供应链、地产、行政、人资、财务基础岗或稳定型组织里。",
        }.get(spouse_element, "更偏专业型、稳定型或需要长期积累的角色")
        relation_level = "中等偏高" if good_years else "需谨慎观察"
        risk_note = "；".join(f"{row[0]}{row[1]}压力高" for row in risk_years[:2]) or "主要风险来自现实责任没有谈清"
        return [
            ["未来关系波动", relation_level, f"伴侣星线索：{star_text}；夫妻宫为{context['day_branch']}，流年若合冲日支会明显触发关系。"],
            ["适合恋爱窗口", window, "按流年与日支、伴侣星、压力分数综合筛选，不是固定年份。"],
            ["最可能遇到时间", meet, "这是自动模型窗口；若客户提供恋爱/分手/结婚节点，可进一步校准。"],
            ["外貌气质", trait, f"由日支五行、伴侣星和喜用{''.join(useful)}综合取象，置信度中低。"],
            ["从事行业/角色", role_trait, "这是象意推断，不是硬性条件。"],
            ["不适配对象", "承诺模糊、财务边界混乱、强情绪控制或长期不给行动的人", risk_note],
            ["结婚成熟窗口", window if meet != "无法提供判断" else "无法提供判断", "重点不是单一年份，而是对象、城市、钱、家庭责任是否同步成熟。"],
        ]
    return [
        ["未来关系波动", "中等偏高", "事业节奏、现金流和现实承诺会直接影响关系稳定，置信度约62%。"],
        ["适合恋爱窗口", "2026-12 至 2027-01、2028-2029、2031-2033", "优先选金水较足、规则感更强的月份/年份。"],
        ["最可能遇到时间", "需结合大运流年细推；当前模型以 2028-2033 为较优窗口", "若问卷事件不足，年份细节置信度降低。"],
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


def llm_provider() -> str:
    provider = os.environ.get("MING_ATELIER_LLM_PROVIDER", "").strip().lower()
    if provider:
        return provider
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return "openai"


def llm_report_enabled() -> bool:
    if os.environ.get("MING_ATELIER_LLM", "1").lower() in {"0", "false", "off"}:
        return False
    provider = llm_provider()
    if provider in {"gemini", "google"}:
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return bool(os.environ.get("OPENAI_API_KEY"))


def compact_rows(rows: list[list[str]], limit: int | None = None) -> list[list[str]]:
    return rows[:limit] if limit else rows


def llm_fact_packet(data: dict, computed: dict, model: dict) -> dict:
    ec = model["ec"]
    context = model["analysis_context"]
    return {
        "client": {
            "name": data.get("name") or "匿名",
            "gender": data.get("gender") or "",
            "birth": f"{data.get('calendar', '阳历')} {data.get('birthDate', '')} {data.get('birthTime', '')}",
            "birthPlace": data.get("birthPlace") or "",
            "currentCity": data.get("currentCity") or "",
            "industry": data.get("industry") or "",
            "role": data.get("role") or "",
            "status": data.get("status") or "",
            "question": data.get("question") or "",
        },
        "chart": {
            "pillars": {
                "year": ec.getYear(),
                "month": ec.getMonth(),
                "day": ec.getDay(),
                "hour": ec.getTime(),
            },
            "dayMaster": f"{context['day_stem']}{context['day_element']}",
            "monthCommand": f"{context['month_branch']} / {context['month_structure']}",
            "strength": f"{model['day_strength_label']} {model['day_strength']}%",
            "engineUsefulElements": model["useful_elements"],
            "engineUsefulReason": model["useful_text"],
            "fiveElements": model["profile"],
            "relations": computed["chart"].get("relations") or [],
            "currentDayun": model["selected_dayun"],
            "dayunRows": compact_rows(model["dayun_rows"], 12),
        },
        "tenGods": {
            "rows": model["ten_god_rows"],
            "groupScores": context["group_scores"],
            "counts": context["ten_god_counts"],
            "spouseStars": context["spouse_stars"],
            "spouseVisible": context["spouse_visible"],
            "spouseHidden": context["spouse_hidden"],
        },
        "shensha": model["shensha_rows"],
        "riskFlags": context.get("risk_flags", []),
        "computedSections": {
            "careerRows": model.get("career_rows", []),
            "wealthIntro": model.get("wealth_tone", {}).get("base", ""),
            "incomeRows": model.get("income_rows", []),
            "incomeStageRows": model.get("income_stage_rows", []),
            "annualRows": [row[:10] for row in model.get("annual_rows", [])],
            "relationshipRows": [row for row in model.get("relationship_rows", []) if row[0] != "身高/体型"],
            "monthlyRows": [row[:7] for row in model.get("monthly_rows", [])],
            "crisisRows": model.get("crisis_rows", []),
            "summaryParagraphs": plain_summary_paragraphs(data, model),
        },
    }


def llm_report_prompt(packet: dict, lang: str = "zh") -> list[dict[str, str]]:
    if lang == "en":
        schema_note = {
            "useful_elements": ["金", "水"],
            "useful_text": "Optional. If the engine's useful-element reading is inaccurate, return 1-3 Chinese element symbols and one explanation. Must be based on season, Day Master strength, Ten-God pressure, hidden stems, branch relations, and luck cycles. Do not use missing-element logic.",
            "career_rows": [["Theme", "Reading", "Reasoning"]],
            "wealth_intro": "One plain-English opening paragraph for ten-year wealth rhythm.",
            "income_notes": {"Million-level": "replacement text", "Five-million level": "replacement text", "Ten-million level": "replacement text"},
            "income_stage_rows": [["Stage", "Income Reading", "Key Condition", "Risk"]],
            "annual_notes": [{"year": "2026", "note": "plain-English annual analysis"}],
            "monthly_notes": [{"month": "2026-02", "note": "monthly action note"}],
            "june_2026_detail": "Focused note for June 2026.",
            "crisis_rows": [["Theme", "Chart Basis", "Real-World Action"]],
            "summary_paragraphs": ["5 plain-English summary paragraphs"],
        }
        system = (
            "You are the interpretation layer for Ming Atelier BaZi reports. You write only the client-facing interpretation; do not recalculate the chart. "
            "For Career Development, Ten-Year Wealth, 2026 Monthly Timing, Core Crisis, and Plain-Language Summary, your independent judgment and language should drive 90% of the visible result; the local BaZi engine and tables are factual anchors and validation only. "
            "Keep Four Pillars, Ten Gods, ShenSha, branch relations, luck cycles, annual pillars, scores, and chart facts exactly as provided. Do not invent chart facts. "
            "Write in polished English for paying clients interested in BaZi. You may keep GanZhi, Ten-God Chinese names, and ShenSha names as technical symbols only when useful, but all explanatory prose must be English. "
            "Do not use generic template language, do not use missing-element logic, and do not promise wealth, marriage, disaster, or certainty. "
            "Return valid JSON only."
        )
        user = (
            "Generate personalized English text for the client-visible sections: Career Development, Ten-Year Wealth, 2026 Monthly Timing, Core Crisis, and Plain-Language Summary. "
            "Also review useful elements and return useful_elements/useful_text. The useful_elements value must still use Chinese element symbols from this set only: 金, 木, 水, 火, 土. "
            "Annual notes must cover 2026 through 2036, each with a distinct reading grounded in that year's GanZhi, major luck, scores, and triggers. Do not reuse the same sentence structure year after year. "
            "Use direct, restrained, empathetic, high-end English. Keep 20% technical anchoring and 80% practical interpretation.\n\n"
            f"Schema: {json.dumps(schema_note, ensure_ascii=False)}\n\n"
            f"Structured chart packet:\n{json.dumps(packet, ensure_ascii=False)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
    schema_note = {
        "useful_elements": ["金", "水"],
        "useful_text": "可选。若你认为引擎喜用神不准确，可返回 1-3 个五行和一句说明；必须基于月令、日主强弱、十神压力、合冲刑害，不得缺啥补啥。",
        "career_rows": [["主题", "判断", "依据"]],
        "wealth_intro": "未来十年财运开头说明，一段即可。",
        "income_notes": {"百万级": "替换收入卡条件文案", "500万级": "替换收入卡条件文案", "千万级": "替换收入卡条件文案"},
        "income_stage_rows": [["阶段", "收入判断", "关键条件", "风险"]],
        "annual_notes": [{"year": "2026", "note": "覆盖该年的年度大白话分析，不改分数"}],
        "monthly_notes": [{"month": "2026-02", "note": "覆盖该月提示，不改分数"}],
        "june_2026_detail": "2026年6月甲午重点提示。",
        "crisis_rows": [["主题", "盘面依据", "现实动作"]],
        "summary_paragraphs": ["5段大白话总结"],
    }
    system = (
        "你是 Ming Atelier 的八字命理解读层。你只写解释，不重新排盘。"
        "对事业发展、未来十年财运、2026流月、核心危机、大白话总结这些私人订制板块，"
        "你的独立判断与语言结论占 90%；输入中的本地命理 skill、书籍规则和表格只占 10%，用于事实锚点、术语依据和校验。"
        "不要被 computedSections 的旧文案牵着走；可以重写旧结论，但不能改动命盘事实和分数。"
        "必须遵守：四柱、十神、神煞、地支关系、大运、流年和分数以输入 JSON 为准；"
        "不得引用输入里不存在的十神、神煞或年份；不得恐吓、不得保证发财/结婚/灾祸；"
        "你必须完整覆盖事业发展、未来十年财运、2026流月、核心危机、大白话总结；"
        "未来十年财运必须为 2026-2036 每一年返回 annual_notes，字段 note 必须是一段大白话分析，按照现有报告 2026 年那种语言和逻辑讲清这一年的机会、风险、钱、人、合同、现金流和行动边界；2027 以后不能套用 2026 的句式，必须逐年引用该年的流年、大运和触发差异；"
        "喜用神体系也必须由你复核，返回 useful_elements 与 useful_text；可以和引擎一致，也可以修正，但必须说明月令、强弱、十神压力、地支关系和大运依据；"
        "不得用固定话术，不得只按五行百分比或缺啥补啥判断喜用。"
        "语言风格：东方命理、克制、直接、有同理心，像高端私人报告，不像模板。"
        "输出必须是合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"
    )
    user = (
        "请基于以下结构化命盘，为客户可见板块生成个性化文本：事业发展、未来十年财运、2026流月、核心危机、大白话总结。"
        "注意：原始盘信息、格局与用神、十神分析、神煞体系、喜用神、适配水晶由本地引擎负责；你只负责上述私人订制板块。"
        "但喜用神体系请由你复核后返回 useful_elements/useful_text，本地引擎会按你的复核结果更新喜用神和水晶。"
        "这些板块请以你的 Gemini Pro 结论为主，避免沿用 computedSections 里的模板话术。"
        "annual_notes 必须覆盖 2026、2027、2028、2029、2030、2031、2032、2033、2034、2035、2036 共 11 年。"
        "保留页面现有架构和表格维度，返回字段按这个样例："
        f"{json.dumps(schema_note, ensure_ascii=False)}\n\n"
        "结构化命盘如下：\n"
        f"{json.dumps(packet, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def llm_detail_prompt(packet: dict, lang: str = "zh") -> list[dict[str, str]]:
    if lang == "en":
        schema_note = {
            "ten_god_judgments": [{"index": 1, "judgment": "Plain-English interpretation of how this Ten-God signal affects personality, career, money, relationships, or long-term choice."}],
            "shensha_notes": [{"pillar": "Year Pillar", "star": "天乙贵人", "note": "Plain-English explanation of this ShenSha in this pillar."}],
        }
        system = (
            "You are the English explanation layer for Ming Atelier. Rewrite only the Ten-God judgment and the ShenSha pillar meaning. "
            "Do not add Ten Gods or ShenSha that are not in the input. Keep the technical names as supplied, but make the client-facing explanation English. "
            "Use 20% technical anchor and 80% practical reading: personality, career, money style, relationship pattern, risk boundaries, and long-term choices. "
            "Return valid JSON only."
        )
        user = (
            f"Return this schema: {json.dumps(schema_note, ensure_ascii=False)}\n\n"
            "ten_god_judgments index starts at 1 and follows tenGods.rows. Cover as many rows as possible. "
            "For shensha_notes, pillar must match the input English group names such as Year Pillar, Month Pillar, Day Pillar, Hour Pillar; star must match a ShenSha name in the input.\n\n"
            f"Structured chart packet:\n{json.dumps(packet, ensure_ascii=False)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
    schema_note = {
        "ten_god_judgments": [{"index": 1, "judgment": "用大白话说明这一行十神对客户性格、事业、财务、关系或长期选择的影响"}],
        "shensha_notes": [{"pillar": "年柱", "star": "天乙贵人", "note": "用客户能理解的话说明这个神煞在该柱的体现"}],
    }
    system = (
        "你是 Ming Atelier 的八字命理解释层。只改写十神分析里的“判断”和神煞体系里的“在该柱代表什么”。"
        "十神、柱(干/支)、通用解释、神煞名称、强度都以输入为准，不得新增不存在的十神或神煞。"
        "输出 20% 技术锚点、80% 客户自身解读：语言要通用、可读、贴合付费用户，说明这些信号如何影响性格、事业、赚钱方式、关系模式、风险边界或长期选择。"
        "不要写否定定式或模板话，直接解释这个信号在客户身上的现实表现。"
        "输出必须是合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"
    )
    user = (
        "请按以下 JSON schema 返回："
        f"{json.dumps(schema_note, ensure_ascii=False)}\n\n"
        "ten_god_judgments 的 index 从 1 开始，对应 tenGods.rows 的顺序，尽量覆盖全部十神行。"
        "shensha_notes 请覆盖输入 shensha 中的主要神煞，pillar 必须使用 年柱/月柱/日柱/时柱，star 必须使用输入里出现的神煞名。\n\n"
        "结构化命盘如下：\n"
        f"{json.dumps(packet, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def llm_relationship_prompt(packet: dict, lang: str = "zh") -> list[dict[str, str]]:
    if lang == "en":
        schema_note = {
            "relationship_rows": [
                ["Overall relationship pattern", "Relationship trend reading", "Use partner star, spouse palace, branch relations, major luck, or annual triggers"],
                ["Better dating window", "Years or stage", "Explain why these years/stages are better for forming a relationship"],
                ["Likely meeting context", "Years or context", "Ground it in annual luck, major luck, spouse palace, or partner-star activation"],
                ["Appearance / temperament", "Symbolic temperament", "Do not write body height or body type"],
                ["Likely industry / role", "Industry or role symbolism", "Must be different from temperament wording"],
                ["Mismatch type", "Unsuitable relationship type", "Connect chart risk to relationship boundaries"],
                ["Marriage-readiness window", "Years or stage", "Write maturity conditions, do not guarantee marriage"],
            ]
        }
        system = (
            "You are the English relationship outlook layer for Ming Atelier. Output relationship_rows only. "
            "Use the input partner stars, spouse palace, Ten-God distribution, branch combinations/clashes/punishments/harms/breaks, major luck, and 2026-2036 annual timing. Do not recalculate. "
            "Do not include height/body type. Appearance/temperament and industry/role must be different. "
            "Write for a paying client: 20% BaZi basis, 80% relationship pattern, partner standard, risk boundary, and timing window. "
            "Do not guarantee marriage or fate. Return valid JSON only."
        )
        user = (
            f"Return this schema: {json.dumps(schema_note, ensure_ascii=False)}\n\n"
            "Preserve the seven row themes and order. Do not reuse default computedSections wording.\n\n"
            f"Structured chart packet:\n{json.dumps(packet, ensure_ascii=False)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
    schema_note = {
        "relationship_rows": [
            ["未来关系波动", "对亲密关系整体走势的判断", "引用伴侣星、夫妻宫、合冲刑害、大运或流年触发"],
            ["适合恋爱窗口", "年份或阶段", "说明为什么这些年份或阶段更适合建立关系"],
            ["最可能遇到时间", "年份或阶段", "依据流年、大运、日支或伴侣星触发写"],
            ["外貌气质", "气质取象", "只写外貌/气质，不写行业角色"],
            ["从事行业/角色", "行业或角色取象", "必须写职业、行业或角色，不复用外貌气质原句"],
            ["不适配对象", "不适配类型", "结合盘面风险写关系边界"],
            ["结婚成熟窗口", "年份或阶段", "写关系成熟条件，不保证结婚"],
        ]
    }
    system = (
        "你是 Ming Atelier 的八字感情运势解释层。只输出 relationship_rows。"
        "必须基于输入里的伴侣星、夫妻宫、十神分布、地支合冲刑害、大运和 2026-2036 流年，不重新排盘。"
        "不要返回“身高/体型”。外貌气质与从事行业/角色必须是两种不同内容，不能同句复用。"
        "语言要给付费客户看得懂：20% 命理依据，80% 关系模式、择偶标准、风险边界和现实窗口。"
        "不得保证结婚或遇到正缘，不得恐吓。输出必须是合法 JSON，不要 Markdown。"
    )
    user = (
        "请按以下 JSON schema 返回："
        f"{json.dumps(schema_note, ensure_ascii=False)}\n\n"
        "七行主题必须完整保留，顺序也必须一致。不要沿用 computedSections 里的默认文案。\n\n"
        "结构化命盘如下：\n"
        f"{json.dumps(packet, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def llm_english_translation_prompt(packet: dict, issues: list[str] | None = None) -> list[dict[str, str]]:
    schema_note = {
        "useful_text": "Full English translation of the finalized Chinese useful-element reasoning.",
        "strength_reason": "Full English translation of the finalized Chinese Day-Master strength reasoning.",
        "career_rows": [["Theme", "Reading", "Reasoning"]],
        "wealth_intro": "Full English translation of the finalized Chinese ten-year wealth opening.",
        "income_notes": [{"index": 1, "text": "Full English condition text for this income tier."}],
        "income_stage_rows": [["Stage", "Income Reading", "Key Condition", "Risk"]],
        "annual_notes": [{"year": "2026", "note": "Full English translation of that year's finalized Chinese reading."}],
        "relationship_rows": [["Theme", "Reading", "Explanation"]],
        "monthly_notes": [{"month": "2026-02", "note": "Full English translation of that month's finalized Chinese reading."}],
        "june_2026_detail": "Full English translation of the finalized June 2026 focus.",
        "crisis_rows": [["Theme", "Chart Basis", "Real-World Action"]],
        "summary_paragraphs": ["Five or more full English summary paragraphs."],
        "ten_god_judgments": [{"index": 1, "judgment": "Full English translation of this finalized Chinese Ten-God judgment."}],
        "shensha_notes": [{"pillar_index": 1, "row_index": 1, "note": "Full English translation of this finalized Chinese ShenSha pillar reading."}],
        "shensha_balances": [{"pillar_index": 1, "text": "Full English translation of this pillar balance."}],
        "cross_shensha_balance": "Full English translation of the cross-pillar balance.",
        "branch_relation_rows": [["Relation", "Structure Signal", "Impact", "Resolution"]],
    }
    review_note = (
        "\nA previous translation attempt had these completeness issues. Correct every one of them: "
        + json.dumps(issues, ensure_ascii=False)
        if issues
        else ""
    )
    system = (
        "You are the bilingual delivery editor for Ming Atelier. The Chinese report has already been generated and reviewed. "
        "Translate the finalized client-visible Chinese text into polished English without recalculating, shortening, summarizing, or changing any conclusion. "
        "Preserve the same section structure, row count, year coverage, month coverage, evidence, practical advice, and emotional nuance. "
        "Keep Four Pillars, GanZhi, Ten Gods, ShenSha, major luck, annual/monthly pillars, scores, useful elements, and risk flags locked. "
        "Chinese technical names may be retained only when they identify a BaZi term; explanatory prose must be English. "
        "The English version should carry roughly 85% to 130% of the information volume of the Chinese source. Never compress a paragraph into a short sentence. "
        "Return valid JSON only."
    )
    user = (
        "Translate every field in currentVisibleSections using the exact schema below. "
        "annual_notes must contain all 11 years from 2026 through 2036. monthly_notes must contain every supplied 2026 month. "
        "career_rows, income_stage_rows, relationship_rows, crisis_rows, branch_relation_rows, Ten-God judgments, and ShenSha notes must preserve their source row counts and order. "
        "summary_paragraphs must preserve every source paragraph and its detail. Do not introduce new chart facts or generic filler."
        f"{review_note}\n\nSchema: {json.dumps(schema_note, ensure_ascii=False)}\n\n"
        f"Finalized Chinese source and locked chart packet:\n{json.dumps(packet, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_llm_json_text(content: str) -> dict | None:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def call_openai_json(messages: list[dict[str, str]]) -> dict | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(os.environ.get("MING_ATELIER_LLM_TEMPERATURE", "0.45")),
        "response_format": {"type": "json_object"},
    }
    req = urlrequest.Request(
        os.environ.get("OPENAI_CHAT_COMPLETIONS_URL", "https://api.openai.com/v1/chat/completions"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=int(os.environ.get("MING_ATELIER_LLM_TIMEOUT", "45"))) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        return parse_llm_json_text(content)
    except (KeyError, json.JSONDecodeError, TimeoutError, urlerror.URLError, urlerror.HTTPError):
        return None


def call_gemini_json(messages: list[dict[str, str]]) -> dict | None:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-pro-latest").replace("models/", "")
    system_text = "\n".join(item["content"] for item in messages if item.get("role") == "system")
    user_text = "\n\n".join(item["content"] for item in messages if item.get("role") != "system")
    payload = {
        "systemInstruction": {"parts": [{"text": system_text}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": float(os.environ.get("MING_ATELIER_LLM_TEMPERATURE", "0.45")),
            "responseMimeType": "application/json",
            "maxOutputTokens": int(os.environ.get("MING_ATELIER_LLM_MAX_OUTPUT_TOKENS", "12000")),
        },
    }
    req = urlrequest.Request(
        os.environ.get(
            "GEMINI_GENERATE_CONTENT_URL",
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        ),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=int(os.environ.get("MING_ATELIER_LLM_TIMEOUT", "60"))) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        parts = result["candidates"][0]["content"]["parts"]
        content = "\n".join(part.get("text", "") for part in parts)
        return parse_llm_json_text(content)
    except (KeyError, json.JSONDecodeError, TimeoutError, urlerror.URLError, urlerror.HTTPError):
        return None


def call_llm_json(messages: list[dict[str, str]]) -> dict | None:
    provider = llm_provider()
    if provider in {"gemini", "google"}:
        return call_gemini_json(messages)
    return call_openai_json(messages)


def valid_text(value, min_len: int = 2) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_len


def valid_rows(rows, width: int, min_rows: int = 1, max_rows: int = 20) -> bool:
    return (
        isinstance(rows, list)
        and min_rows <= len(rows) <= max_rows
        and all(isinstance(row, list) and len(row) == width and all(valid_text(cell) for cell in row) for row in rows)
    )


def apply_llm_sections(model: dict, llm: dict | None) -> bool:
    if not isinstance(llm, dict):
        return False
    changed = False
    elements = llm.get("useful_elements")
    if isinstance(elements, list):
        clean = [item for item in elements if item in {"金", "木", "水", "火", "土"}]
        if 1 <= len(clean) <= 3:
            model["useful_elements"] = unique(clean)
            if valid_text(llm.get("useful_text"), 12):
                model["useful_text"] = llm["useful_text"].strip()
            changed = True
    if valid_rows(llm.get("career_rows"), 3, 4, 8):
        model["career_rows"] = llm["career_rows"]
        changed = True
    if valid_text(llm.get("wealth_intro"), 30):
        model["wealth_tone"]["base"] = llm["wealth_intro"].strip()
        changed = True
    income_notes = llm.get("income_notes")
    if isinstance(income_notes, dict):
        updated = []
        for row in model["income_rows"]:
            note = income_notes.get(row[0])
            updated.append([row[0], row[1], row[2], note.strip() if valid_text(note, 15) else row[3]])
        model["income_rows"] = updated
        changed = True
    if valid_rows(llm.get("income_stage_rows"), 4, 3, 5):
        model["income_stage_rows"] = llm["income_stage_rows"]
        changed = True
    annual_notes = llm.get("annual_notes")
    if isinstance(annual_notes, list):
        by_year = {str(item.get("year")): item.get("note", "").strip() for item in annual_notes if isinstance(item, dict)}
        rows = []
        for row in model["annual_rows"]:
            rows.append(row[:10] + [by_year.get(row[0], row[10]) if valid_text(by_year.get(row[0]), 15) else row[10]])
        model["annual_rows"] = rows
        changed = True
    ten_god_judgments = llm.get("ten_god_judgments")
    if isinstance(ten_god_judgments, list):
        by_index = {}
        for item in ten_god_judgments:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index", 0)) - 1
            except (TypeError, ValueError):
                continue
            judgment = item.get("judgment", "").strip()
            if index >= 0 and valid_text(judgment, 25):
                by_index[index] = judgment
        if by_index:
            rows = []
            for index, row in enumerate(model["ten_god_rows"]):
                rows.append(row[:3] + [by_index.get(index, row[3])])
            model["ten_god_rows"] = rows
            changed = True
    if valid_rows(llm.get("relationship_rows"), 3, 5, 10):
        model["relationship_rows"] = llm["relationship_rows"]
        changed = True
    monthly_notes = llm.get("monthly_notes")
    if isinstance(monthly_notes, list):
        by_month = {str(item.get("month")): item.get("note", "").strip() for item in monthly_notes if isinstance(item, dict)}
        rows = []
        for row in model["monthly_rows"]:
            rows.append(row[:7] + [by_month.get(row[0], row[7]) if valid_text(by_month.get(row[0]), 15) else row[7]])
        model["monthly_rows"] = rows
        changed = True
    if valid_text(llm.get("june_2026_detail"), 30):
        model["june_2026_detail"] = llm["june_2026_detail"].strip()
        changed = True
    if valid_rows(llm.get("crisis_rows"), 3, 3, 6):
        model["crisis_rows"] = llm["crisis_rows"]
        changed = True
    shensha_notes = llm.get("shensha_notes")
    if isinstance(shensha_notes, list):
        note_map = {}
        for item in shensha_notes:
            if not isinstance(item, dict):
                continue
            pillar = str(item.get("pillar", "")).strip()
            star = str(item.get("star", "")).strip()
            note = str(item.get("note", "")).strip()
            if pillar and star and valid_text(note, 20):
                note_map[(pillar, star)] = note
        if note_map:
            updated = {}
            for pillar, rows in model["shensha_rows"].items():
                updated[pillar] = [row[:4] + [note_map.get((pillar, row[1]), row[4])] for row in rows]
            model["shensha_rows"] = updated
            changed = True
    summary = llm.get("summary_paragraphs")
    if isinstance(summary, list) and 3 <= len(summary) <= 7 and all(valid_text(item, 30) for item in summary):
        model["llm_summary_paragraphs"] = [item.strip() for item in summary]
        changed = True
    return changed


def english_translation_issues(source_model: dict, translated: dict | None) -> list[str]:
    if not isinstance(translated, dict):
        return ["translation response is missing or invalid JSON"]
    issues: list[str] = []
    expected_rows = {
        "career_rows": len(source_model.get("career_rows", [])),
        "income_stage_rows": len(source_model.get("income_stage_rows", [])),
        "relationship_rows": len(source_model.get("relationship_rows", [])),
        "crisis_rows": len(source_model.get("crisis_rows", [])),
        "branch_relation_rows": len(source_model.get("branch_relation_rows", [])),
    }
    for key, expected in expected_rows.items():
        actual = translated.get(key)
        if expected and (not isinstance(actual, list) or len(actual) != expected):
            issues.append(f"{key} must preserve {expected} rows")
    annual_years = {
        str(item.get("year"))
        for item in translated.get("annual_notes", [])
        if isinstance(item, dict)
    }
    expected_years = {str(row[0]) for row in source_model.get("annual_rows", [])}
    if annual_years != expected_years:
        issues.append("annual_notes must preserve every source year")
    monthly_keys = {
        str(item.get("month"))
        for item in translated.get("monthly_notes", [])
        if isinstance(item, dict)
    }
    expected_months = {str(row[0]) for row in source_model.get("monthly_rows", [])}
    if monthly_keys != expected_months:
        issues.append("monthly_notes must preserve every source month")
    summaries = translated.get("summary_paragraphs")
    expected_summaries = len(plain_summary_paragraphs({}, source_model))
    if not isinstance(summaries, list) or len(summaries) != expected_summaries:
        issues.append(f"summary_paragraphs must preserve {expected_summaries} paragraphs")
    ten_god_indexes = {
        int(item.get("index", 0))
        for item in translated.get("ten_god_judgments", [])
        if isinstance(item, dict) and str(item.get("index", "")).isdigit()
    }
    if len(ten_god_indexes) != len(source_model.get("ten_god_rows", [])):
        issues.append("ten_god_judgments must preserve every source row")
    expected_shensha = sum(len(rows) for rows in source_model.get("shensha_rows", {}).values())
    shensha_keys = {
        (int(item.get("pillar_index", 0)), int(item.get("row_index", 0)))
        for item in translated.get("shensha_notes", [])
        if isinstance(item, dict)
        and str(item.get("pillar_index", "")).isdigit()
        and str(item.get("row_index", "")).isdigit()
    }
    if len(shensha_keys) != expected_shensha:
        issues.append("shensha_notes must preserve every source row")
    source_text = " ".join(text for _, text in review_texts(source_model))
    translated_text = " ".join(
        str(value)
        for key, value in translated.items()
        if key not in {"useful_elements"}
    )
    if source_text and len(translated_text) < len(source_text) * 0.58:
        issues.append("English information volume is materially shorter than the Chinese source")
    return issues


def apply_english_translation(model: dict, translated: dict | None) -> bool:
    if not isinstance(translated, dict):
        return False
    changed = apply_llm_sections(model, translated)
    if valid_text(translated.get("useful_text"), 40):
        model["useful_text"] = translated["useful_text"].strip()
        changed = True
    if valid_text(translated.get("strength_reason"), 40):
        model["strength_reason"] = translated["strength_reason"].strip()
        changed = True
    income_notes = translated.get("income_notes")
    if isinstance(income_notes, list):
        by_index = {
            int(item.get("index", 0)) - 1: str(item.get("text", "")).strip()
            for item in income_notes
            if isinstance(item, dict) and str(item.get("index", "")).isdigit()
        }
        if by_index:
            model["income_rows"] = [
                row[:3] + [by_index.get(index, row[3]) if valid_text(by_index.get(index), 25) else row[3]]
                for index, row in enumerate(model.get("income_rows", []))
            ]
            changed = True
    branch_rows = translated.get("branch_relation_rows")
    if valid_rows(branch_rows, 4, len(model.get("branch_relation_rows", [])), len(model.get("branch_relation_rows", []))):
        model["branch_relation_rows"] = branch_rows
        changed = True
    notes = translated.get("shensha_notes")
    if isinstance(notes, list):
        note_map = {}
        for item in notes:
            if not isinstance(item, dict):
                continue
            try:
                key = (int(item.get("pillar_index", 0)) - 1, int(item.get("row_index", 0)) - 1)
            except (TypeError, ValueError):
                continue
            note = str(item.get("note", "")).strip()
            if key[0] >= 0 and key[1] >= 0 and valid_text(note, 25):
                note_map[key] = note
        if note_map:
            updated = {}
            for pillar_index, (pillar, rows) in enumerate(model.get("shensha_rows", {}).items()):
                updated[pillar] = [
                    row[:4] + [note_map.get((pillar_index, row_index), row[4])]
                    for row_index, row in enumerate(rows)
                ]
            model["shensha_rows"] = updated
            changed = True
    balances = translated.get("shensha_balances")
    if isinstance(balances, list):
        balance_map = {}
        for item in balances:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("pillar_index", 0)) - 1
            except (TypeError, ValueError):
                continue
            value = str(item.get("text", "")).strip()
            if index >= 0 and valid_text(value, 30):
                balance_map[index] = value
        if balance_map:
            model["shensha_balance"] = {
                pillar: balance_map.get(index, model["shensha_balance"].get(pillar, ""))
                for index, pillar in enumerate(model.get("shensha_rows", {}))
            }
            changed = True
    if valid_text(translated.get("cross_shensha_balance"), 35):
        model["cross_shensha_balance"] = translated["cross_shensha_balance"].strip()
        changed = True
    return changed


REVIEW_BANNED_PHRASES = [
    "高风险点在",
    "触发日支/关系宫",
    "触发月令/事业宫",
    "身强盘最怕动作过大",
    "先定边界再放量",
    "前期讲义气、后期算不清",
    "比劫夺财被引动",
    "不要只靠口头默契",
    "机会与挑战并存",
    "注意沟通",
]


def review_texts(model: dict) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for row in model.get("career_rows", []):
        texts.extend([("career", str(cell)) for cell in row])
    texts.append(("wealth_intro", model.get("wealth_tone", {}).get("base", "")))
    for row in model.get("income_stage_rows", []):
        texts.extend([("income_stage", str(cell)) for cell in row])
    for row in model.get("annual_rows", []):
        if len(row) > 10:
            texts.append((f"annual_{row[0]}", str(row[10])))
    for row in model.get("relationship_rows", []):
        texts.extend([("relationship", str(cell)) for cell in row])
    for row in model.get("monthly_rows", []):
        if len(row) > 7:
            texts.append((f"monthly_{row[0]}", str(row[7])))
    for row in model.get("crisis_rows", []):
        texts.extend([("crisis", str(cell)) for cell in row])
    for item in model.get("llm_summary_paragraphs", []):
        texts.append(("summary", str(item)))
    return [(key, text.strip()) for key, text in texts if text and text.strip()]


def repeated_sentence_issues(texts: list[tuple[str, str]]) -> list[str]:
    seen: dict[str, int] = {}
    for _, text in texts:
        for part in re.split(r"[。；;]\s*", text):
            clean = part.strip()
            if len(clean) >= 18:
                seen[clean] = seen.get(clean, 0) + 1
    return [f"重复句：{sentence[:42]}" for sentence, count in seen.items() if count >= 2]


def report_quality_issues(model: dict) -> list[str]:
    texts = review_texts(model)
    full_text = "\n".join(text for _, text in texts)
    issues: list[str] = []
    for phrase in REVIEW_BANNED_PHRASES:
        count = full_text.count(phrase)
        if count:
            issues.append(f"出现模板/禁用短语「{phrase}」{count}次")
    issues.extend(repeated_sentence_issues(texts)[:8])
    annual_notes = [row[10] for row in model.get("annual_rows", []) if len(row) > 10]
    if len(annual_notes) >= 8:
        openers = [note[:18] for note in annual_notes if len(note) >= 18]
        repeated_openers = {item for item in openers if openers.count(item) >= 2}
        for opener in sorted(repeated_openers):
            issues.append(f"年度说明开头重复：{opener}")
    relationship = {row[0]: row[1:] for row in model.get("relationship_rows", []) if len(row) >= 3}
    looks = " ".join(relationship.get("外貌气质", []))
    role = " ".join(relationship.get("从事行业/角色", []))
    if looks and role and looks == role:
        issues.append("感情运势中外貌气质与从事行业/角色完全重复")
    if len(full_text) < 1800:
        issues.append("私人订制板块总字数偏短，可能没有达到付费报告信息量")
    return unique(issues)


def llm_delivery_review_prompt(packet: dict, issues: list[str], lang: str = "zh") -> list[dict[str, str]]:
    if lang == "en":
        schema_note = {
            "career_rows": [["Theme", "Reading", "Reasoning"]],
            "wealth_intro": "Rewrite the ten-year wealth opening in plain English.",
            "income_stage_rows": [["Stage", "Income Reading", "Key Condition", "Risk"]],
            "annual_notes": [{"year": "2026", "note": "annual plain-English analysis"}],
            "relationship_rows": [["Theme", "Reading", "Explanation"]],
            "monthly_notes": [{"month": "2026-02", "note": "monthly action note"}],
            "june_2026_detail": "Focused note for June 2026.",
            "crisis_rows": [["Theme", "Chart Basis", "Real-World Action"]],
            "summary_paragraphs": ["5 plain-English summary paragraphs"],
        }
        system = (
            "You are Ming Atelier's English pre-delivery reviewer. Do not recalculate the chart. "
            "The report has QA issues such as repetition, template language, overly technical phrasing, or insufficient personalization. "
            "Rewrite the visible client sections while preserving Four Pillars, Ten Gods, ShenSha, major luck, annual/monthly pillars, scores, and risk flags. "
            "Every year and month must have its own tone and evidence. Avoid repeated sentence structures. "
            "Write all explanatory prose in English. Technical Chinese symbols may remain only as chart labels. Return valid JSON only."
        )
        user = (
            "Return replacement fields using the schema. annual_notes must cover 2026-2036; monthly_notes must cover all supplied 2026 months. "
            "relationship_rows must preserve the themes, exclude height/body type, and keep temperament separate from industry/role. "
            "summary_paragraphs should feel like a real paid summary: personality, career/industry, wealth years, relationship window, risk boundary, and timing advice.\n\n"
            f"Schema: {json.dumps(schema_note, ensure_ascii=False)}\n\n"
            f"QA issues: {json.dumps(issues, ensure_ascii=False)}\n\n"
            f"Locked chart and current report: {json.dumps(packet, ensure_ascii=False)}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
    schema_note = {
        "career_rows": [["主题", "判断", "依据"]],
        "wealth_intro": "重写未来十年财运开头，一段客户能听懂的大白话。",
        "income_stage_rows": [["阶段", "收入判断", "关键条件", "风险"]],
        "annual_notes": [{"year": "2026", "note": "该年年度大白话分析"}],
        "relationship_rows": [["主题", "判断", "说明"]],
        "monthly_notes": [{"month": "2026-02", "note": "该月行动建议"}],
        "june_2026_detail": "2026年6月甲午重点提示。",
        "crisis_rows": [["主题", "盘面依据", "现实动作"]],
        "summary_paragraphs": ["5段大白话总结"],
    }
    system = (
        "你是 Ming Atelier 的交付前审稿官。你不重新排盘，只检查并重写客户可见语言。"
        "当前报告已生成，但 QA 发现模板化、重复、术语堆砌或信息量不足。"
        "你必须在锁定四柱、十神、神煞、大运、流年、分数和风险旗标的前提下，重写客户真正会看的板块。"
        "不要复用旧句，不要写“触发日支/关系宫”“高风险点在”“先定边界再放量”等审稿问题里的句式。"
        "每一年、每个月都要有自己的语气和判断依据；同一个命理逻辑可以重复，但表达不能复制粘贴。"
        "输出必须是合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"
    )
    user = (
        "请按 schema 返回可替换字段。annual_notes 必须覆盖 2026-2036 共 11 年；monthly_notes 必须覆盖输入里的全部 2026 流月。"
        "relationship_rows 必须保留原有主题，不得出现身高/体型，外貌气质和行业角色不能复用同一句。"
        "summary_paragraphs 需要像一段真正的付费总结，覆盖性格、行业/事业、财运年份、感情窗口、风险边界和顺势建议。\n\n"
        f"schema: {json.dumps(schema_note, ensure_ascii=False)}\n\n"
        f"QA发现的问题：{json.dumps(issues, ensure_ascii=False)}\n\n"
        f"锁定命盘与当前报告如下：{json.dumps(packet, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def pre_delivery_review(data: dict, computed: dict, model: dict) -> None:
    issues = report_quality_issues(model)
    model["review_issues"] = issues
    model["review_status"] = "passed" if not issues else "needs_review"
    if not issues or not llm_report_enabled():
        return
    packet = llm_fact_packet(data, computed, model)
    packet["currentVisibleSections"] = {
        "careerRows": model.get("career_rows", []),
        "wealthIntro": model.get("wealth_tone", {}).get("base", ""),
        "incomeStageRows": model.get("income_stage_rows", []),
        "annualRows": model.get("annual_rows", []),
        "relationshipRows": model.get("relationship_rows", []),
        "monthlyRows": model.get("monthly_rows", []),
        "crisisRows": model.get("crisis_rows", []),
        "summaryParagraphs": plain_summary_paragraphs(data, model),
    }
    lang = "en" if is_english(data) else "zh"
    reviewed = call_llm_json(llm_delivery_review_prompt(packet, issues, lang))
    if apply_llm_sections(model, reviewed):
        remaining = report_quality_issues(model)
        model["review_issues"] = remaining
        model["review_status"] = "passed_after_llm_review" if not remaining else "reviewed_with_warnings"


def finalized_translation_packet(data: dict, computed: dict, model: dict) -> dict:
    packet = llm_fact_packet(data, computed, model)
    packet["currentVisibleSections"] = {
        "strengthReason": model.get("strength_reason", ""),
        "usefulText": model.get("useful_text", ""),
        "careerRows": model.get("career_rows", []),
        "wealthIntro": model.get("wealth_tone", {}).get("base", ""),
        "incomeRows": model.get("income_rows", []),
        "incomeStageRows": model.get("income_stage_rows", []),
        "annualRows": model.get("annual_rows", []),
        "relationshipRows": model.get("relationship_rows", []),
        "monthlyRows": model.get("monthly_rows", []),
        "june2026Detail": model.get("june_2026_detail", ""),
        "crisisRows": model.get("crisis_rows", []),
        "summaryParagraphs": plain_summary_paragraphs(data, model),
        "tenGodRows": model.get("ten_god_rows", []),
        "shenshaRows": model.get("shensha_rows", {}),
        "shenshaBalance": model.get("shensha_balance", {}),
        "crossShenshaBalance": model.get("cross_shensha_balance", ""),
        "branchRelationRows": model.get("branch_relation_rows", []),
    }
    return packet


def enrich_model_with_llm(data: dict, computed: dict, model: dict) -> None:
    model["llm_status"] = "disabled"
    output_english = is_english(data)
    source_data = dict(data)
    source_data["lang"] = "zh"
    if not llm_report_enabled():
        pre_delivery_review(source_data, computed, model)
        if output_english:
            localize_deep_model_en(data, model)
            model["translation_status"] = "fallback"
        return
    packet = llm_fact_packet(source_data, computed, model)
    changed = False
    llm = call_llm_json(llm_report_prompt(packet, "zh"))
    changed = apply_llm_sections(model, llm) or changed
    relationship_llm = call_llm_json(llm_relationship_prompt(packet, "zh"))
    changed = apply_llm_sections(model, relationship_llm) or changed
    detail_llm = call_llm_json(llm_detail_prompt(packet, "zh"))
    changed = apply_llm_sections(model, detail_llm) or changed
    model["llm_status"] = "applied" if changed else "fallback"
    pre_delivery_review(source_data, computed, model)
    if not output_english:
        return

    source_model = copy.deepcopy(model)
    translation_packet = finalized_translation_packet(source_data, computed, source_model)
    localize_deep_model_en(data, model)
    translated = call_llm_json(llm_english_translation_prompt(translation_packet))
    issues = english_translation_issues(source_model, translated)
    if issues:
        revised = call_llm_json(llm_english_translation_prompt(translation_packet, issues))
        revised_issues = english_translation_issues(source_model, revised)
        if len(revised_issues) < len(issues):
            translated = revised
            issues = revised_issues
    translated_changed = apply_english_translation(model, translated)
    model["translation_issues"] = issues
    model["translation_status"] = "passed" if translated_changed and not issues else "reviewed_with_warnings" if translated_changed else "fallback"
    if translated_changed:
        model["llm_status"] = "applied"


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
    annual = annual_rows(selected.getGanZhi() if selected else "", useful, context, dayun_rows)
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
    enrich_model_with_llm(data, computed, model)
    return model


def localize_deep_model_en(data: dict, model: dict) -> None:
    model["lang"] = "en"
    useful = [element_en(item) for item in model.get("useful_elements", [])]
    useful_text = ", ".join(useful) or "rhythm and structure"
    day_master_stem = model["analysis_context"]["day_stem"]
    day_master = STEM_EN.get(day_master_stem, f"{day_master_stem} {element_en(model['analysis_context']['day_element'])}")
    model["dominant"] = ", ".join(
        f"{element_en(k)} {v}%" for k, v in sorted(model.get("profile", {}).items(), key=lambda item: item[1], reverse=True)
    )
    model["day_strength_label"] = {"身强": "strong", "身弱": "weak", "中和": "balanced"}.get(model.get("day_strength_label"), model.get("day_strength_label", ""))
    model["useful_text"] = (
        f"The useful-element reading leans toward {useful_text}. This is not a 'missing element' rule; it is based on season, Day Master strength, visible pressure, hidden stems, branch interactions, and current luck-cycle conditions."
    )
    model["strength_reason"] = (
        f"The Day Master is {day_master}. The strength estimate is a model reading, not a medical or financial fact. It helps identify whether the client should expand through output/wealth signals, or first build support, structure, and risk control."
    )
    model["wealth_tone"]["base"] = (
        "The next ten years should be read as a rhythm of opportunity and containment. Money comes more easily when pricing, delivery, ownership, accounts, contracts, and cash-flow rules are written clearly before scale is pursued."
    )
    source_income = model.get("income_rows", [])
    tier_names = ["RMB 1M-5M / year", "RMB 5M-10M / year", "RMB 10M+ / year"]
    tier_labels = ["Million-level", "Five-million level", "Ten-million level"]
    tier_notes = [
        "This tier is most realistic when professional ability becomes a repeatable offer, client system, or productized service. Confidence estimate about 68%.",
        "This tier requires stronger operating structure: legal terms, payment rhythm, delivery ownership, team/channel leverage, and financial review. Confidence estimate about 58%.",
        "This tier is possible only when platform resources, team capacity, capital/supply chain support, and risk control can carry the scale. Confidence estimate about 45%.",
    ]
    model["income_rows"] = [
        [tier_labels[i], source_income[i][1] if i < len(source_income) else "0%", tier_names[i], tier_notes[i]]
        for i in range(3)
    ]
    model["career_rows"] = [
        ["Operating style", "Build with structure before scaling", f"With useful elements around {useful_text}, the career path works better when methods, standards, and review systems are clear."],
        ["Best-fit fields", "Strategy, product, operations, research, finance/risk, technology, consulting, or structured advisory work", "The chart favors turning knowledge and judgment into repeatable delivery."],
        ["Risk control", "Avoid vague partnerships and emotionally driven expansion", "If role, ownership, client attribution, and payment are unclear, opportunity can become consumption."],
        ["Growth method", "Use small tests, documented process, and staged commitments", "This turns chart pressure into execution rather than conflict."],
    ]
    model["income_stage_rows"] = [
        ["2026-2027", "Foundation and first acceleration", "Clarify pricing, contracts, delivery standards, and cash-flow rhythm.", "Do not over-promise before the operating system is stable."],
        ["2028-2029", "Client and resource activation", "Better for visible offers, repeatable products, stronger negotiation, and long-term clients.", "Money and relationship issues must not be mixed casually."],
        ["2030-2033", "Systemization and asset building", "Suitable for team, product, cross-border resources, data, licensing, or structured channels.", "Process cost rises; personal willpower alone is not enough."],
        ["2034-2036", "Repositioning and selective expansion", "Review what is truly scalable, then choose a narrower but stronger direction.", "Avoid new heavy commitments before the old system is cleaned up."],
    ]
    annual = []
    annual_templates = [
        "This is a year to move, but only after the operating terms are clear. Push visible offers and client conversion, while keeping payment schedule, refund terms, and delivery ownership written.",
        "The money signal is usable, but it needs containment. Let pricing, account control, and written scope carry the opportunity instead of relying on excitement or verbal trust.",
        "This year favors building an asset-like system: product, method, channel, documentation, recurring clients, or a team process. Avoid turning every opening into a heavy commitment.",
        "Relationship and money can pull on each other this year. If an opportunity involves affection, friendship, partnership, or shared resources, separate the emotional decision from the financial one.",
        "The chart reads this year as a maintenance-and-filter year. It is better for reviewing contracts, cleaning old obligations, and protecting cash flow than for forcing a large expansion.",
        "Pressure is higher than the visible opportunity. Slow down major promises, use professional review where needed, and treat any rushed signature or unclear split as a warning signal.",
    ]
    for index, row in enumerate(model.get("annual_rows", [])):
        year, ganzhi, dayun = row[0], row[1], row[2]
        career, wealth, relation, stress, loss, compliance = [int(row[i]) for i in [3, 4, 5, 6, 7, 9]]
        if loss >= 8 or compliance >= 8:
            action = annual_templates[5]
        elif wealth >= 8:
            action = annual_templates[1]
        elif career >= 8 or career >= wealth:
            action = annual_templates[2]
        elif relation >= 7:
            action = annual_templates[3]
        elif stress >= 7:
            action = annual_templates[4]
        else:
            action = annual_templates[index % len(annual_templates)]
        note = (
            f"In {year} ({ganzhi} / {ganzhi_en(ganzhi)}), while the major-luck pillar is {dayun} / {ganzhi_en(dayun)}, the scores show career {career}, wealth {wealth}, relationship {relation}, stress {stress}, loss-risk {loss}, and compliance {compliance}. "
            f"{action}"
        )
        display_row = row[:10]
        display_row[1] = bilingual_ganzhi(ganzhi)
        display_row[2] = bilingual_ganzhi(dayun)
        annual.append(display_row + [note])
    model["annual_rows"] = annual
    model["relationship_rows"] = [
        ["Overall relationship pattern", "Attraction needs definition and rhythm", "The spouse-star and spouse-palace signals should be read through real boundaries, not only chemistry."],
        ["Better dating window", "Years with lower risk and clearer commitment signals", "Move slowly in high-trigger years; use them to observe consistency rather than force certainty."],
        ["Likely meeting context", "Work, learning, projects, structured communities, or cross-border/online scenes", "The chart favors meeting through function and shared direction rather than pure randomness."],
        ["Appearance / temperament", "Clear, composed, professional, or emotionally contained", "This is symbolic temperament reading, not a fixed physical description."],
        ["Likely industry / role", "Finance, data, operations, consulting, technology, education, compliance, or structured service roles", "Look for someone who strengthens your reality system rather than only emotional heat."],
        ["Mismatch type", "Ambiguous, highly emotional, financially boundaryless, or controlling partners", "These types amplify the chart's relationship and money stress."],
        ["Marriage-readiness window", "When money, city, family responsibility, and long-term rhythm can be discussed plainly", "The chart does not guarantee marriage; it shows when a relationship becomes easier to land."],
    ]
    model["ten_god_rows"] = []
    for god, pillar, _meaning, _reading in ten_god_rows({"chart": model["chart"]}):
        pillar_label = "General position"
        for cn, en in PILLAR_EN.items():
            if pillar.startswith(cn):
                suffix = pillar.removeprefix(cn)
                english_terms = []
                for char in suffix:
                    if char in STEM_EN:
                        english_terms.append(STEM_EN[char])
                    elif char in BRANCH_EN:
                        english_terms.append(BRANCH_EN[char])
                pillar_label = en + suffix.replace("天干", " heavenly stem ").replace("地支", " earthly branch ").replace("藏", " hidden stem ")
                if english_terms:
                    pillar_label += "\n" + " / ".join(english_terms)
                break
        scene = next((scene for cn, scene in PILLAR_SCENE_EN.items() if pillar.startswith(cn)), "this life area")
        god_text = TEN_GOD_TEXT_EN.get(god, "a supporting signal in the chart")
        model["ten_god_rows"].append([
            bilingual_term_list([god], TEN_GOD_EN),
            pillar_label,
            god_text.capitalize() + ".",
            f"When this signal appears in {scene}, it describes how the client reacts in that arena: how they judge opportunity, handle pressure, set boundaries with people and money, and decide whether to invest more energy.",
        ])
    relation_rows = []
    for relation in model.get("branch_relation_rows", []):
        label = relation[0]
        if label == "无明显合冲刑害破":
            label = "No major combination/clash/punishment/harm/break detected"
        else:
            label = label.replace("地支冲刑害破：", "Branch interactions: ")
            label = label.replace("；", "; ")
            label = bilingual_branch_relation_text(label)
        relation_rows.append([
            label,
            "The chart contains interaction between branches; it should not be read pillar by pillar only.",
            "This can affect career rhythm, relationship stability, money retention, emotional swings, or timing pressure when activated by luck cycles.",
            "Use written agreements, payment terms, review checkpoints, communication boundaries, and exit conditions as practical resolution.",
        ])
    model["branch_relation_rows"] = relation_rows
    shensha_en = {}
    balance_en = {}
    for group, rows in model.get("shensha_rows", {}).items():
        group_en = PILLAR_EN.get(group, group)
        converted = []
        for row in rows:
            star = row[1]
            converted.append([
                row[0],
                bilingual_term_list([star], SHENSHA_TEXT_EN),
                row[2],
                SHENSHA_TEXT_EN.get(star, "Auxiliary ShenSha signal; read together with Ten Gods, branch relations, and luck cycles."),
                f"In the {group_en}, this signal mainly affects {PILLAR_SCENE_EN.get(group, 'the related life area')}. For the client, it shows where support, sensitivity, pressure, relationship pull, contract issues, or resource movement may be felt.",
            ])
        shensha_en[group_en] = converted
        balance_en[group_en] = (
            f"{group_en} ShenSha should be used as supporting evidence. Favorable stars show where help and skill may appear; pressure stars show where boundaries, documentation, and pacing are necessary."
        )
    model["shensha_rows"] = shensha_en
    model["shensha_balance"] = balance_en
    model["cross_shensha_balance"] = (
        "Across pillars, ShenSha do not decide good or bad alone. They refine the reading by showing where talent, help, pressure, solitude, mobility, or relationship triggers are likely to appear."
    )
    flow = model.get("flow_chart", {})
    if flow:
        flow["headers"] = ["Item", "Year Pillar", "Month Pillar", "Day Pillar", "Hour Pillar", "Major Luck", "Annual Luck", "Monthly Luck"]
        row_label_map = {
            "主星/干神": "Main Star / Stem Ten-God",
            "天干": "Heavenly Stem",
            "地支": "Earthly Branch",
            "藏干": "Hidden Stems",
            "支神": "Branch Ten-Gods",
            "纳音": "NaYin",
            "空亡": "Void Branches",
            "地势": "Growth Stage",
            "神煞": "ShenSha",
        }
        converted_rows = []
        for row in flow.get("rows", []):
            row_label = row_label_map.get(row[0], row[0])
            converted = [row_label]
            for cell in row[1:]:
                text = str(cell).replace("无明显主星", "No dominant ShenSha").replace("随流盘触发", "Activated by timing overlay")
                converted.append(bilingual_chart_cell(row_label, text))
            converted_rows.append(converted)
        flow["rows"] = converted_rows
        flow["dayun_strip"] = [
            [str(row[0]).replace("岁", ""), row[1], bilingual_ganzhi(row[2]), "Current major luck" if row[3] == "当前大运" else ""]
            for row in flow.get("dayun_strip", [])
        ]
        model["selected_dayun"] = bilingual_ganzhi(model.get("selected_dayun") or "未识别")
        flow["selected_dayun"] = bilingual_ganzhi(flow.get("selected_dayun") or "未识别")
        flow["flow_year"] = bilingual_ganzhi(flow.get("flow_year") or "")
        flow["flow_month"] = bilingual_ganzhi(flow.get("flow_month") or "")
    monthly = []
    for row in model.get("monthly_rows", []):
        monthly.append([row[0], bilingual_ganzhi(row[1]), f"{row[2]}\n{solar_term_en(row[2])}", *row[3:7], f"{row[0]} ({row[1]} / {ganzhi_en(row[1])}) is a month for controlled action. Keep the focus on one clear decision, verify the other side's response, and do not let emotion or urgency replace written confirmation."])
    model["monthly_rows"] = monthly
    model["june_2026_detail"] = (
        "June 2026 is a high-activation month. It can bring visibility, movement, and decisive communication, but it also magnifies impulse, unclear promises, and conflict around money or relationship boundaries. Delay irreversible commitments until the terms are written."
    )
    model["crisis_rows"] = [
        ["Partnership and split risk", "Peer/wealth interaction and branch triggers", "Do not rely on loyalty alone. Ownership, accounts, IP/data, payment, and exit terms must be written early."],
        ["Over-expansion risk", "Output and wealth signals can be activated before the system is ready", "Scale only after delivery, cash flow, and review standards are stable."],
        ["Relationship ambiguity", "Spouse-star and branch interactions can intensify emotional decisions", "Separate love, money, relocation, and business decisions instead of solving them all at once."],
        ["Compliance and contract risk", "Officer/killing and clash signals require rules", "Use professional review for large contracts, equity, debt, legal, medical, or investment matters."],
    ]
    model["llm_summary_paragraphs"] = [
        f"This chart is best read as a script of rhythm, boundaries, and choice. The Day Master is {day_master}, and the useful-element direction is {useful_text}. The core task is not to chase every opportunity, but to know when to move, when to hold structure, and when to stop emotional or financial leakage.",
        "In personality and work style, you are not suited to vague environments for too long. You do better when expectations, standards, and accountability are visible. When the system is clear, your judgment becomes an asset; when the system is vague, you may carry too much pressure for other people.",
        "Career and money improve when professional ability becomes a repeatable product, method, channel, or long-term client relationship. The highest-risk years are not necessarily the quiet years; they are the years when opportunity arrives faster than contracts, payment rules, and ownership boundaries.",
        "Relationship-wise, attraction alone is not enough. The right relationship should calm the decision system, not pull money, time, city choice, and career direction into one emotional knot. Slow commitment is not avoidance; for this chart, it is risk control.",
        "The practical advice is simple: build rules before scale, separate money from emotion, keep written records, and use timing as a way to choose sequence. Ming Atelier reads the chart so you can act with more clarity, not so you can hand your decisions to fate.",
    ]


def load_font(size: int, bold: bool = False):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_standard_visuals(run_id: str, elements: list[str], lang_en: bool = False) -> tuple[Path, Path]:
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
    draw.text((88, 82), "Ming Atelier · Useful Elements" if lang_en else "Ming Atelier · 喜用神", font=font_mid, fill="#f0c47a")
    draw.text((88, 132), "Five-element timing anchors" if lang_en else "Five-element remedy sigils", font=font_small, fill="#8d7b58")
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
        center_text(draw, (cx, cy), element_en(element) if lang_en else element, font_big, color)
        center_text(draw, (cx, 760), f"{element_en(element)} · Useful Element" if lang_en else f"{element} · 五行补足", font_mid, "#f0c47a")
    img.save(useful_path)
    crystal = PILImage.new("RGB", (1600, 920), "#0b0906")
    draw = ImageDraw.Draw(crystal)
    draw.rectangle((28, 28, 1572, 892), outline="#c7963f", width=4)
    draw.rectangle((58, 58, 1542, 862), outline="#3c2c12", width=2)
    draw.text((88, 82), "Ming Atelier · Crystal Anchors" if lang_en else "Ming Atelier · 适配水晶", font=font_mid, fill="#f0c47a")
    draw.text((88, 132), "Crystal anchors for daily reminders", font=font_small, fill="#8d7b58")
    source_rows = crystal_rows_en(elements[:2] or ["金", "水"]) if lang_en else crystal_rows(elements[:2] or ["金", "水"])
    for i, row in enumerate(source_rows):
        element, name, fit, _ = row
        element_key = next((key for key, value in ELEMENT_EN.items() if value == element), element)
        x = 160 + i * 700
        color = colors_map.get(element_key, "#d8b35f")
        draw.polygon([(x + 245, 260), (x + 390, 360), (x + 340, 620), (x + 150, 620), (x + 100, 360)], outline=color, fill="#151209")
        draw.line((x + 245, 260, x + 245, 620), fill=color, width=2)
        draw.line((x + 100, 360, x + 390, 360), fill=color, width=2)
        center_text(draw, (x + 245, 455), element, font_big, color)
        draw.text((x + 60, 690), f"{element} | {name}" if lang_en else f"{element}｜{name}", font=font_mid, fill=color)
        draw.text((x + 60, 740), fit[:34] if lang_en else fit[:18], font=font_small, fill="#e8d7b4")
    crystal.save(crystal_path)
    return useful_path, crystal_path


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def wrap_draw_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int = 3) -> list[str]:
    words = re.split(r"(\s+|/|,|;|·)", str(text or ""))
    lines: list[str] = []
    current = ""
    for word in words:
        if not word:
            continue
        trial = current + word
        if text_size(draw, trial, font)[0] <= max_width:
            current = trial
        else:
            if current.strip():
                lines.append(current.strip())
            current = word.strip()
        if len(lines) >= max_lines:
            break
    if current.strip() and len(lines) < max_lines:
        lines.append(current.strip())
    if len(lines) == max_lines and text_size(draw, lines[-1], font)[0] > max_width:
        while lines[-1] and text_size(draw, lines[-1] + "...", font)[0] > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "..."
    return lines


def short_en_name(value: str, mapping: dict[str, str]) -> str:
    mapped = mapping.get(str(value), "")
    short = mapped.split(" / ", 1)[0].split(":", 1)[0].strip()
    return re.sub(r"\s*\([^)]*\)", "", short).strip()


def hidden_bilingual_text(items: list[str]) -> str:
    parts = []
    for item in items:
        stem, _, element = str(item).partition("·")
        en_stem = STEM_EN.get(stem, "")
        en_element = ELEMENT_EN.get(element, element)
        parts.append(f"{item} {en_stem}/{en_element}".strip("/"))
    return " | ".join(parts) or "None"


def list_bilingual_text(items: list[str], mapping: dict[str, str], limit: int = 4) -> str:
    parts = []
    for item in items[:limit]:
        en = short_en_name(item, mapping)
        parts.append(f"{item} {en}".strip())
    return " | ".join(parts) or "None"


def chart_color_for(label: str, pillar: dict, cn: str = "") -> str:
    if label == "Heavenly Stem":
        return ELEMENT_COLOR.get(STEM_ELEMENT.get(str(cn)), "#ffe0a0")
    if label == "Earthly Branch":
        return ELEMENT_COLOR.get(BRANCH_ELEMENT.get(str(cn)), "#ffe0a0")
    if label in {"Hidden Stems", "Branch Ten-Gods", "ShenSha"}:
        return ELEMENT_COLOR.get(BRANCH_ELEMENT.get(str(pillar.get("branch", ""))), "#cdbb98")
    if label == "NaYin":
        element = next((item for item in ELEMENT_EN if str(cn).endswith(item)), "")
        return ELEMENT_COLOR.get(element, "#ffe0a0")
    if label == "Growth Stage":
        return "#f0c47a"
    if label == "Ten God":
        return ELEMENT_COLOR.get(STEM_ELEMENT.get(str(pillar.get("stem", ""))), "#ffe0a0")
    return "#ffe0a0"


def generate_bilingual_chart_image(run_id: str, model: dict) -> Path:
    path = GENERATED / f"{run_id}-english-bazi-chart.png"
    width, height = 2100, 1660
    margin = 58
    label_w = 235
    col_w = (width - margin * 2 - label_w) // 4
    row_heights = [86, 128, 128, 128, 168, 168, 126, 116, 116, 270]
    gold = "#d8ad55"
    gold2 = "#ffe0a0"
    line = "#6d4d1f"
    muted = "#cdbb98"
    panel = "#100b05"
    img = PILImage.new("RGB", (width, height), "#070503")
    draw = ImageDraw.Draw(img)
    title_font = load_font(56, True)
    subtitle_font = load_font(26)
    label_font = load_font(28, True)
    cn_font = load_font(48, True)
    en_font = load_font(22)
    small_font = load_font(19)

    draw.rectangle((24, 24, width - 24, height - 24), outline=gold, width=3)
    draw.rectangle((42, 42, width - 42, height - 42), outline="#2d2110", width=2)
    draw.text((margin, 54), "Ming Atelier · Four Pillars Chart", font=title_font, fill=gold2)
    draw.text((margin, 114), "Original BaZi symbols preserved with English labels underneath", font=subtitle_font, fill=muted)
    draw.ellipse((width - 205, 56, width - 82, 179), outline="#8b6b34", width=2)
    draw.line((width - 144, 72, width - 144, 163), fill="#8b6b34", width=2)
    draw.line((width - 188, 118, width - 101, 118), fill="#8b6b34", width=2)

    x0 = margin
    y0 = 190
    table_w = label_w + col_w * 4
    table_h = sum(row_heights)
    draw.rounded_rectangle((x0, y0, x0 + table_w, y0 + table_h), radius=10, outline=line, fill=panel, width=3)
    x_positions = [x0, x0 + label_w] + [x0 + label_w + col_w * i for i in range(1, 5)]
    y = y0
    for h in row_heights:
        draw.line((x0, y, x0 + table_w, y), fill=line, width=2)
        y += h
    draw.line((x0, y0 + table_h, x0 + table_w, y0 + table_h), fill=line, width=2)
    for x in x_positions:
        draw.line((x, y0, x, y0 + table_h), fill=line, width=2)

    headers = ["", "Year Pillar", "Month Pillar", "Day Pillar", "Hour Pillar"]
    pillars = model.get("chart", {}).get("pillars", [])
    for i, header in enumerate(headers):
        left = x0 if i == 0 else x0 + label_w + col_w * (i - 1)
        right = x0 + label_w if i == 0 else left + col_w
        tw, th = text_size(draw, header, label_font)
        draw.text((left + (right - left - tw) / 2, y0 + 26), header, font=label_font, fill=gold2)

    row_specs = [
        ("Ten God", lambda p: (p.get("gan_shen") or "日主", short_en_name(p.get("gan_shen") or "日主", TEN_GOD_EN))),
        ("Heavenly Stem", lambda p: (p.get("stem", ""), STEM_EN.get(p.get("stem", ""), ""))),
        ("Earthly Branch", lambda p: (p.get("branch", ""), BRANCH_EN.get(p.get("branch", ""), ""))),
        ("Hidden Stems", lambda p: ("", hidden_bilingual_text(p.get("hidden", [])))),
        ("Branch Ten-Gods", lambda p: ("", list_bilingual_text(p.get("zhi_shen", []), TEN_GOD_EN, 4))),
        ("NaYin", lambda p: (p.get("nayin", ""), NAYIN_EN.get(p.get("nayin", ""), ""))),
        ("Void", lambda p: (p.get("kongwang", "") or "None", "")),
        ("Growth Stage", lambda p: (p.get("dishi", ""), BRANCH_STAGE_EN.get(p.get("dishi", ""), ""))),
        ("ShenSha", lambda p: ("", list_bilingual_text(p.get("shen_sha", []), SHENSHA_TEXT_EN, 5))),
    ]
    y = y0 + row_heights[0]
    for row_index, (label, getter) in enumerate(row_specs, start=1):
        h = row_heights[row_index]
        draw.text((x0 + 22, y + 22), label, font=label_font, fill=gold)
        for col, pillar in enumerate(pillars):
            left = x0 + label_w + col_w * col
            center_x = left + col_w / 2
            cn, en = getter(pillar)
            cell_color = chart_color_for(label, pillar, cn)
            if cn:
                tw, _ = text_size(draw, cn, cn_font)
                draw.text((center_x - tw / 2, y + 18), cn, font=cn_font, fill=cell_color)
                en_y = y + 72
                max_lines = 2
            else:
                en_y = y + 24
                max_lines = 5 if label == "ShenSha" else 4
            for line_text in wrap_draw_text(draw, en, en_font if cn else small_font, col_w - 34, max_lines):
                tw, _ = text_size(draw, line_text, en_font if cn else small_font)
                draw.text((center_x - tw / 2, en_y), line_text, font=en_font if cn else small_font, fill=muted if cn else cell_color)
                en_y += 27
        y += h

    footer_y = y0 + table_h + 26
    notes = [
        "Natal chart image generated deterministically from the locked Four Pillars data.",
        "Use the Flow Overlay tab for major luck, annual luck, and monthly timing layers.",
    ]
    for note in notes:
        draw.text((margin, footer_y), note, font=subtitle_font, fill="#9f8d6b")
        footer_y += 36
    img.save(path)
    return path


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

    def cell_html(cell: str) -> str:
        parts = str(cell).splitlines()
        if len(parts) <= 1:
            return html.escape(str(cell))
        first, rest = parts[0], parts[1:]
        return html.escape(first) + "".join(f"<small class='en-sub'>{html.escape(part)}</small>" for part in rest if part)

    body = "".join(
        "<tr>" + "".join(f"<td>{cell_html(cell)}</td>" for cell in row) + "</tr>"
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
    lang_en = model.get("lang") == "en"
    headers = ["Rank", "ShenSha", "Strength", "General Meaning", "Pillar Meaning"] if lang_en else ["排名", "神煞", "强度", "通用解释", "在该柱代表什么"]

    def detail_title(value: str) -> str:
        parts = str(value).splitlines()
        if len(parts) <= 1:
            return html.escape(str(value))
        return html.escape(parts[0]) + "".join(f"<small class='en-sub'>{html.escape(part)}</small>" for part in parts[1:] if part)

    for group, rows in model["shensha_rows"].items():
        detail = "".join(
            f"<details class='star-detail'><summary>{detail_title(row[1])}<span>{html.escape(row[2])}</span></summary>"
            f"<p>{html.escape(row[3])}</p><p>{html.escape(row[4])}</p></details>"
            for row in rows
        )
        parts.append(
            f"<article class='card shensha-block'><h3>{html.escape(group + (' ShenSha' if lang_en else '神煞'))}</h3>"
            f"{html_table(headers, rows)}"
            f"<p class='balance'>{html.escape(model['shensha_balance'][group])}</p>{detail}</article>"
        )
    cross_title = "Cross-Pillar ShenSha Balance" if lang_en else "跨柱神煞制衡关系"
    parts.append(f"<article class='card'><h3>{cross_title}</h3><p>{html.escape(model['cross_shensha_balance'])}</p></article>")
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
    if model.get("lang") == "en":
        intro = (
            f"<div class='card liupan-note'><b>Flow Overlay Reference</b>"
            f"<p>Generated at {html.escape(flow['reference'])}. Current major luck: {html.escape(flow['selected_dayun'])}; "
            f"annual pillar: {html.escape(flow['flow_year'])}; monthly pillar: {html.escape(flow['flow_month'])}. "
            "This MVP uses the overlay to read natal chart, major luck, annual luck, and monthly luck in one console.</p></div>"
        )
        dayun_headers = ["Age Range", "Start Year", "Major Luck", "Status"]
        dayun_title = "Major-Luck Track"
    else:
        intro = (
            f"<div class='card liupan-note'><b>流盘参照</b>"
            f"<p>生成时间：{html.escape(flow['reference'])}。当前大运为 {html.escape(flow['selected_dayun'])}，"
            f"流年为 {html.escape(flow['flow_year'])}，流月为 {html.escape(flow['flow_month'])}。"
            "MVP 版先用来观察本命四柱与大运、流年、流月的叠加关系；后续可继续扩展为可切换年份、月份的完整流盘。</p></div>"
        )
        dayun_headers = ["年龄段", "起始年", "大运", "状态"]
        dayun_title = "大运轨道"
    return (
        intro
        + html_table(flow["headers"], flow["rows"])
        + f"<article class='card'><h3>{dayun_title}</h3>"
        + html_table(dayun_headers, flow["dayun_strip"])
        + "</article>"
    )


def bilingual_value(value: str, mapping: dict[str, str]) -> str:
    value = str(value or "")
    mapped = mapping.get(value)
    if mapped:
        return f"<b>{html.escape(value)}</b><small>{html.escape(mapped)}</small>"
    return f"<b>{html.escape(value)}</b>"


def hidden_bilingual(items: list[str]) -> str:
    if not items:
        return "<small>None</small>"
    parts = []
    for item in items:
        stem, _, element = str(item).partition("·")
        en_stem = STEM_EN.get(stem, "")
        en_element = ELEMENT_EN.get(element, element)
        sub = " / ".join(part for part in [en_stem, en_element] if part)
        parts.append(f"<span>{html.escape(item)}<small>{html.escape(sub)}</small></span>")
    return "".join(parts)


def text_bilingual_list(items: list[str], mapping: dict[str, str]) -> str:
    if not items:
        return "<small>None</small>"
    return "".join(
        f"<span>{html.escape(str(item))}<small>{html.escape(mapping.get(str(item), ''))}</small></span>"
        for item in items
    )


def natal_bilingual_chart(model: dict) -> str:
    headers = ["", "Year Pillar", "Month Pillar", "Day Pillar", "Hour Pillar"]
    pillars = model.get("chart", {}).get("pillars", [])

    def cell(content: str) -> str:
        return f"<td class='bazi-cell'>{content}</td>"

    rows = []
    row_specs = [
        ("Ten God", lambda p: text_bilingual_list([p.get("gan_shen") or "日主"], TEN_GOD_EN)),
        ("Heavenly Stem", lambda p: bilingual_value(p.get("stem", ""), STEM_EN)),
        ("Earthly Branch", lambda p: bilingual_value(p.get("branch", ""), BRANCH_EN)),
        ("Hidden Stems", lambda p: hidden_bilingual(p.get("hidden", []))),
        ("Branch Ten-Gods", lambda p: text_bilingual_list(p.get("zhi_shen", []), TEN_GOD_EN)),
        ("NaYin", lambda p: text_bilingual_list([p.get("nayin", "")], NAYIN_EN)),
        ("Void", lambda p: bilingual_value(p.get("kongwang", ""), BRANCH_EN) if len(str(p.get("kongwang", ""))) == 1 else f"<b>{html.escape(str(p.get('kongwang', '') or 'None'))}</b>"),
        ("Growth Stage", lambda p: text_bilingual_list([p.get("dishi", "")], BRANCH_STAGE_EN)),
        ("ShenSha", lambda p: text_bilingual_list(p.get("shen_sha", [])[:6], SHENSHA_TEXT_EN)),
    ]
    for label, getter in row_specs:
        rows.append("<tr><th>{}</th>{}</tr>".format(html.escape(label), "".join(cell(getter(p)) for p in pillars)))
    head = "".join(f"<th>{html.escape(item)}</th>" for item in headers)
    return (
        "<div class='bazi-board'><p class='bazi-caption'>English chart view keeps the original Chinese BaZi symbols, with English reading labels underneath.</p>"
        f"<div class='table-wrap'><table class='bazi-pillars'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>"
    )


def html_chart_console(model: dict, chart_url: str) -> str:
    flow = model["flow_chart"]
    lang_en = model.get("lang") == "en"
    tab_labels = ("Natal Chart", "Flow Overlay", "Major Luck") if lang_en else ("本命排盘", "流盘叠加", "大运")
    chart_alt = "black-gold BaZi chart" if lang_en else "黑金命盘图"
    flow_title = "Flow Overlay Reference" if lang_en else "流盘参照"
    flow_selected = str(flow["selected_dayun"]).replace("\n", " / ")
    flow_year = str(flow["flow_year"]).replace("\n", " / ")
    flow_month = str(flow["flow_month"]).replace("\n", " / ")
    flow_note = (
        f"Generated at {html.escape(flow['reference'])}. Current major luck: {html.escape(flow_selected)}; annual pillar: {html.escape(flow_year)}; monthly pillar: {html.escape(flow_month)}. The natal chart and current timing layers are read in the same console."
        if lang_en
        else f"生成时间：{html.escape(flow['reference'])}。当前大运 {html.escape(flow['selected_dayun'])}，流年 {html.escape(flow['flow_year'])}，流月 {html.escape(flow['flow_month'])}。此处把本命盘与当前运势叠在同一排盘控制台里看。"
    )
    dayun_headers = ["Age Range", "Start Year", "Major Luck", "Status"] if lang_en else ["年龄段", "起始年", "大运", "状态"]
    natal_panel = f"<div class='chart'><img src='{chart_url}' alt='{chart_alt}'></div>"
    return (
        "<div class='chart-console'>"
        "<div class='chart-tabs' role='tablist'>"
        f"<button class='active' data-chart-tab='natal'>{tab_labels[0]}</button>"
        f"<button data-chart-tab='flow'>{tab_labels[1]}</button>"
        f"<button data-chart-tab='dayun'>{tab_labels[2]}</button>"
        "</div>"
        f"<div class='chart-panel active' data-chart-panel='natal'>{natal_panel}</div>"
        f"<div class='chart-panel' data-chart-panel='flow'><div class='card liupan-note'><b>{flow_title}</b><p>{flow_note}</p></div>{html_table(flow['headers'], flow['rows'])}</div>"
        f"<div class='chart-panel' data-chart-panel='dayun'>{html_table(dayun_headers, flow['dayun_strip'])}</div>"
        "</div>"
    )


def html_card_table(rows: list[list[str]], title_key: str = "主题") -> str:
    return "<div class='grid two'>" + "".join(
        f"<article class='card'><b>{html.escape(row[0])}</b><p>{html.escape(row[1])}</p><small>{html.escape(row[2])}</small></article>"
        for row in rows
    ) + "</div>"


def plain_summary_paragraphs(data: dict, model: dict) -> list[str]:
    if model.get("llm_summary_paragraphs"):
        return model["llm_summary_paragraphs"]
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
    flag_text = "、".join(flag["title"] for flag in flags[:3])
    if flag_text:
        flag_text = f" 这张盘还触发了关键风控：{flag_text}。具体动作已经放在“核心危机”板块，这里不重复堆术语。"
    return [
        f"{name}这张盘的主题，不是被命盘推着走，而是要学会读懂自己的节奏，再决定怎么行动、怎么取舍、怎么顺势。日主判断为{model['day_strength_label']} {model['day_strength']}%，喜用落在{useful}。这里的喜用不是看五行缺什么就补什么，而是按月令、根气、透干、藏干、十神压力和大运触发共同判断。{flag_text} 所以人生里真正能托住你的，不是一次情绪很满的爆发，而是稳定的规则、稳定的专业、稳定的现金流，以及在关键时刻能让自己慢半拍的判断力。",
        f"性格上，十神里比较值得看的信号包括{ten_gods}，神煞里可参考{shensha}。这类组合通常不是“轻松躺赢”的类型，而是对环境、承诺、关系和资源质量很敏感：别人一句话可能会让你想很多，一个机会也容易让你同时看到希望和风险。好处是你不适合粗糙地活，只要方法论建立起来，就能把敏感变成洞察，把压力变成执行力；难处是不要总把所有责任先扛到自己身上，尤其在合作、感情和金钱问题上，要先看边界，再谈投入。",
        f"事业上，你现在填写的是“{industry} / {role}”，从命盘看当前方向{career_fit}。适合你的行业不是单纯热闹的赛道，而是能把经验沉淀为专业、流程、产品、咨询、运营、内容、数据、金融/法务/技术、供应链、教育训练或品牌方法论的路径。想增加机会，重点不是盲目扩大，而是把报价、合同、交付、复盘、客户筛选和现金流规则做出来；想规避风险，就要避开无账期、无退出、无责任人的合作，也不要为了证明自己能扛而接下过大的承诺。",
        f"财运上，这张盘不是靠刺激和硬冲取财，而是靠专业可信度、规则意识和现金流纪律把机会接住。未来十年里，比较适合努力搞钱的窗口集中在{money_text}，这些年份更适合谈客户、提价、收账、做产品化、做长期合作；风险较高的年份要重点看{risk_text}，尤其是合冲刑害、财官压力、比劫分利或现金流压力被引动的阶段，容易先答应、后核算，或者因为情面、面子、兴奋感而扩大成本。你不是不能冲，而是每一次冲之前都要有预算、合同、复盘和止损线。",
        f"感情上，适合恋爱或关系推进的窗口可优先看{relation_windows}；最可能遇到或明显推进的阶段，目前自动模型给到的是{meet_window}。这不是说其他时间没有缘分，而是这些窗口更容易出现能谈现实、谈规则、谈未来安排的人。比较适合你的关系，不是强刺激、强拉扯、强消耗，而是对方能尊重你的节奏，也愿意一起把钱、时间、城市、家庭责任讲清楚。若要看结婚，建议优先观察 2028-2033 之间能否出现稳定对象与现实条件同步成熟；如果关系长期只给情绪不给行动，就不要用等待消耗自己的运势。",
    ]


def report_plain_summary(data: dict, model: dict) -> str:
    return "\n\n".join(plain_summary_paragraphs(data, model))


def deep_report_pdf(data: dict, computed: dict, chart_png: Path, output: Path, model: dict | None = None) -> None:
    model = model or report_model(data, computed)
    lang_en = is_english(data)
    useful_img, crystal_img = generate_standard_visuals(output.stem, model["useful_elements"], lang_en)
    display_chart_png = generate_bilingual_chart_image(output.stem, model) if lang_en else chart_png
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
    pillars = bilingual_pillars(ec) if lang_en else f"{ec.getYear()} 年｜{ec.getMonth()} 月｜{ec.getDay()} 日｜{ec.getTime()} 时"
    day_master_display = f"{ec.getDayGan()}\n{STEM_EN.get(ec.getDayGan(), '')} | {model['day_strength_label']} {model['day_strength']}%" if lang_en else f"{ec.getDayGan()}｜{model['day_strength_label']}｜{model['day_strength']}%"
    raw_relation_text = "；".join(computed["chart"].get("relations") or [])
    relation_text = bilingual_branch_relation_text(raw_relation_text.replace("；", "; ")) if lang_en else raw_relation_text
    labels = {
        "title": f"{data.get('name') or 'Anonymous'} Destiny Report" if lang_en else f"{data.get('name') or '匿名'}命理报告",
        "sub": f"{data.get('calendar', 'Solar')} {data.get('birthDate')} {data.get('birthTime')} | {data.get('birthPlace', '')} | {GENDER_EN.get(data.get('gender', ''), data.get('gender', ''))}" if lang_en else f"{data.get('calendar', '阳历')} {data.get('birthDate')} {data.get('birthTime')}｜{data.get('birthPlace', '')}｜{data.get('gender', '')}",
        "note": "This report follows the Ming Atelier structure: locked chart facts first, then client-facing interpretation across personality, career, wealth, relationship, timing, risk, useful elements, and crystals. It is a cultural reading and does not replace professional advice." if lang_en else "本报告按 Ming Atelier 标准化结构生成：以原始盘、大运流年、十神、神煞、地支关系和现实问卷为基础，输出可复核的命理阅读。自动版用于客测交付，后续可叠加人工校准。",
        "raw": "1. Original Chart Information" if lang_en else "一、原始盘信息",
        "summary": "2. Plain-Language Summary" if lang_en else "二、大白话总结",
        "pattern": "3. Structure and Useful Elements" if lang_en else "三、分析：格局与用神体系",
        "career": "4. Career Development" if lang_en else "四、事业发展",
        "wealth": "5. Ten-Year Wealth and Income Tiers" if lang_en else "五、未来十年财运与收入层级",
        "relationship": "6. Relationship Outlook" if lang_en else "六、感情运势",
        "monthly": "7. 2026 Monthly Timing" if lang_en else "七、2026 年单独流月拆解",
        "crisis": "8. Core Constraints and Risks" if lang_en else "八、核心限制与潜在危机",
        "ten_god": "9. Ten-God Analysis" if lang_en else "九、十神分析",
        "shensha": "10. ShenSha System" if lang_en else "十、神煞体系",
        "elements": "11. Useful Elements" if lang_en else "十一、喜用神与五行补足",
        "crystals": "12. Crystal Recommendations" if lang_en else "十二、适配水晶建议",
    }
    story = [
        paragraph(labels["title"], styles["title"]),
        paragraph(labels["sub"], styles["sub"]),
        Spacer(1, 8),
        paragraph(labels["note"], styles["note"]),
        Spacer(1, 10),
        Image(str(display_chart_png), width=170 * mm, height=134 * mm) if lang_en else Image(str(chart_png), width=135 * mm, height=205 * mm),
        PageBreak(),
    ]
    story.extend([
        paragraph(labels["raw"], styles["h1"]),
        pdf_table([
            ["Item" if lang_en else "项目", "Content" if lang_en else "内容"],
            ["Four Pillars" if lang_en else "四柱", pillars],
            ["Day Master" if lang_en else "日主", day_master_display],
            ["Current / 2026 Luck Pillar" if lang_en else "当前/2026大运", model["selected_dayun"]],
            ["Five Element Estimate" if lang_en else "五行估计", model["dominant"]],
            ["Branch Relations" if lang_en else "地支关系", relation_text],
        ], [35 * mm, 135 * mm], font),
        paragraph(labels["summary"], styles["h1"]),
    ])
    for item in plain_summary_paragraphs(data, model):
        story.append(paragraph(item, styles["body"]))
    story.extend([
        paragraph(labels["pattern"], styles["h1"]),
        paragraph(model["strength_reason"], styles["body"]),
        paragraph(model["useful_text"], styles["body"]),
        pdf_table(([["Useful Element", "Practical Use"]] if lang_en else [["喜用", "行为落地"]]) + [[element_en(e) if lang_en else e, element_behavior_en(e) if lang_en else element_behavior(e)] for e in model["useful_elements"]], [28 * mm, 142 * mm], font),
        paragraph(labels["career"], styles["h1"]),
        pdf_table(([["Theme", "Reading", "Basis"]] if lang_en else [["主题", "判断", "依据"]]) + model["career_rows"], [30 * mm, 70 * mm, 70 * mm], font, 6.8),
        paragraph(labels["wealth"], styles["h1"]),
        paragraph(model["wealth_tone"]["base"], styles["body"]),
        pdf_table(([["Tier", "Probability", "Amount", "Conditions"]] if lang_en else [["层级", "概率", "金额", "条件"]]) + model["income_rows"], [24 * mm, 18 * mm, 38 * mm, 90 * mm], font, 6.8),
        pdf_table(([["Stage", "Income Reading", "Key Conditions", "Risk"]] if lang_en else [["阶段", "收入判断", "关键条件", "风险"]]) + model["income_stage_rows"], [26 * mm, 38 * mm, 58 * mm, 48 * mm], font, 6.6),
        pdf_table(([["Year", "Annual", "Luck", "Career", "Wealth", "Relation", "Stress", "Loss", "Home", "Compliance", "Plain-Language Annual Reading"]] if lang_en else [["年份", "流年", "大运", "事业", "财运", "感情", "健康/压力", "破财", "家宅", "合规", "年度大白话分析"]]) + model["annual_rows"], [12 * mm, 14 * mm, 16 * mm, 8 * mm, 8 * mm, 8 * mm, 13 * mm, 8 * mm, 8 * mm, 8 * mm, 75 * mm], font, 5.2),
        paragraph(labels["relationship"], styles["h1"]),
        pdf_table(([["Theme", "Reading", "Notes"]] if lang_en else [["主题", "判断", "说明"]]) + model["relationship_rows"], [35 * mm, 48 * mm, 87 * mm], font, 6.8),
        paragraph(labels["monthly"], styles["h1"]),
        paragraph(model["june_2026_detail"], styles["note"]),
        pdf_table(([["Month", "Pillar", "Solar Term", "Career", "Wealth", "Relation", "Risk", "Action"]] if lang_en else [["月份", "月柱", "节气", "事业", "财运", "关系", "风险", "行动建议"]]) + model["monthly_rows"], [18 * mm, 16 * mm, 28 * mm, 13 * mm, 13 * mm, 13 * mm, 13 * mm, 56 * mm], font, 6.0),
        paragraph(labels["crisis"], styles["h1"]),
        pdf_table(([["Risk", "Expression", "Control Method"]] if lang_en else [["风险", "表现", "控制方式"]]) + model["crisis_rows"], [28 * mm, 72 * mm, 70 * mm], font, 6.8),
        paragraph(labels["ten_god"], styles["h1"]),
        pdf_table(([["Ten God", "Pillar", "General Meaning", "Reading"]] if lang_en else [["十神", "柱(干/支)", "通用解释", "判断"]]) + model["ten_god_rows"], [22 * mm, 34 * mm, 52 * mm, 62 * mm], font, 6.8),
        paragraph("Ten-God balance: visible heavenly stems describe outward behavior; hidden stems describe the inner motive line. A serious reading must observe where each signal sits across year, month, day, and hour." if lang_en else "十神制衡关系：外显天干决定可见行为，地支藏干决定暗线动机。判断时不能只看一个十神，要看它在年、月、日、时四个位置分别作用于圈层、事业、自我关系和长期项目。", styles["body"]),
        paragraph("Branch relation balance" if lang_en else "地支关系制衡", styles["body"]),
        pdf_table(([["Relation", "Structure Signal", "Possible Impact", "Practical Resolution"]] if lang_en else [["关系", "结构提示", "可能影响", "现实制化"]]) + model["branch_relation_rows"], [34 * mm, 43 * mm, 48 * mm, 45 * mm], font, 6.8),
        paragraph(labels["shensha"], styles["h1"]),
    ])
    for group, rows in model["shensha_rows"].items():
        story.append(paragraph(group, styles["body"]))
        story.append(pdf_table(([["Rank", "ShenSha", "Strength", "General Meaning", "Pillar Meaning"]] if lang_en else [["排名", "神煞", "强度", "通用解释", "在该柱代表什么"]]) + rows, [14 * mm, 24 * mm, 18 * mm, 58 * mm, 56 * mm], font, 6.6))
        story.append(paragraph(model["shensha_balance"][group], styles["body"]))
        story.append(Spacer(1, 5))
    story.extend([
        paragraph(model["cross_shensha_balance"], styles["body"]),
        paragraph(labels["elements"], styles["h1"]),
        Image(str(useful_img), width=170 * mm, height=96 * mm),
        paragraph(labels["crystals"], styles["h1"]),
        Image(str(crystal_img), width=170 * mm, height=96 * mm),
        pdf_table(([["Element", "Recommendation", "Fit", "Use"]] if lang_en else [["五行", "建议", "适配点", "使用方式"]]) + (crystal_rows_en(model["useful_elements"]) if lang_en else crystal_rows(model["useful_elements"])), [18 * mm, 38 * mm, 54 * mm, 60 * mm], font, 6.8),
    ])
    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    doc.build(story)


def deep_report_html(data: dict, computed: dict, chart_png: Path, output: Path, model: dict | None = None) -> None:
    model = model or report_model(data, computed)
    lang_en = is_english(data)
    useful_img, crystal_img = generate_standard_visuals(output.stem, model["useful_elements"], lang_en)
    display_chart_png = generate_bilingual_chart_image(output.stem, model) if lang_en else chart_png
    ec = model["ec"]
    raw_title = f"{data.get('name') or 'Anonymous'} Destiny Report" if lang_en else f"{data.get('name') or '匿名'}命理报告"
    title = html.escape(raw_title)
    chart_url = f"/generated/{display_chart_png.name}"
    useful_url = f"/generated/{useful_img.name}"
    crystal_url = f"/generated/{crystal_img.name}"
    sections = (
        [("raw", "Original Chart"), ("summary", "Plain Summary"), ("pattern", "Structure"), ("career", "Career"), ("wealth", "Ten-Year Wealth"), ("relationship", "Relationship"), ("monthly", "2026 Monthly"), ("crisis", "Core Risks"), ("ten-god", "Ten Gods"), ("shensha", "ShenSha"), ("elements", "Useful Elements"), ("crystals", "Crystals")]
        if lang_en
        else [("raw", "原始盘信息"), ("summary", "大白话总结"), ("pattern", "格局与用神"), ("career", "事业发展"), ("wealth", "未来十年财运"), ("relationship", "感情运势"), ("monthly", "2026流月"), ("crisis", "核心危机"), ("ten-god", "十神分析"), ("shensha", "神煞体系"), ("elements", "喜用神"), ("crystals", "适配水晶")]
    )
    nav = "".join(f"<a href='#{sid}'>{html.escape(label)}</a>" for sid, label in sections)
    raw_relation_text = "；".join(computed["chart"].get("relations") or [])
    relation_text = bilingual_branch_relation_text(raw_relation_text.replace("；", "; ")) if lang_en else raw_relation_text
    risk_year = max(model["annual_rows"], key=lambda row: int(row[6]) + int(row[7]) + int(row[9]))
    useful_text = ", ".join(element_en(e) for e in model["useful_elements"]) if lang_en else "、".join(model["useful_elements"]) or "节奏"
    current_luck_display = model["selected_dayun"] if lang_en else model["selected_dayun"]
    risk_year_display = f"{risk_year[0]} {risk_year[1]}" if not lang_en else f"{risk_year[0]} {str(risk_year[1]).replace(chr(10), ' / ')}"
    kpis = [
        ["Day-Master Strength" if lang_en else "身强估计", f"{model['day_strength_label']} {model['day_strength']}%", model["strength_reason"]],
        ["Core Useful Elements" if lang_en else "核心喜用", useful_text, model["useful_text"]],
        ["Current Luck Pillar" if lang_en else "当前大运", current_luck_display, "Annual timing should be read together with the current major-luck cycle." if lang_en else "以 2026 所在大运为基准，所有流年判断均需与大运叠加。"],
        ["Highest-Risk Year" if lang_en else "风险最高年", risk_year_display, compact_flow_note(risk_year[10])],
    ]
    def multiline_html(value: str) -> str:
        parts = str(value).splitlines()
        if len(parts) <= 1:
            return html.escape(str(value))
        return html.escape(parts[0]) + "".join(f"<small class='en-sub'>{html.escape(part)}</small>" for part in parts[1:] if part)

    kpi_html = "".join(f"<div class='kpi'><span>{html.escape(k[0])}</span><b>{multiline_html(k[1])}</b><p>{html.escape(k[2])}</p></div>" for k in kpis)
    monthly_html = "".join(
        f"<article class='month'><i></i><b>{html.escape(row[0])}｜{multiline_html(row[1])}</b><em>{multiline_html(row[2])}</em>"
        f"<p>{html.escape(row[7])}</p><small>{'Career' if lang_en else '事业'} {row[3]} / {'Wealth' if lang_en else '财运'} {row[4]} / {'Relationship' if lang_en else '关系'} {row[5]} / {'Risk' if lang_en else '风险'} {row[6]}</small></article>"
        for row in model["monthly_rows"]
    )
    chart_console = html_chart_console(model, chart_url)
    summary_html = "".join(f"<p>{html.escape(item)}</p>" for item in plain_summary_paragraphs(data, model))
    output.write_text(f"""<!doctype html>
<html lang="{'en' if lang_en else 'zh-CN'}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><link rel="stylesheet" href="/pages.css">
<style>
	body{{background:#080604;color:#f7ead2}}.scroll-progress{{position:fixed;top:0;left:0;height:3px;background:#d8b35f;z-index:80;width:0}}.report-nav{{position:sticky;top:70px;z-index:20;background:rgba(8,6,4,.9);backdrop-filter:blur(12px);border-block:1px solid rgba(216,179,95,.22);overflow:auto;white-space:nowrap}}.report-nav .shell{{display:flex;gap:18px;padding:12px 20px}}.report-nav a{{color:#e8d7b4;text-decoration:none;font-size:13px}}.hero{{min-height:82vh;display:grid;align-items:center;padding:98px 0 56px;background:radial-gradient(circle at 50% 18%,rgba(216,179,95,.24),transparent 34%),linear-gradient(180deg,#0d0905,#080604);position:relative;overflow:hidden}}.hero:before{{content:"命";position:absolute;right:7vw;top:10vh;font-size:34vw;line-height:1;color:rgba(216,179,95,.07);animation:breathe 6s ease-in-out infinite}}.hero h1{{font-size:56px;line-height:1.08;max-width:760px;color:#f7ead2}}.lead{{max-width:760px;color:#e8d7b4}}.hero-actions{{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}}.print-btn{{border:1px solid rgba(216,179,95,.5);background:#d8b35f;color:#090604;border-radius:6px;padding:12px 18px;text-decoration:none;font-weight:700;cursor:pointer}}.panel{{max-width:1160px;margin:0 auto;padding:46px 20px;border-top:1px solid rgba(216,179,95,.2)}}.panel h2{{color:#f0c47a;font-size:28px}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}.grid.two{{grid-template-columns:repeat(2,minmax(0,1fr))}}.grid.three{{grid-template-columns:repeat(3,minmax(0,1fr))}}.card,.kpi{{border:1px solid rgba(216,179,95,.28);background:rgba(20,15,8,.72);border-radius:8px;padding:18px;box-shadow:0 18px 44px rgba(0,0,0,.18);transition:transform .25s ease,border-color .25s ease}}.card:hover,.kpi:hover{{transform:translateY(-3px);border-color:rgba(240,196,122,.58)}}.kpi b{{display:block;color:#f0c47a;font-size:25px;line-height:1.2;margin:8px 0}}.kpi p,.card small{{color:#cdbb98}}.chart-console{{margin-top:22px;border:1px solid rgba(216,179,95,.3);border-radius:8px;background:rgba(12,9,5,.82);padding:14px}}.chart-tabs{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}}.chart-tabs button{{border:1px solid rgba(216,179,95,.35);background:rgba(216,179,95,.08);color:#e8d7b4;border-radius:6px;padding:9px 12px;cursor:pointer;font:inherit;white-space:nowrap}}.chart-tabs button.active{{background:#d8b35f;color:#090604}}.chart-panel{{display:none}}.chart-panel.active{{display:block}}.table-wrap{{overflow:auto;border:1px solid rgba(216,179,95,.22);border-radius:8px;margin-top:14px}}table{{border-collapse:collapse;width:100%;min-width:850px}}th,td{{border-bottom:1px solid rgba(216,179,95,.16);padding:11px 12px;text-align:left;vertical-align:top}}th{{color:#f0c47a;background:rgba(216,179,95,.08)}}td{{color:#ead9b7}}td .en-sub,.kpi .en-sub,.month .en-sub{{display:block;margin-top:4px;color:#cdbb98;font-size:.72em;line-height:1.25}}tr:hover td{{background:rgba(216,179,95,.05)}}.bazi-caption{{margin:6px 0 10px;color:#cdbb98}}.bazi-pillars{{min-width:920px}}.bazi-cell b{{display:block;color:#ffe0a0;font-size:24px;line-height:1.1}}.bazi-cell small{{display:block;color:#cdbb98;font-size:12px;line-height:1.25;margin-top:3px}}.bazi-cell span{{display:block;margin-bottom:6px}}.chart-reference{{max-width:960px;opacity:.96}}.chart{{max-width:980px;margin:22px auto;animation:softGlow 4s ease-in-out infinite}}.chart img,.god-art img{{width:100%;height:auto;object-fit:contain;border:1px solid rgba(216,179,95,.35);border-radius:8px}}.god-art{{animation:lineDrift 5s ease-in-out infinite}}.bar-track{{height:10px;border-radius:99px;background:rgba(216,179,95,.13);overflow:hidden;margin:12px 0}}.bar{{display:block;height:100%;width:var(--w);border-radius:99px;background:linear-gradient(90deg,#d8b35f,#8f6a2a);animation:barGrow 1.2s ease both}}.income-band b,.warning b{{color:#f0c47a}}.income-band strong{{display:block;font-size:28px;color:#f7ead2;margin-top:8px}}.balance{{color:#dcc796}}details.star-detail{{border-top:1px solid rgba(216,179,95,.18);padding:10px 0}}details.star-detail summary{{cursor:pointer;color:#f0c47a}}details.star-detail summary span{{float:right;color:#d8b35f}}.timeline{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}.month{{position:relative;border:1px solid rgba(216,179,95,.22);border-radius:8px;padding:16px 16px 16px 42px;background:rgba(20,15,8,.65)}}.month i{{position:absolute;left:16px;top:22px;width:10px;height:10px;border-radius:50%;background:#d8b35f;box-shadow:0 0 0 0 rgba(216,179,95,.5);animation:pulse 2.2s infinite}}.month b,.month em{{display:block;color:#f0c47a;font-style:normal}}.fade{{opacity:0;transform:translateY(18px);transition:opacity .7s ease,transform .7s ease}}.fade.show{{opacity:1;transform:none}}footer{{padding:34px 20px;color:#9f8d6b}}@keyframes breathe{{50%{{transform:scale(1.04);opacity:.8}}}}@keyframes softGlow{{50%{{filter:drop-shadow(0 0 22px rgba(216,179,95,.26))}}}}@keyframes barGrow{{from{{width:0}}to{{width:var(--w)}}}}@keyframes pulse{{70%{{box-shadow:0 0 0 12px rgba(216,179,95,0)}}100%{{box-shadow:0 0 0 0 rgba(216,179,95,0)}}}}@keyframes lineDrift{{50%{{transform:translateY(-7px)}}}}@media(max-width:760px){{.hero h1{{font-size:38px}}.grid,.grid.two,.grid.three,.timeline{{grid-template-columns:1fr}}.report-nav{{top:64px}}table{{min-width:760px}}.bazi-pillars{{min-width:900px}}.chart-tabs button{{flex:1 1 31%;font-size:13px}}}}
	</style></head>
		<body><header class="top"><nav class="shell nav"><a class="brand" href="/{'?lang=en' if lang_en else ''}"><img src="/assets/ming-four-pillars-mark.png"><span>Ming Atelier<small>{'Destiny Readings' if lang_en else '命理工坊'}</small></span></a><div class="links"><a href="/{'?lang=en' if lang_en else ''}">{'Home' if lang_en else '首页'}</a><a href="/questionnaire.html{'?lang=en' if lang_en else ''}">{'Intake' if lang_en else '问卷'}</a><a href="/divination.html{'?lang=en' if lang_en else ''}">{'Divination' if lang_en else '起卦'}</a></div></nav></header>
		<div class="scroll-progress" id="scrollProgress"></div><main>
	<section class="hero"><div class="shell fade"><p class="eyebrow">Ming Atelier · Eastern Destiny Readings</p><h1>{title}</h1><p class="lead">{'Using the Four Pillars as the base map, this report reads personality, rhythm, choices, and relationships: how you act, what you choose, and how you move with timing.' if lang_en else '以八字四柱为底图，读性格、节奏、选择与关系。关于你如何行动、如何取舍、如何顺势。'}</p><div class="hero-actions"><button class="print-btn" onclick="window.print()">{'Save PDF' if lang_en else '保存 PDF'}</button><a class="print-btn" href="/{'?lang=en' if lang_en else ''}">{'Back Home' if lang_en else '回到主页'}</a></div></div></section><nav class="report-nav"><div class="shell">{nav}</div></nav>
	<section class="panel fade" id="raw"><h2>{'Original Chart Information' if lang_en else '原始盘信息'}</h2><div class="grid">{kpi_html}</div>{chart_console}{html_table(["Item" if lang_en else "项目","Content" if lang_en else "内容"], [["Four Pillars" if lang_en else "四柱", bilingual_pillars(ec) if lang_en else f"{ec.getYear()} 年｜{ec.getMonth()} 月｜{ec.getDay()} 日｜{ec.getTime()} 时"], ["Five Element Estimate" if lang_en else "五行估计", model["dominant"]], ["Branch Relations" if lang_en else "地支关系", relation_text]])}</section>
	<section class="panel fade" id="summary"><h2>{'Plain-Language Summary' if lang_en else '大白话总结'}</h2><div class="card">{summary_html}</div></section>
	<section class="panel fade" id="pattern"><h2>{'Structure and Useful Elements' if lang_en else '格局与用神体系'}</h2><div class="card"><p>{html.escape(model["strength_reason"])}</p><p>{html.escape(model["useful_text"])}</p></div>{html_table(["Useful Element" if lang_en else "喜用","Practical Use" if lang_en else "行为落地"], [[element_en(e) if lang_en else e, element_behavior_en(e) if lang_en else element_behavior(e)] for e in model["useful_elements"]])}</section>
	<section class="panel fade" id="career"><h2>{'Career Development' if lang_en else '事业发展'}</h2>{html_card_table(model["career_rows"])}</section>
	<section class="panel fade" id="wealth"><h2>{'Ten-Year Wealth and Income Tiers' if lang_en else '未来十年财运与收入层级'}</h2><div class="card"><p>{html.escape(model["wealth_tone"]["base"])}</p></div>{html_income_cards(model)}{html_table(["Stage" if lang_en else "阶段","Income Reading" if lang_en else "收入判断","Key Conditions" if lang_en else "关键条件","Risk" if lang_en else "风险"], model["income_stage_rows"])}{html_table(["Year" if lang_en else "年份","Annual" if lang_en else "流年","Luck" if lang_en else "大运","Career" if lang_en else "事业","Wealth" if lang_en else "财运","Relation" if lang_en else "感情","Stress" if lang_en else "健康/压力","Loss" if lang_en else "破财","Home" if lang_en else "家宅","Compliance" if lang_en else "合规","Plain-Language Annual Reading" if lang_en else "年度大白话分析"], model["annual_rows"])}</section>
	<section class="panel fade" id="relationship"><h2>{'Relationship Outlook' if lang_en else '感情运势'}</h2>{html_table(["Theme" if lang_en else "主题","Reading" if lang_en else "判断","Notes" if lang_en else "说明"], model["relationship_rows"])}</section>
	<section class="panel fade" id="monthly"><h2>{'2026 Monthly Timing' if lang_en else '2026 年单独流月拆解'}</h2><div class="card warning"><b>{'June 2026 Focus' if lang_en else '6 月甲午重点提示'}</b><p>{html.escape(model["june_2026_detail"])}</p></div><div class="timeline">{monthly_html}</div></section>
	<section class="panel fade" id="crisis"><h2>{'Core Constraints and Risks' if lang_en else '核心限制与潜在危机'}</h2>{html_card_table(model["crisis_rows"])}</section>
	<section class="panel fade" id="ten-god"><h2>{'Ten-God Analysis' if lang_en else '十神分析'}</h2>{html_table(["Ten God" if lang_en else "十神","Pillar" if lang_en else "柱(干/支)","General Meaning" if lang_en else "通用解释","Reading" if lang_en else "判断"], model["ten_god_rows"])}<div class="grid two"><article class="card"><b>{'Ten-God Balance' if lang_en else '十神制衡关系'}</b><p>{'Visible heavenly stems describe outward behavior; hidden stems describe the inner motive line. A serious reading must observe where each signal sits across year, month, day, and hour.' if lang_en else '外显天干决定可见行为，地支藏干决定暗线动机。判断时不能只看一个十神，要看它在年、月、日、时四个位置分别作用于圈层、事业、自我关系和长期项目。'}</p></article><article class="card"><b>{'Branch Relations and Resolution' if lang_en else '地支合冲与大盘制化'}</b>{html_table(["Relation" if lang_en else "关系","Structure Signal" if lang_en else "盘面含义","Impact" if lang_en else "对大盘影响","Resolution" if lang_en else "制化/化解方式"], model["branch_relation_rows"])}</article></div></section>
	<section class="panel fade" id="shensha"><h2>{'ShenSha System' if lang_en else '神煞体系'}</h2>{html_shensha_tables(model)}</section>
	<section class="panel fade elements" id="elements"><h2>{'Useful Elements' if lang_en else '喜用神'}</h2><div class="god-art"><img src="{useful_url}" alt="{'Useful element sigils' if lang_en else '喜用神图'}"></div>{html_table(["Useful Element" if lang_en else "喜用","Practical Use" if lang_en else "行为落地"], [[element_en(e) if lang_en else e, element_behavior_en(e) if lang_en else element_behavior(e)] for e in model["useful_elements"]])}</section>
	<section class="panel fade" id="crystals"><h2>{'Crystal Recommendations' if lang_en else '适配水晶建议'}</h2><div class="god-art"><img src="{crystal_url}" alt="{'Crystal recommendations' if lang_en else '适配水晶图'}"></div>{html_table(["Element" if lang_en else "五行","Recommendation" if lang_en else "建议","Fit" if lang_en else "适配点","Use" if lang_en else "使用方式"], crystal_rows_en(model["useful_elements"]) if lang_en else crystal_rows(model["useful_elements"]))}</section></main>
	<footer class="shell">{'Ming Atelier | Automated standard report for testing. Important life decisions should be reviewed with real-world evidence and professional advice where needed.' if lang_en else 'Ming Atelier｜命理工坊。自动标准版用于客测交付，关键人生决策建议叠加人工复核。'}</footer><script>const p=document.getElementById('scrollProgress');addEventListener('scroll',()=>{{const h=document.documentElement; p.style.width=((h.scrollTop)/(h.scrollHeight-h.clientHeight)*100)+'%';}});const io=new IntersectionObserver(es=>es.forEach(e=>e.isIntersecting&&e.target.classList.add('show')),{{threshold:.14}});document.querySelectorAll('.fade').forEach(el=>io.observe(el));document.querySelectorAll('[data-chart-tab]').forEach(btn=>btn.addEventListener('click',()=>{{const target=btn.dataset.chartTab;document.querySelectorAll('[data-chart-tab]').forEach(b=>b.classList.toggle('active',b===btn));document.querySelectorAll('[data-chart-panel]').forEach(panel=>panel.classList.toggle('active',panel.dataset.chartPanel===target));}}));</script></body></html>""", encoding="utf-8")


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
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        if path == "/api/health":
            self.send_json({"ok": True, "service": "ming-atelier-mvp"})
            return
        if path == "/api/history":
            self.send_error(404)
            return
        english_static = {
            "/ten-gods.html": "ten-gods-en.html",
            "/shensha.html": "shensha-en.html",
            "/shop.html": "shop-en.html",
        }
        if query.get("lang", [""])[0].lower() == "en" and path in english_static:
            target = STATIC / english_static[path]
        elif path == "/":
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
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        english_static = {
            "/ten-gods.html": "ten-gods-en.html",
            "/shensha.html": "shensha-en.html",
            "/shop.html": "shop-en.html",
        }
        if query.get("lang", [""])[0].lower() == "en" and path in english_static:
            target = STATIC / english_static[path]
        elif path == "/":
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
        if self.path not in {"/api/report", "/api/deep-report", "/api/divination", "/api/compatibility"}:
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
            if self.path == "/api/compatibility":
                model, html_path = build_compatibility(data)
                record_id = uuid.uuid4().hex[:10]
                html_url = f"/generated/{html_path.name}"
                append_record({
                    "id": record_id,
                    "type": "compatibility",
                    "createdAt": now_text(),
                    "title": f"{data.get('aName') or 'You'} × {data.get('bName') or 'Other'} Compatibility" if is_english(data) else f"{data.get('aName') or '你'} × {data.get('bName') or '对方'} 合盘",
                    "htmlUrl": html_url,
                    "llmStatus": model.get("llmStatus"),
                })
                self.send_json({
                    "ok": True,
                    "recordId": record_id,
                    "htmlUrl": html_url,
                    "llmStatus": model.get("llmStatus"),
                    "scores": model.get("scores"),
                    "text": model.get("text"),
                })
                return
            required = ["gender", "birthDate", "birthTime", "birthPlace"]
            missing = [key for key in required if not data.get(key)]
            if missing:
                self.send_json({"error": f"缺少字段：{', '.join(missing)}"}, 400)
                return
            run_id = f"{safe_name(data.get('name') or 'anonymous')}-{uuid.uuid4().hex[:8]}"
            computed, chart_png = build_chart(data, run_id)
            if self.path == "/api/deep-report":
                report_slug = safe_name(f"{data.get('name') or 'Anonymous'} Destiny Report" if is_english(data) else f"{data.get('name') or '匿名'}命理报告")
                pdf_path = GENERATED / f"{report_slug}-{uuid.uuid4().hex[:6]}.pdf"
                html_path = GENERATED / f"{report_slug}-interactive-{uuid.uuid4().hex[:6]}.html" if is_english(data) else GENERATED / f"{report_slug}-互动版-{uuid.uuid4().hex[:6]}.html"
                model = report_model(data, computed)
                deep_report_pdf(data, computed, chart_png, pdf_path, model)
                deep_report_html(data, computed, chart_png, html_path, model)
                pdf_url = f"/generated/{pdf_path.name}"
                html_url = f"/generated/{html_path.name}"
                chart_url = f"/generated/{chart_png.name}"
                append_record({
                    "id": run_id,
                    "type": "deep-bazi",
                    "createdAt": now_text(),
                    "title": f"{data.get('name') or 'Anonymous'} Destiny Report" if is_english(data) else f"{data.get('name') or '匿名'}命理报告",
                    "input": data,
                    "pdfUrl": pdf_url,
                    "htmlUrl": html_url,
                    "chartUrl": chart_url,
                    "llmStatus": model.get("llm_status"),
                    "reviewStatus": model.get("review_status"),
                    "translationStatus": model.get("translation_status"),
                    "translationIssues": model.get("translation_issues", []),
                    "reviewIssues": model.get("review_issues", []),
                })
                self.send_json({
                    "ok": True,
                    "recordId": run_id,
                    "pdfUrl": pdf_url,
                    "htmlUrl": html_url,
                    "chartUrl": chart_url,
                    "llmStatus": model.get("llm_status"),
                    "reviewStatus": model.get("review_status"),
                    "translationStatus": model.get("translation_status"),
                })
                return
            pdf_path = GENERATED / f"{run_id}.pdf"
            report_pdf(data, computed, chart_png, pdf_path)
            pdf_url = f"/generated/{pdf_path.name}"
            chart_url = f"/generated/{chart_png.name}"
            append_record({
                "id": run_id,
                "type": "bazi",
                "createdAt": now_text(),
                "title": f"{data.get('name') or 'Anonymous'} Destiny Report" if is_english(data) else f"{data.get('name') or '匿名'}命理报告",
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
