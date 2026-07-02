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
        label = "偏强"
        useful = f"宜用{child or '泄秀'}、{wealth or '财星'}来疏导能量，避免只凭惯性硬顶。"
    elif strength <= 44:
        label = "偏弱"
        useful = f"宜补{parent or '印星'}、{day_element or '比劫'}，先稳资源、专业和支持系统。"
    else:
        label = "中和"
        useful = "宜看具体流年和现实选择，不必一味补或泄，关键是顺势调整节奏。"
    reason = f"日主{ec.getDayGan()}{day_element}，同类与生扶约{support}%，消耗、财星与压力约{drain}%。"
    return label, strength, useful, reason


def deep_report_sections(data: dict, computed: dict) -> list[tuple[str, list[str]]]:
    ec = computed["ec"]
    profile = computed["profile"]
    chart = computed["chart"]
    label, strength, useful, reason = day_master_assessment(ec, profile)
    dominant = "、".join(f"{k}{v}%" for k, v in sorted(profile.items(), key=lambda item: item[1], reverse=True)[:3])
    focus = data.get("focus") or data.get("keyQuestion") or "综合命理阅读"
    industry = data.get("industry") or "未填写"
    role = data.get("role") or data.get("status") or "未填写"
    income = data.get("income") or "未填写"
    events = data.get("events") or "未填写"
    relation_question = data.get("relationshipQuestion") or "未填写"
    ten_god_lines = []
    pillar_names = ["年柱", "月柱", "日柱", "时柱"]
    for name, pillar in zip(pillar_names, chart["pillars"]):
        ten_god_lines.append(
            f"{name}：天干为{pillar['stem']}，十神{pillar['gan_shen']}；地支为{pillar['branch']}，藏干/十神为{'、'.join(pillar['zhi_shen']) or '未明'}。"
        )
    shensha_lines = []
    for name, pillar in zip(pillar_names, chart["pillars"]):
        stars = "、".join(pillar["shen_sha"]) if pillar["shen_sha"] else "无明显主星"
        shensha_lines.append(f"{name}：{stars}。本项只作辅助，不单独决定吉凶。")
    yun, selected, dayun_rows = current_dayun(ec, data.get("gender", "男"))
    dayun_text = "；".join(f"{row[0]}({row[1]})" for row in dayun_rows[:5]) or "暂未识别"
    relationship_note = "感情判断以日支、财官和现实状态共同看。MVP 版先给关系模式和风险边界；正缘外貌、行业和年份需要后续人工复核提高置信度。"
    if data.get("gender") == "男":
        relationship_note += " 男命重点看财星与日支承接力。"
    elif data.get("gender") == "女":
        relationship_note += " 女命重点看官杀与日支稳定性。"
    return [
        ("原始盘信息", [
            f"四柱：{ec.getYear()} 年｜{ec.getMonth()} 月｜{ec.getDay()} 日｜{ec.getTime()} 时。",
            f"日主：{ec.getDayGan()}，身强身弱模型判断为{label} {strength}%。",
            f"五行分布：{dominant}。",
            f"当前/2026 大运：{selected.getGanZhi() if selected else '未识别'}。",
        ]),
        ("核心判断", [
            reason,
            useful,
            f"你填写的重点是“{focus}”。这份 MVP 深度报告会把命盘结构、现实基线和关键问题合并判断，但不替代人工复核。",
        ]),
        ("十神八维拆解", ten_god_lines + [
            "十神不是性格标签，而是行动方式：比劫看自我与竞争，食伤看表达与产出，财星看资源与交易，官杀看规则与压力，印星看学习与支持。",
        ]),
        ("地支关系与神煞", computed["chart"]["relations"] + shensha_lines),
        ("事业与财富", [
            f"当前行业/角色：{industry} / {role}。",
            f"当前收入区间：{income}。",
            "事业上先看月柱和十神组合：月令代表现实赛道，食伤代表输出，财星代表商业化，官杀代表规则压力。MVP 版会给方向感，正式版再做十年收入节奏和月份拆解。",
            "财富上不做保证式预测。更适合把财运理解为资源转化能力：能否把专业、流量、产品、客户和现金流稳定连接起来。",
        ]),
        ("感情与关系", [
            f"你填写的感情问题：{relation_question}。",
            relationship_note,
            "若一段关系长期消耗金钱、时间、承诺或城市选择，这类关系对命盘节奏的损耗会比单纯情绪冲突更大。",
        ]),
        ("大运与未来节奏", [
            f"可识别的大运序列：{dayun_text}。",
            "MVP 版先展示大运背景，不做完整十年逐年展开。正式深度版会把大运、流年、2026 月份节奏和关键风险单独拆开。",
        ]),
        ("事件校准与置信度", [
            f"你提供的关键年份事件：{events}。",
            "若关键年份越具体，报告置信度越高；若出生时间只知道时辰或不确定，涉及时柱、子女、晚年、副业和细节时间窗的判断会降低置信度。",
            "当前自动深度体验版置信度约 65%-72%，适合体验报告结构和初步方向，不等同人工最终版。",
        ]),
        ("大白话总结", [
            free_report_summary(data, computed),
        ]),
    ]


