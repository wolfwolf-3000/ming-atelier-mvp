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


STEM_ELEMENT = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
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
    GENERATED.mkdir(parents=True, exist_ok=True)
    with RECORDS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


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
        f"事业上，用户当前填写的行业/角色是“{industry} / {role}”，免费版只能做初筛：比较适合往{industries}"
        f"如果要做得更顺，关键不是追热点，而是把自己的专业、流程、交付标准和现金流规则固定下来。"
        f"感情上，{gender or '此盘'}看{spouse_logic}与日支状态，免费版不做细断正缘外貌和年份，只能说关系里最需要的是边界、节奏和现实责任感；"
        f"如果一段关系长期让你在钱、时间、承诺或城市选择上反复消耗，就不适合硬拖。完整感情窗口、正缘特征和未来几年波动，需要付费深度报告结合大运流年再看。"
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
    risk_points = [
        "不要把卦象当作确定承诺，仍要以现实证据、合同、沟通记录和专业意见为准。",
        "若对方回复含糊、条件不断变化，说明用卦压力在兑现，应降低投入。",
        "若这件事涉及医疗、法律、投资或重大资金，不建议只凭自动起卦决策。",
    ]
    advice = [
        "先把问题缩小到一个可验证动作：一次沟通、一个节点、一个明确条件。",
        "能进则小步推进，不能进则先等信息，不要在不清楚的时候加码。",
        "保留退出条件：时间、成本、对方承诺三项至少要有一项可量化。",
    ]
    return {
        "question": question,
        "time": divination_time.strftime("%Y-%m-%d %H:%M"),
        "location": data.get("location", "").strip() or "未填，按当前本地时间起卦",
        "background": data.get("background", "").strip() or "未填",
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
        "advice": advice,
        "riskPoints": risk_points,
        "summary": f"此卦判断为「{verdict}」，倾向是「{verdict_tone}」。核心原因是{relation}，再看动爻处于{phase}，所以短期不宜只凭情绪决定，应按节点、小步验证、留后手来处理。",
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


def day_master_assessment(ec, profile: dict) -> tuple[str, int, str, str]:
    day_element = STEM_ELEMENT.get(ec.getDayGan(), "")
    parent = {"木": "水", "火": "木", "土": "火", "金": "土", "水": "金"}.get(day_element, "")
    child = GENERATES.get(day_element, "")
    wealth = CONTROLS.get(day_element, "")
    officer = next((k for k, v in CONTROLS.items() if v == day_element), "")
    support = profile.get(day_element, 0) + profile.get(parent, 0)
    drain = profile.get(child, 0) + profile.get(wealth, 0) + profile.get(officer, 0)
    strength = max(28, min(82, 50 + support - drain // 2))
    if strength >= 62:
        label = "身强"
        useful = f"宜用{child or '泄秀'}、{wealth or '财星'}来疏导能量，把行动力转成产品、现金流和规则。"
    elif strength <= 44:
        label = "身弱"
        useful = f"宜补{parent or '印星'}、{day_element or '比劫'}，先稳资源、专业和支持系统，再谈扩张。"
    else:
        label = "中和"
        useful = "不宜一味补或泄，关键是随流年调节：旺时收束，弱时补资源，机会来时先算风险。"
    reason = f"日主{ec.getDayGan()}{day_element}，同类与生扶约{support}%，输出、财星与压力约{drain}%。"
    return label, strength, useful, reason


def useful_elements(ec, profile: dict) -> list[str]:
    label, _, _, _ = day_master_assessment(ec, profile)
    day_element = STEM_ELEMENT.get(ec.getDayGan(), "")
    parent = {"木": "水", "火": "木", "土": "火", "金": "土", "水": "金"}.get(day_element, "")
    child = GENERATES.get(day_element, "")
    wealth = CONTROLS.get(day_element, "")
    if label == "身强":
        return [e for e in [child, wealth] if e][:2]
    if label == "身弱":
        return [e for e in [parent, day_element] if e][:2]
    ordered = sorted(profile.items(), key=lambda item: item[1])
    return [item[0] for item in ordered[:2]]


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


def income_probabilities(strength: int, useful: list[str], data: dict) -> list[list[str]]:
    has_income = 1 if data.get("income") else 0
    useful_bonus = 1 if "金" in useful or "水" in useful else 0
    million = max(45, min(72, 55 + has_income * 5 + useful_bonus * 4 - max(0, strength - 70) // 4))
    five_million = max(18, min(40, 30 + max(0, strength - 58) // 3 + useful_bonus * 2 - has_income))
    ten_million = max(6, min(22, 100 - million - five_million))
    overflow = million + five_million + ten_million - 100
    if overflow > 0:
        reduce_five = min(overflow, five_million - 18)
        five_million -= reduce_five
        overflow -= reduce_five
        million -= overflow
    elif overflow < 0:
        million += abs(overflow)
    return [
        ["百万级", f"{million}%", "RMB 100万-500万/年", "需要把专业、客户、现金流和交付标准稳定连接，置信度约68%。"],
        ["500万级", f"{five_million}%", "RMB 500万-1000万/年", "需要项目可复制、团队/渠道/产品成型，并有明确风控，置信度约58%。"],
        ["千万级", f"{ten_million}%", "RMB 1000万以上/年", "需要规模化、资本/团队/供应链协同，且不能靠高杠杆硬冲，置信度约45%。"],
    ]


def annual_rows(selected_ganzhi: str) -> list[list[str]]:
    years = [
        ("2026", "丙午"), ("2027", "丁未"), ("2028", "戊申"), ("2029", "己酉"), ("2030", "庚戌"),
        ("2031", "辛亥"), ("2032", "壬子"), ("2033", "癸丑"), ("2034", "甲寅"), ("2035", "乙卯"), ("2036", "丙辰"),
    ]
    rows = []
    for idx, (year, pillar) in enumerate(years):
        fire = "午" in pillar or "丙" in pillar or "丁" in pillar
        metal_water = any(x in pillar for x in "申酉亥子壬癸庚辛")
        career = 5 + (2 if metal_water else 0) - (1 if fire else 0)
        wealth = 5 + (2 if metal_water else 0) - (2 if fire else 0)
        relation = 5 + (1 if idx in (3, 5, 6) else 0)
        stress = 5 + (2 if fire else 0)
        loss = 4 + (2 if fire else 0) + (1 if idx in (3, 9) else 0)
        family = 4 + (1 if idx in (5, 6, 9) else 0)
        compliance = 5 + (2 if year in {"2026", "2029", "2035"} else 0)
        rows.append([year, pillar, selected_ganzhi or "未识别", str(career), str(wealth), str(relation), str(stress), str(loss), str(family), str(compliance), "按流年五行与盘面合冲作模型估计。"])
    return rows


def monthly_rows() -> list[list[str]]:
    data = [
        ("2026-02", "庚寅", "立春-惊蛰", 6, 6, 5, 6, "寅木启动计划，适合小样本验证。"),
        ("2026-03", "辛卯", "惊蛰-清明", 6, 6, 7, 7, "卯木带来关系和合作波动，签约要慢。"),
        ("2026-04", "壬辰", "清明-立夏", 7, 7, 5, 5, "辰土收束，适合谈规则、账期和合同。"),
        ("2026-05", "癸巳", "立夏-芒种", 6, 5, 6, 7, "巳火加热，推进快但压力上升。"),
        ("2026-06", "甲午", "芒种-小暑", 4, 3, 8, 9, "全年高风险月，禁高杠杆、重库存、冲动承诺和情绪摊牌。"),
        ("2026-07", "乙未", "小暑-立秋", 5, 4, 6, 7, "适合复盘止损、清库存和整理现金流。"),
        ("2026-08", "丙申", "立秋-白露", 7, 7, 5, 5, "申金出现，商务和客户机会回升。"),
        ("2026-09", "丁酉", "白露-寒露", 7, 7, 8, 7, "钱与关系同时被激活，分成、股权、承诺要写清楚。"),
        ("2026-10", "戊戌", "寒露-立冬", 6, 5, 6, 7, "适合销售表达，忌挑战规则和公开冲突。"),
        ("2026-11", "己亥", "立冬-大雪", 6, 6, 6, 6, "变动月，适合调整供应商、策略和合作结构。"),
        ("2026-12", "庚子", "大雪-小寒", 8, 8, 5, 4, "金水到位，适合收账、定合同、谈长期资源。"),
        ("2027-01", "辛丑", "小寒-立春", 8, 8, 5, 4, "财务收束窗口，适合预算、复盘和资源整合。"),
    ]
    return [[m, gz, period, str(c), str(w), str(r), str(risk), note] for m, gz, period, c, w, r, risk, note in data]


def relationship_profile(data: dict, useful: list[str]) -> list[list[str]]:
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
    return {
        "ec": ec,
        "chart": chart,
        "profile": profile,
        "day_strength_label": label,
        "day_strength": strength,
        "useful_text": useful_text,
        "strength_reason": strength_reason,
        "useful_elements": useful,
        "dominant": dominant,
        "selected_dayun": selected.getGanZhi() if selected else "未识别",
        "dayun_rows": dayun_rows,
        "ten_god_rows": ten_god_rows(computed),
        "shensha_rows": shensha_rows(computed),
        "branch_relation_rows": branch_relation_rows(computed),
        "income_rows": income_probabilities(strength, useful, data),
        "annual_rows": annual_rows(selected.getGanZhi() if selected else ""),
        "monthly_rows": monthly_rows(),
        "relationship_rows": relationship_profile(data, useful),
        "calibration_title": calibration_title,
        "calibration_lines": [
            f"出生时间来源：{data.get('timeSource') or '未填写'}；准确度：{data.get('timeAccuracy') or '未填写'}；真太阳时：{data.get('trueSolarTime') or '未填写'}。",
            f"出生地/当前城市：{data.get('birthPlace') or '未填写'} / {data.get('currentCity') or '未填写'}。",
            f"关键年份事件：{events or '未提供具体事件，因此不做事件校准，改用排盘边界与置信度校准。'}",
            "当前自动标准版以盘面、大运、流年为主，现实事件只作校准，不覆盖命局结构。",
        ],
    }


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
    font_big = load_font(92, True)
    font_mid = load_font(30)
    img = PILImage.new("RGB", (1200, 680), "#080604")
    draw = ImageDraw.Draw(img)
    draw.rectangle((18, 18, 1182, 662), outline="#c7963f", width=3)
    draw.text((58, 42), "Ming Atelier · 喜用神", font=font_mid, fill="#f0c47a")
    for i, element in enumerate(elements[:2] or ["金", "水"]):
        cx = 330 + i * 520
        color = colors_map.get(element, "#d8b35f")
        draw.ellipse((cx - 150, 170, cx + 150, 470), outline=color, width=5)
        draw.line((cx, 120, cx, 520), fill=color, width=2)
        draw.arc((cx - 220, 110, cx + 220, 550), 25, 335, fill=color, width=2)
        draw.text((cx - 45, 255), element, font=font_big, fill=color)
        draw.text((cx - 170, 500), element_behavior(element)[:22], font=font_mid, fill="#e8d7b4")
    img.save(useful_path)
    crystal = PILImage.new("RGB", (1200, 680), "#0b0906")
    draw = ImageDraw.Draw(crystal)
    draw.rectangle((18, 18, 1182, 662), outline="#c7963f", width=3)
    draw.text((58, 42), "Ming Atelier · 适配水晶", font=font_mid, fill="#f0c47a")
    for i, row in enumerate(crystal_rows(elements[:2] or ["金", "水"])):
        element, name, fit, _ = row
        x = 90 + i * 540
        color = colors_map.get(element, "#d8b35f")
        draw.polygon([(x + 140, 170), (x + 250, 235), (x + 220, 390), (x + 60, 390), (x + 30, 235)], outline=color, fill="#151209")
        draw.text((x, 430), f"{element}｜{name}", font=font_mid, fill=color)
        draw.text((x, 480), fit[:24], font=font_mid, fill="#e8d7b4")
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


def report_plain_summary(data: dict, model: dict) -> str:
    useful = "、".join(model["useful_elements"]) or "节奏与边界"
    return (
        f"{data.get('name') or '这张盘'}的核心不是靠单点爆发取胜，而是要把{useful}这类能量用成稳定系统。"
        f"性格上，日主强弱判断为{model['day_strength_label']}，行动时容易先凭直觉和压力反应，但真正能走远的方式是把判断写成规则，把机会拆成可验证的小步骤。"
        "适合从事的方向以可沉淀专业、可复用方法、可管理现金流的行业为主，例如咨询、内容产品、品牌运营、金融/数据/法务/技术、供应链、教育训练或带有研究属性的服务业。"
        "感情上，不适合高消耗、高情绪、承诺模糊的关系；越是能共同定规则、谈现实、稳节奏的人，越能让关系变成加分项。"
    )


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
        paragraph("三、十神分析", styles["h1"]),
        pdf_table([["十神", "位置", "通用解释", "本盘含义"]] + model["ten_god_rows"], [22 * mm, 34 * mm, 52 * mm, 62 * mm], font, 6.8),
        paragraph("四、分析：神煞体系", styles["h1"]),
    ])
    for group, rows in model["shensha_rows"].items():
        story.append(paragraph(group, styles["body"]))
        story.append(pdf_table([["排名", "神煞", "强度", "通用解释", "在该柱代表什么"]] + rows, [14 * mm, 24 * mm, 18 * mm, 58 * mm, 56 * mm], font, 6.6))
        story.append(Spacer(1, 5))
    story.extend([
        paragraph("地支关系制衡", styles["body"]),
        pdf_table([["关系", "结构提示", "可能影响", "现实制化"]] + model["branch_relation_rows"], [34 * mm, 43 * mm, 48 * mm, 45 * mm], font, 6.8),
        paragraph("五、专项剖析：事业发展、财运与感情", styles["h1"]),
        paragraph("事业上，本盘更适合走专业沉淀、方法论输出、规则化交付和长期客户信任路线。若选择高波动赛道，必须先设计现金流、合约和退出条件。", styles["body"]),
        paragraph("财运不宜只看机会大小，更要看承接系统。下面收入层级为模型概率，不代表保证结果。", styles["body"]),
        pdf_table([["层级", "概率", "金额", "条件"]] + model["income_rows"], [24 * mm, 18 * mm, 38 * mm, 90 * mm], font, 6.8),
        pdf_table([["主题", "判断", "说明"]] + model["relationship_rows"], [35 * mm, 48 * mm, 87 * mm], font, 6.8),
        paragraph("六、未来十年财运与风险", styles["h1"]),
        pdf_table([["年份", "流年", "大运", "事业", "财运", "感情", "健康/压力", "破财", "家宅", "合规", "触发"]] + model["annual_rows"], [14 * mm, 16 * mm, 18 * mm, 13 * mm, 13 * mm, 13 * mm, 17 * mm, 13 * mm, 13 * mm, 13 * mm, 27 * mm], font, 5.6),
        paragraph("七、2026 年单独流月拆解", styles["h1"]),
        pdf_table([["月份", "月柱", "节气", "事业", "财运", "关系", "风险", "行动建议"]] + model["monthly_rows"], [18 * mm, 16 * mm, 28 * mm, 13 * mm, 13 * mm, 13 * mm, 13 * mm, 56 * mm], font, 6.0),
        paragraph(f"八、{model['calibration_title']}", styles["h1"]),
    ])
    for line in model["calibration_lines"]:
        story.append(paragraph(line, styles["body"]))
    story.extend([
        paragraph("九、结论：核心限制与潜在危机", styles["h1"]),
        paragraph("核心限制不是没有机会，而是机会、情绪、承诺和现金流同时出现时，容易先行动后核算。高风险年份或月份应减少重资产、重库存、高杠杆、模糊合伙和口头承诺。", styles["body"]),
        paragraph("最需要守住的是三件事：第一，所有合作写清楚边界；第二，重大支出延迟 24 小时再决定；第三，情绪关系和金钱关系分开处理。", styles["body"]),
        paragraph("十、大白话总结", styles["h1"]),
        paragraph(report_plain_summary(data, model), styles["body"]),
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
        ("ten-god", "十神分析"),
        ("shensha", "神煞体系"),
        ("career", "事业财运感情"),
        ("annual", "未来十年"),
        ("monthly", "2026流月"),
        ("calibration", model["calibration_title"]),
        ("crisis", "核心危机"),
        ("summary", "大白话总结"),
        ("elements", "喜用神"),
        ("crystals", "适配水晶"),
    ]
    nav = "".join(f"<a href='#{sid}'>{html.escape(label)}</a>" for sid, label in sections)
    relation_text = "；".join(computed["chart"].get("relations") or [])
    output.write_text(f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><link rel="stylesheet" href="/pages.css">
<style>
body{{background:#080604;color:#f7ead2}}.scroll-progress{{position:fixed;top:0;left:0;height:3px;background:#d8b35f;z-index:80;width:0}}.report-nav{{position:sticky;top:70px;z-index:20;background:rgba(8,6,4,.88);backdrop-filter:blur(12px);border-block:1px solid rgba(216,179,95,.2);overflow:auto;white-space:nowrap}}.report-nav .shell{{display:flex;gap:18px;padding:12px 20px}}.report-nav a{{color:#e8d7b4;text-decoration:none;font-size:13px}}.hero{{min-height:78vh;display:grid;align-items:center;padding:98px 0 56px;background:radial-gradient(circle at 50% 18%,rgba(216,179,95,.24),transparent 34%),linear-gradient(180deg,#0d0905,#080604)}}.hero h1{{font-size:56px;line-height:1.08;max-width:760px;color:#f7ead2}}.lead{{max-width:760px;color:#e8d7b4}}.panel{{max-width:1120px;margin:0 auto;padding:42px 20px;border-top:1px solid rgba(216,179,95,.2)}}.panel h2{{color:#f0c47a;font-size:28px}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}.grid.two{{grid-template-columns:repeat(2,minmax(0,1fr))}}.card,.kpi{{border:1px solid rgba(216,179,95,.28);background:rgba(20,15,8,.72);border-radius:8px;padding:18px}}.kpi b{{display:block;color:#f0c47a;font-size:28px}}.table-wrap{{overflow:auto;border:1px solid rgba(216,179,95,.22);border-radius:8px}}table{{border-collapse:collapse;width:100%;min-width:760px}}th,td{{border-bottom:1px solid rgba(216,179,95,.16);padding:11px 12px;text-align:left;vertical-align:top}}th{{color:#f0c47a;background:rgba(216,179,95,.08)}}td{{color:#ead9b7}}.chart{{max-width:520px;margin:22px auto}}.chart img,.god-art img{{width:100%;border:1px solid rgba(216,179,95,.35);border-radius:8px}}.bar{{height:9px;border-radius:99px;background:linear-gradient(90deg,#d8b35f,#8f6a2a);margin-top:10px}}.income-band b,.warning b{{color:#f0c47a}}details.star-detail{{border-top:1px solid rgba(216,179,95,.18);padding:10px 0}}details.star-detail summary{{cursor:pointer;color:#f0c47a}}details.star-detail summary span{{float:right;color:#d8b35f}}.timeline{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}.month{{border:1px solid rgba(216,179,95,.22);border-radius:8px;padding:14px;background:rgba(20,15,8,.65)}}.fade{{opacity:0;transform:translateY(18px);transition:opacity .7s ease,transform .7s ease}}.fade.show{{opacity:1;transform:none}}footer{{padding:34px 20px;color:#9f8d6b}}@media(max-width:760px){{.hero h1{{font-size:38px}}.grid,.grid.two,.timeline{{grid-template-columns:1fr}}.report-nav{{top:64px}}}}
</style></head>
<body><header class="top"><nav class="shell nav"><a class="brand" href="/"><img src="/assets/ming-four-pillars-mark.png"><span>Ming Atelier<small>命理工坊</small></span></a><div class="links"><a href="/">首页</a><a href="/questionnaire.html">问卷</a><a href="/divination.html">起卦</a></div></nav></header>
<div class="scroll-progress" id="scrollProgress"></div><main><section class="hero"><div class="shell fade"><p class="eyebrow">Ming Atelier · Eastern Destiny Readings</p><h1>{title}</h1><p class="lead">以八字四柱为底图，读性格、节奏、选择与关系。关于你如何行动、如何取舍、如何顺势。</p></div></section><nav class="report-nav"><div class="shell">{nav}</div></nav>
<section class="panel fade" id="raw"><h2>原始盘信息</h2><div class="grid"><div class="kpi"><span>日主强弱</span><b>{html.escape(model["day_strength_label"])}</b><div class="bar" style="width:{model["day_strength"]}%"></div></div><div class="kpi"><span>强度估计</span><b>{model["day_strength"]}%</b></div><div class="kpi"><span>当前/2026大运</span><b>{html.escape(model["selected_dayun"])}</b></div></div><div class="chart"><img src="{chart_url}" alt="命盘图"></div>{html_table(["项目","内容"], [["四柱", f"{ec.getYear()} 年｜{ec.getMonth()} 月｜{ec.getDay()} 日｜{ec.getTime()} 时"], ["五行估计", model["dominant"]], ["地支关系", relation_text]])}</section>
<section class="panel fade" id="pattern"><h2>格局与用神体系</h2><div class="card"><p>{html.escape(model["strength_reason"])}</p><p>{html.escape(model["useful_text"])}</p></div>{html_table(["喜用","行为落地"], [[e, element_behavior(e)] for e in model["useful_elements"]])}</section>
<section class="panel fade" id="ten-god"><h2>十神分析</h2>{html_table(["十神","位置","通用解释","本盘含义"], model["ten_god_rows"])}</section>
<section class="panel fade" id="shensha"><h2>神煞体系</h2>{html_detail_cards(model["shensha_rows"])}{html_table(["关系","结构提示","可能影响","现实制化"], model["branch_relation_rows"])}</section>
<section class="panel fade" id="career"><h2>事业发展、财运与感情</h2><div class="grid two"><article class="card income-band"><b>事业路径</b><p>适合走专业沉淀、方法论输出、规则化交付和长期客户信任路线。高波动赛道必须先设计现金流、合约和退出条件。</p></article><article class="card warning"><b>财运原则</b><p>财运不只看机会大小，更要看承接系统。收入层级是模型概率，不是保证结果。</p></article></div>{html_table(["层级","概率","金额","条件"], model["income_rows"])}{html_table(["主题","判断","说明"], model["relationship_rows"])}</section>
<section class="panel fade" id="annual"><h2>未来十年财运与风险</h2>{html_table(["年份","流年","大运","事业","财运","感情","健康/压力","破财","家宅","合规","触发"], model["annual_rows"])}</section>
<section class="panel fade" id="monthly"><h2>2026 年单独流月拆解</h2><div class="timeline">{"".join(f"<article class='month'><b>{html.escape(row[0])}｜{html.escape(row[1])}</b><p>{html.escape(row[7])}</p><small>事业 {row[3]} / 财运 {row[4]} / 关系 {row[5]} / 风险 {row[6]}</small></article>" for row in model["monthly_rows"])}</div></section>
<section class="panel fade" id="calibration"><h2>{html.escape(model["calibration_title"])}</h2><div class="card">{"".join(f"<p>{html.escape(line)}</p>" for line in model["calibration_lines"])}</div></section>
<section class="panel fade" id="crisis"><h2>核心限制与潜在危机</h2><div class="grid two"><article class="card warning"><b>限制</b><p>机会、情绪、承诺和现金流同时出现时，容易先行动后核算。</p></article><article class="card warning"><b>守法则</b><p>合作写清边界，重大支出延迟 24 小时，情绪关系和金钱关系分开处理。</p></article></div></section>
<section class="panel fade" id="summary"><h2>大白话总结</h2><div class="card"><p>{html.escape(report_plain_summary(data, model))}</p></div></section>
<section class="panel fade elements" id="elements"><h2>喜用神与五行补足</h2><div class="god-art"><img src="{useful_url}" alt="喜用神图"></div></section>
<section class="panel fade" id="crystals"><h2>适配水晶建议</h2><div class="god-art"><img src="{crystal_url}" alt="适配水晶图"></div>{html_table(["五行","建议","适配点","使用方式"], crystal_rows(model["useful_elements"]))}</section></main>
<footer class="shell">Ming Atelier｜命理工坊。自动标准版用于客测交付，关键人生决策建议叠加人工复核。</footer><script>const p=document.getElementById('scrollProgress');addEventListener('scroll',()=>{{const h=document.documentElement; p.style.width=((h.scrollTop)/(h.scrollHeight-h.clientHeight)*100)+'%';}});const io=new IntersectionObserver(es=>es.forEach(e=>e.isIntersecting&&e.target.classList.add('show')),{{threshold:.14}});document.querySelectorAll('.fade').forEach(el=>io.observe(el));</script></body></html>""", encoding="utf-8")


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
            self.send_json({"ok": True, "records": read_records()})
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
