from __future__ import annotations

import json
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


def build_chart(data: dict, run_id: str) -> tuple[dict, Path]:
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


def build_divination(data: dict) -> dict:
    question = data.get("question", "").strip()
    if not question:
        raise ValueError("请填写要问的具体事情")
    if data.get("divinationDate") and data.get("divinationTime"):
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
    relation = "同气" if body_element == use_element else f"体卦{body_element}，用卦{use_element}"
    risk = 5 + (1 if moving_line in (3, 4) else 0) + (1 if body_element != use_element else -1)
    risk = max(2, min(9, risk))
    success = max(35, min(82, 72 - risk * 3 + (8 if body_element == use_element else 0)))
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
        "body": f"{TRIGRAMS[upper_index][0]}卦（{body_element}）",
        "use": f"{TRIGRAMS[lower_index][0]}卦（{use_element}）",
        "relation": relation,
        "success": f"{success}%",
        "risk": f"{risk}/10",
        "confidence": "62%",
        "summary": "这是自动年月日时起卦结果，适合做初步判断。若涉及投资、法律、健康或重大合同，必须结合现实资料复核。",
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
        if self.path not in {"/api/report", "/api/divination"}:
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