def deep_report_pdf(data: dict, computed: dict, chart_png: Path, output: Path) -> None:
    font = register_font()
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("deepTitle", parent=base["Title"], fontName=font, fontSize=22, leading=30, alignment=1, wordWrap="CJK"),
        "sub": ParagraphStyle("deepSub", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=14, alignment=1, textColor=colors.HexColor("#666666"), wordWrap="CJK"),
        "h1": ParagraphStyle("deepH1", parent=base["Heading1"], fontName=font, fontSize=14.5, leading=21, spaceBefore=12, spaceAfter=8, wordWrap="CJK"),
        "body": ParagraphStyle("deepBody", parent=base["BodyText"], fontName=font, fontSize=9, leading=14, spaceAfter=5, wordWrap="CJK"),
        "note": ParagraphStyle("deepNote", parent=base["BodyText"], fontName=font, fontSize=8.2, leading=12, backColor=colors.HexColor("#fff6df"), borderColor=colors.HexColor("#ead69d"), borderWidth=0.4, borderPadding=6, textColor=colors.HexColor("#6d541d"), wordWrap="CJK"),
    }
    story = [
        paragraph(f"{data.get('name') or '匿名'} 命理深度体验报告", styles["title"]),
        paragraph(f"{data.get('calendar', '阳历')} {data.get('birthDate')} {data.get('birthTime')}｜{data.get('birthPlace', '')}｜{data.get('gender', '')}", styles["sub"]),
        Spacer(1, 8),
        paragraph("MVP 深度体验版：用于展示深度报告的结构、语气和基础分析能力。正式版会继续补充人工复核、互动模块、支付和订单追踪。", styles["note"]),
        Spacer(1, 8),
        Image(str(chart_png), width=135 * mm, height=205 * mm),
        PageBreak(),
    ]
    for title, lines in deep_report_sections(data, computed):
        story.append(paragraph(title, styles["h1"]))
        for line in lines:
            story.append(paragraph(line, styles["body"]))
    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    doc.build(story)


def deep_report_html(data: dict, computed: dict, chart_png: Path, output: Path) -> None:
    title = f"{html.escape(data.get('name') or '匿名')} 命理深度体验报告"
    sections = []
    for heading, lines in deep_report_sections(data, computed):
        body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
        sections.append(f"<section class='report-section'><h2>{html.escape(heading)}</h2>{body}</section>")
    chart_url = f"/generated/{chart_png.name}"
    output.write_text(f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><link rel="stylesheet" href="/pages.css">
<style>
body{{background:#080604;color:#f7ead2}}.report-cover{{min-height:72vh;display:grid;place-items:center;padding:88px 0 48px;background:radial-gradient(circle at 50% 20%,rgba(199,150,63,.22),transparent 38%),#080604}}.report-cover h1{{font-size:54px;max-width:760px}}.report-section{{max-width:980px;margin:0 auto;padding:34px 20px;border-top:1px solid rgba(199,150,63,.28)}}.report-section h2{{color:#f0c47a}}.report-section p{{color:#e8d7b4}}.chart-wrap{{max-width:520px;margin:24px auto}}.chart-wrap img{{width:100%;border:1px solid rgba(199,150,63,.35);border-radius:8px}}
</style></head>
<body><header class="top"><nav class="shell nav"><a class="brand" href="/"><img src="/assets/ming-four-pillars-mark.png"><span>Ming Atelier<small>命理工坊</small></span></a><div class="links"><a href="/">首页</a><a href="/questionnaire.html">问卷</a><a href="/divination.html">起卦</a></div></nav></header>
<main><section class="report-cover"><div class="shell"><p class="eyebrow">Essential Ming Report · MVP</p><h1>{title}</h1><p class="lead">以八字四柱为底图，读性格、节奏、选择与关系。关于你如何行动、如何取舍、如何顺势。</p></div></section><div class="chart-wrap"><img src="{chart_url}" alt="命盘图"></div>{''.join(sections)}</main>
<footer class="shell">Ming Atelier｜命理工坊。自动深度体验版用于产品测试，不替代人工复核。</footer></body></html>""", encoding="utf-8")


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
                pdf_path = GENERATED / f"{run_id}-deep.pdf"
                html_path = GENERATED / f"{run_id}-deep.html"
                deep_report_pdf(data, computed, chart_png, pdf_path)
                deep_report_html(data, computed, chart_png, html_path)
                pdf_url = f"/generated/{pdf_path.name}"
                html_url = f"/generated/{html_path.name}"
                chart_url = f"/generated/{chart_png.name}"
                append_record({
                    "id": run_id,
                    "type": "deep-bazi",
                    "createdAt": now_text(),
                    "title": f"{data.get('name') or '匿名'}命理深度体验报告",
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
