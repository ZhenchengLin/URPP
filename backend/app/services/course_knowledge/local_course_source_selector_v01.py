"""14D-4B4C: bilingual bounded source selection (developer-only pilot).

Select only original authorized excerpts; never alter source text/IDs. Explicit
PDF page and equation numbers take priority over lexical matching. This is NOT
semantic retrieval or proof that model claims are supported by selected pages.
A selection with no known Chinese topic is fail-closed, not a first-page citation.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

# 14D-4B4C: bilingual bounded source selection
MAX_SELECTED_SOURCES_V01 = 2
MAX_SELECTED_SOURCE_CHARS_V01 = 12000
_STOP = frozenset({
    "the", "and", "for", "from", "with", "that", "this", "what", "why",
    "how", "can", "could", "would", "should", "about", "please", "tell",
    "give", "explain", "teach", "learn", "basic", "basics", "concept",
    "concepts", "paper", "uploaded", "material", "document", "source",
    "using", "into", "more", "start", "first", "next", "then", "only",
    "section", "chapter", "short", "sentence", "sentences", "does", "mean",
    "function", "functions", "formula", "formulas", "equation", "equations",
})
_WORDS = re.compile(r"[a-z][a-z0-9_-]{2,}", re.I)
_SECTION = re.compile(r"\b(?:section|chapter)\s+([IVX]{1,5}|[1-6])\b", re.I)
_HEADING = re.compile(r"(?m)^\s*([IVX]{1,5})\.\s+([A-Z][A-Z0-9 /\-]{3,})")
_PAGE = re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*页|\bpage\s+(\d{1,2})\b", re.I)
_EQUATION = re.compile(r"(?:公式|方程|式|equation|eq\.?)\s*[（(]?\s*(\d{1,2})\s*[)）]?", re.I)
_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI"}
_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
       "七": 7, "八": 8, "九": 9, "十": 10}
# The mapping describes retrieval hints, not translations of scientific claims.
_CN_TERMS = {
    "投影": ("projection", "projector"),
    "射线": ("ray", "beam"),
    "体积": ("volume",),
    "面积": ("area",),
    "交集": ("intersection", "intersect"),
    "相交": ("intersection", "intersect"),
    "高度": ("height",),
    "近似": ("approximation", "regression", "distance method"),
    "查找表": ("look-up table", "lookup table", "lut"),
    "积分": ("integration", "integral"),
    "几何": ("geometry",),
    "探测器": ("detector",),
    "体素": ("voxel",),
    "锥束": ("cone-beam",),
    "扇束": ("fan-beam",),
    "数学": ("equation", "formula", "volume", "area"),
    "公式": ("equation", "formula", "volume", "area"),
    "函数": ("function", "regression", "distance method"),
    "算法": ("algorithm",),
    "编程": ("cuda", "kernel"),
    "实现": ("implementation", "algorithm"),
}


def _pages(source: dict) -> tuple[int, int] | None:
    locator = source.get("source_locator", "")
    if type(locator) is not str or urlsplit(locator).scheme != "local-pdf":
        return None
    field = parse_qs(urlsplit(locator).query).get("pages", [""])[0]
    match = re.fullmatch(r"(\d+)-(\d+)", field)
    return (int(match[1]), int(match[2])) if match else None


def _choose(sources: tuple[dict, ...], indices: list[int]) -> tuple[str, ...]:
    result = []
    total = 0
    for index in indices:
        source = sources[index]
        if index in result or len(result) >= MAX_SELECTED_SOURCES_V01:
            continue
        length = len(source["content"])
        if total + length <= MAX_SELECTED_SOURCE_CHARS_V01:
            result.append(index)
            total += length
    return tuple(sources[i]["source_id"] for i in result)


def select_course_source_ids_v01(*, sources: tuple[dict, ...],
                                 current_question: str, history: tuple = ()) -> tuple[str, ...]:
    """Choose at most two complete authorized excerpts, or no source if unsupported.

    An explicit PDF page selects that page; an explicit equation selects its page.
    A section heading close to an excerpt boundary includes the following page
    if capacity permits. Short contextual formula follow-ups use earlier student
    turns. Unrecognized Chinese subject matter returns () without claiming that
    the first excerpt supports an answer. This is still lexical, not semantic.
    """
    if not sources or type(current_question) is not str or not current_question.strip():
        raise ValueError("A current question and authorized sources are required.")
    if any(type(s) is not dict or type(s.get("source_id")) is not str
           or type(s.get("content")) is not str for s in sources):
        raise ValueError("Invalid authorized source selection input.")

    question = current_question.strip()
    history_question = ""
    for item in reversed(history):
        if getattr(item, "role", None) == "student":
            history_question = item.text
            break

    requested_page = _PAGE.search(question)
    if requested_page:
        numeral = requested_page[1] or requested_page[2]
        page = int(numeral) if numeral.isdecimal() else _CN.get(numeral)
        if page is None:
            return ()
        return _choose(sources, [i for i, source in enumerate(sources)
                                 if (span := _pages(source)) and span[0] <= page <= span[1]])

    requested_equation = _EQUATION.search(question)
    if requested_equation:
        number = requested_equation[1]
        pattern = re.compile(r"(?<!\d)\(\s*" + re.escape(number) + r"\s*\)(?!\d)")
        matches = [i for i, source in enumerate(sources) if pattern.search(source["content"])]
        return _choose(sources, matches[:1])

    section = _SECTION.search(question)
    if section:
        heading = _ROMAN.get(section[1].upper(), section[1].upper())
        for i, source in enumerate(sources):
            match = next((m for m in _HEADING.finditer(source["content"])
                          if m[1] == heading), None)
            if match:
                # A section that begins near an excerpt's end needs the next
                # authorized contiguous excerpt for the discussion and formula.
                indices = [i]
                if match.start() >= int(len(source["content"]) * .65) and i + 1 < len(sources):
                    indices.append(i + 1)
                return _choose(sources, indices)
        return ()

    if re.search(r"\b(?:cuda|gpu)\b", question, re.I) or "CUDA" in question.upper():
        for i, source in enumerate(sources):
            if any("CUDA" in m[2] for m in _HEADING.finditer(source["content"])):
                return _choose(sources, [i])

    # A generic request to list the paper's major formulas cannot fit every
    # excerpt. Select bounded 3-D geometry + height-LUT pages, not an arbitrary
    # first excerpt. The model must not imply this exhausts the whole paper.
    followup = bool(re.search(r"\bfunctions?\b|函数", question, re.I)) and bool(
        re.search(r"数学|公式|equation|formula", history_question, re.I))
    broad_formulas = bool(re.search(r"数学公式|重要.*公式|key.*equations?|main.*formulas?", question, re.I))
    if followup or broad_formulas:
        geometry = next((i for i, source in enumerate(sources)
                         if "A. Exact Ray-Voxel Volume" in source["content"]), None)
        height = next((i for i, source in enumerate(sources)
                       if "B. Height Look-Up Table" in source["content"]), None)
        if geometry is not None:
            # A height heading at the very end of the geometry excerpt is
            # followed by its actual derivation in the next original excerpt.
            if height is None or height <= geometry:
                height = geometry + 1 if geometry + 1 < len(sources) else None
            return _choose(sources, [geometry] + ([height] if height is not None else []))

    # Short non-English follow-ups inherit the last student's topical terms,
    # while explicit page/equation requests above NEVER inherit stale history.
    effective = question
    if (len(question) <= 28 and history_question
            and re.search(r"^(?:把|继续|再|这个|那个|刚才|为什么|how about|what about)", question, re.I)):
        effective += " " + history_question
    keywords = {w.lower() for w in _WORDS.findall(effective) if w.lower() not in _STOP}
    hints = {hint for chinese, words in _CN_TERMS.items() if chinese in effective for hint in words}
    keywords |= hints

    def score(source: dict) -> int:
        lower = source["content"].lower()
        total = 0
        for term in keywords:
            count = len(re.findall(r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])", lower))
            total += min(3, count)
            if term in lower[:1200]:
                total += 2
        return total

    ranked = sorted(range(len(sources)), key=lambda i: (-score(sources[i]), i))
    if ranked and score(sources[ranked[0]]) > 0:
        return _choose(sources, ranked[:1])

    if re.search(r"[\u3400-\u9fff]", question):
        # An unknown Chinese topic must not receive an unrelated first-page ID.
        # Generic requests for an introduction are explicitly allowed.
        if re.search(r"概述|简介|介绍|开始学习|从头|第一课", question):
            return _choose(sources, [0])
        return ()

    # Retain the existing English generic-first-concept pilot behavior; a
    # non-matching fallback does not establish semantic support for an answer.
    return _choose(sources, [0])
