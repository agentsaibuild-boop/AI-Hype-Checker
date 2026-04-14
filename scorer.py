"""
Hybrid hype scorer.

Hype score   — morphological patterns for marketing language.
               Each CATEGORY fires at most once (no word-count accumulation).

Signal score — Toulmin structural elements as additive bonuses only.
               Absence of evidence is NOT a penalty.

The two scores are independent.
"""

import re
import html as html_lib
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

@dataclass
class Category:
    label:    str
    patterns: list[str]
    weight:   float   # 1–3, category fires once at this weight
    color:    str


# ── Hype categories ──────────────────────────────────────────────────────────

HYPE_CATEGORIES: list[Category] = [
    Category(
        label="Революционни претенции",
        weight=3.0,
        color="#ef4444",
        patterns=[
            r"redefin\w+",
            r"fundamental\s+(?:shift|change|transform\w*)",
            r"paradigm\s+shift",
            r"revolutioniz\w+",
            r"game[\s-]chang\w+",
            r"unprecedented",
            r"new\s+(?:era|phase|paradigm)\s+(?:of|in|for)\s+\w+",
            r"never[\s-]before[\s-](?:seen|possible|achieved)",
            r"changes?\s+everything",
        ],
    ),
    Category(
        label="PR структура",
        weight=2.5,
        color="#f97316",
        patterns=[
            r"(?:the\s+company|they)\s+said\s+(?:it\s+)?(?:designed|built|created|aims|is\s+releasing)",
            r"in\s+response\s+to\s+this\s+challenge",
            r"(?:is\s+)?proud\s+to\s+(?:announce|introduce|present)",
            r"(?:announced?|introduced?|unveiled?|launched?)\s+today",
            r"said\s+it\s+(?:designed|aims|is\s+releasing|plans\s+to)",
            r"(?:mark|represent)s?\s+a\s+(?:major|significant|key)\s+(?:milestone|step|moment)",
        ],
    ),
    Category(
        label="Неизмерени твърдения",
        weight=2.0,
        color="#f59e0b",
        patterns=[
            r"significantly\s+\w+(?:ing|ed)?",
            r"dramatically\s+\w+",
            r"greatly\s+\w+",
            r"massively\s+\w+",
            r"improved\s+(?:efficiency|performance|accuracy|productivity)(?!\s+(?:by|of)\s+\d)",
            r"lower(?:ing|ed)?\s+(?:the\s+)?barrier",
            r"faster\s+development(?!\s+(?:by|of)\s+\d)",
        ],
    ),
    Category(
        label="Демократизационен език",
        weight=2.0,
        color="#a855f7",
        patterns=[
            r"zero[\s-]code",
            r"no[\s-]code",
            r"(?:even\s+)?non[\s-]technical\s+(?:users?|people|teams?)",
            r"as\s+simple\s+as\s+(?:\w+ing|building|clicking|dragging|assembling)",
            r"without\s+(?:any\s+)?(?:coding|programming|engineering)\s+(?:expertise|knowledge|experience|skills?)",
            r"anyone\s+can",
            r"democratiz\w+\s+\w+",
        ],
    ),
    Category(
        label="Маркетингови суперлативи",
        weight=1.5,
        color="#ec4899",
        patterns=[
            r"cutting[\s-]edge",
            r"next[\s-]gen(?:eration)?",
            r"world[\s-]class",
            r"best[\s-]in[\s-]class",
            r"industry[\s-]leading",
            r"most\s+(?:advanced|powerful|innovative|sophisticated)\s+(?:ever|yet|available|to\s+date)",
        ],
    ),
    Category(
        label="Претенциозност",
        weight=2.0,
        color="#dc2626",
        patterns=[
            r"\bproves?\s+(?:that\s+)?(?:this|it|our|the)\b",
            r"\bdefinitively\b",
            r"\bundeniably\b",
            r"\bcertainly\s+(?:will|is|can|does)\b",
            r"\bwill\s+(?:always|never|definitely)\s+\w+",
            r"unlike\s+(?:all\s+)?(?:other|previous|prior|existing)\s+(?:method|model|approach|system)s?\b",
            r"(?:beyond|surpass\w+)\s+human[\s-]level\b",
        ],
    ),
]

# ── Signal categories (Toulmin) ──────────────────────────────────────────────

SIGNAL_CATEGORIES: list[Category] = [
    Category(
        label="Доказателство",
        weight=3.0,
        color="#10b981",
        patterns=[
            r"\d+\.\d+\s*%",
            r"\d+\s*%\s+(?:accuracy|improvement|reduction|increase|gain|speedup)",
            r"\d+[×x]\s*(?:faster|better|more\s+efficient|speedup)",
            r"\d+[KMBk]\s*(?:param(?:eter)?s?|tokens?|samples?|examples?)",
            r"(?:on|using|with)\s+\d[\d,]+\s+(?:sample|example|instance|image|task|trial)\w*",
            r"(?:score|accuracy|f1|precision|recall|bleu|rouge)\s+(?:of\s+)?\d+",
            r"\d+\s*(?:layer|head|block)s?\b",
        ],
    ),
    Category(
        label="Обяснение (Warrant)",
        weight=2.0,
        color="#06b6d4",
        patterns=[
            r"\bbecause\s+(?:of\s+)?\w+",
            r"\bdue\s+to\s+(?:the\s+)?\w+",
            r"(?:which|this)\s+(?:explains?|indicates?|suggests?|shows?)\s+that\b",
            r"the\s+(?:reason|key\s+insight|intuition)\s+(?:is|being)\s+that\b",
            r"backprop(?:agat\w+)?\s+through",
            r"(?:gradient|loss)\s+(?:flow|signal|function)\s+\w+",
            r"this\s+(?:is\s+)?(?:because|explained\s+by|due\s+to)\b",
        ],
    ),
    Category(
        label="Prior work / Верифицируемост",
        weight=2.5,
        color="#8b5cf6",
        patterns=[
            r"\bet\s+al\.",
            r"\barxiv\b",
            r"(?:as\s+(?:shown|demonstrated|established)\s+(?:by|in))\s+\w+",
            r"(?:following|building\s+on|extending)\s+\w+\s+et\s+al",
            r"(?:prior|previous)\s+(?:work|research|stud\w+)\s+(?:show|suggest|find|establish)\w*",
            r"(?:code|weights?|model)\s+(?:(?:is|are)\s+)?(?:available|released?|open[\s-]?source)",
            r"github\.com",
            r"huggingface\.co",
        ],
    ),
    Category(
        label="Признати ограничения",
        weight=3.0,
        color="#14b8a6",
        patterns=[
            r"\blimitation\w*",
            r"does\s+not\s+(?:generalize|scale|work|handle|transfer)\b",
            r"fail\w+\s+(?:to|on|when|for)\s+\w+",
            r"remain\w*\s+(?:unsolved|challenging|an?\s+open\s+(?:question|problem))",
            r"future\s+work\s+(?:will|could|should|may)\b",
            r"not\s+(?:yet\s+)?(?:a\s+)?(?:general|complete|full)\s+(?:solution|approach|system)",
            r"only\s+(?:test\w+|evaluat\w+|validat\w+)\s+on\b",
        ],
    ),
    Category(
        label="Научна предпазливост",
        weight=1.5,
        color="#3b82f6",
        patterns=[
            r"\bsuggests?\s+(?:that\s+)?\w+",
            r"\bindicates?\s+(?:that\s+)?\w+",
            r"\bappears?\s+to\s+\w+",
            r"\bmay\s+(?:not\s+)?(?:be\s+)?\w+",
            r"\bwe\s+(?:observe|find|note|believe|conjecture|hypothesize)\b",
            r"\bin\s+(?:our|this)\s+(?:experiment\w*|setting|context|study)\b",
            r"\bto\s+(?:our|the\s+best\s+of\s+(?:our|the))\s+knowledge\b",
            r"\bpreliminar\w+\b",
            r"\bseems?\s+to\s+\w+",
        ],
    ),
    Category(
        label="Сравнение с baseline",
        weight=2.0,
        color="#22c55e",
        patterns=[
            r"compared\s+to\s+\w+",
            r"\bvs\.?\s+\w+",
            r"outperform\w+\s+\w+",
            r"(?:over|above)\s+(?:the\s+)?(?:baseline|prior|previous)\s+\w+",
            r"prior\s+(?:work|model|approach|state[\s-]of[\s-]the[\s-]art)",
            r"(?:surpass\w+|exceed\w+)\s+\w+.*?\d",
        ],
    ),
]

ALL_CATEGORIES = HYPE_CATEGORIES + SIGNAL_CATEGORIES

# Max possible scores (all categories fire once)
_HYPE_MAX   = sum(c.weight for c in HYPE_CATEGORIES)
_SIGNAL_MAX = sum(c.weight for c in SIGNAL_CATEGORIES)


# ── Novelty patterns (separate from scoring — used for novelty verdict) ──────

_NOVELTY_CLAIM_PATTERNS = [
    r"\bfirst\s+(?:to\b|ever\b|known\b|of\s+its\s+kind\b|time\b)",
    r"\bnovel\s+(?:approach|method|architecture|framework|technique|algorithm)\b",
    r"\bnew\s+(?:approach|method|way\s+to|paradigm|architecture|technique)\b",
    r"we\s+(?:propose|introduce|present|develop)\s+a\s+(?:new|novel)\b",
    r"\bpreviously\s+(?:unknown|unexplored|unseen|unaddressed)\b",
    r"\bno\s+(?:prior|previous|existing)\s+work\s+(?:has|have|addresses?)\b",
    r"\bstate[\s-]of[\s-]the[\s-]art\b",
    r"\bnew\s+(?:sota|benchmark|record)\b",
    r"outperform\w*\s+(?:all\s+)?(?:prior|previous|existing|current)\b",
]

_BACKING_PATTERNS = [          # mirrors Prior work category — for novelty check
    r"\bet\s+al\.",
    r"\barxiv\b",
    r"(?:prior|previous)\s+(?:work|research|stud\w+)",
    r"(?:following|building\s+on|extending)\s+\w+",
    r"(?:code|weights?|model)\s+(?:(?:is|are)\s+)?(?:available|released?|open[\s-]?source)",
    r"github\.com",
    r"huggingface\.co",
]


# ---------------------------------------------------------------------------
# Novelty assessment
# ---------------------------------------------------------------------------

def _assess_novelty(text: str) -> dict:
    """
    Independent of scoring — detects whether the text claims novelty
    and whether it contextualises that claim with prior work.
    """
    tl = text.lower()

    novelty_phrases = []
    for p in _NOVELTY_CLAIM_PATTERNS:
        for m in re.finditer(p, tl):
            phrase = text[m.start():m.end()].strip()
            if phrase.lower() not in [x.lower() for x in novelty_phrases]:
                novelty_phrases.append(phrase)

    has_novelty = len(novelty_phrases) > 0
    has_backing = any(re.search(p, tl) for p in _BACKING_PATTERNS)

    if has_novelty and has_backing:
        verdict = "Нова теза с контекст"
        color   = "#10b981"
        icon    = "✓"
    elif has_novelty and not has_backing:
        verdict = "Претендира за новост"
        color   = "#f59e0b"
        icon    = "⚠"
    elif not has_novelty and has_backing:
        verdict = "Надгражда познатото"
        color   = "#3b82f6"
        icon    = "✓"
    else:
        verdict = "Неясно"
        color   = "#64748b"
        icon    = "–"

    return {
        "verdict":         verdict,
        "color":           color,
        "icon":            icon,
        "has_novelty":     has_novelty,
        "has_backing":     has_backing,
        "novelty_phrases": novelty_phrases[:6],   # top 6 for display
    }


# ---------------------------------------------------------------------------
# Match finding
# ---------------------------------------------------------------------------

def _find_matches(text: str) -> list[dict]:
    text_lower = text.lower()
    matches = []
    for cat in ALL_CATEGORIES:
        seen: set[tuple[int, int]] = set()
        for pattern in cat.patterns:
            for m in re.finditer(pattern, text_lower):
                span = (m.start(), m.end())
                if span not in seen:
                    seen.add(span)
                    matches.append({
                        "start":    m.start(),
                        "end":      m.end(),
                        "text":     text[m.start():m.end()],
                        "category": cat.label,
                        "color":    cat.color,
                        "weight":   cat.weight,
                        "is_hype":  cat in HYPE_CATEGORIES,
                    })
    matches.sort(key=lambda m: (m["start"], -(m["end"] - m["start"])))
    return matches


def _remove_overlaps(matches: list[dict]) -> list[dict]:
    result, last_end = [], 0
    for m in matches:
        if m["start"] >= last_end:
            result.append(m)
            last_end = m["end"]
    return result


# ---------------------------------------------------------------------------
# Scoring — each category fires at most once
# ---------------------------------------------------------------------------

def _compute_scores(matches: list[dict]) -> tuple[float, float]:
    fired_hype:   set[str] = set()
    fired_signal: set[str] = set()

    for m in matches:
        if m["is_hype"]:
            fired_hype.add(m["category"])
        else:
            fired_signal.add(m["category"])

    hype_raw   = sum(c.weight for c in HYPE_CATEGORIES   if c.label in fired_hype)
    signal_raw = sum(c.weight for c in SIGNAL_CATEGORIES if c.label in fired_signal)

    hype_score   = round(min(10.0, hype_raw   / _HYPE_MAX   * 10), 1)
    signal_score = round(min(10.0, signal_raw / _SIGNAL_MAX * 10), 1)

    return hype_score, signal_score


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def _verdict(hype: float, signal: float) -> tuple[str, str]:
    if hype >= 7 and signal < 3:
        return "Маркетингов хайп", "high_hype"
    if hype >= 5 and hype > signal:
        return "Вероятно хайп", "likely_hype"
    if signal >= 7 and hype < 3:
        return "Силна аргументация", "strong_signal"
    if signal >= 5 and signal > hype:
        return "Добра аргументация", "signal"
    if hype < 3 and signal < 3:
        return "Недостатъчно данни", "neutral"
    return "Смесен сигнал", "mixed"


# ---------------------------------------------------------------------------
# HTML highlighting
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Claim extraction — what does the text actually say?
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

_CLAIM_SENTENCE_PATTERNS = [p for cat in HYPE_CATEGORIES + SIGNAL_CATEGORIES
                             if cat.label in ("Революционни претенции", "Маркетингови суперлативи", "Претенциозност")
                             for p in cat.patterns]
_CLAIM_SENTENCE_PATTERNS += [
    r"(?:achieve|surpass|outperform|exceed|beat)\w+",
    r"\bis\s+(?:the\s+)?(?:first|only|best)\s+(?:to|that)\b",
    r"(?:we|this\s+(?:paper|model|system))\s+(?:show|demonstrate|introduce|propose)s?\b",
    r"(?:enable|allow)s?\s+\w+\s+to\b",
    r"(?:will|can)\s+\w+\s+\w+",
]

_GROUND_SENTENCE_PATTERNS = [p for cat in SIGNAL_CATEGORIES
                              if cat.label == "Доказателство"
                              for p in cat.patterns]


def _extract_claims(text: str) -> dict:
    """
    Split text into sentences, find those containing claims,
    classify each as supported (has evidence nearby) or needs verification.
    """
    sentences = _SENT_SPLIT.split(text.strip())
    tl = text.lower()

    # Which sentence indices have grounds nearby (±1 sentence window)
    has_ground_near: set[int] = set()
    for i, sent in enumerate(sentences):
        sl = sent.lower()
        if any(re.search(p, sl) for p in _GROUND_SENTENCE_PATTERNS):
            for j in (i - 1, i, i + 1):
                if 0 <= j < len(sentences):
                    has_ground_near.add(j)

    supported:    list[str] = []
    to_verify:    list[str] = []

    for i, sent in enumerate(sentences):
        sent = sent.strip()
        if len(sent.split()) < 6:
            continue
        sl = sent.lower()
        is_claim = any(re.search(p, sl) for p in _CLAIM_SENTENCE_PATTERNS)
        if not is_claim:
            continue

        # Trim long sentences
        display = sent if len(sent) <= 160 else sent[:157] + "…"

        if i in has_ground_near:
            supported.append(display)
        else:
            to_verify.append(display)

    return {
        "supported": supported[:3],
        "to_verify": to_verify[:4],
    }


# ---------------------------------------------------------------------------
# Trust conclusion
# ---------------------------------------------------------------------------

def _trust_conclusion(
    hype: float,
    signal: float,
    toulmin_fired: dict,
    novelty: dict,
) -> dict:
    """
    Synthesises all signals into a human-readable trust verdict.
    Returns: level, color, summary, what_to_trust, watch_out.
    """
    has_rebuttal = toulmin_fired.get("Признати ограничения", False)
    has_backing  = toulmin_fired.get("Prior work / Верифицируемост", False)
    has_grounds  = toulmin_fired.get("Доказателство", False)
    novelty_v    = novelty.get("verdict", "")

    caveats: list[str] = []
    positives: list[str] = []

    # Build specific observations
    if has_grounds:
        positives.append("Съдържа конкретни числа и метрики")
    if has_backing:
        positives.append("Цитира предишна работа или публикува код")
    if has_rebuttal:
        positives.append("Авторите признават ограничения")
    if novelty_v == "Нова теза с контекст":
        positives.append("Новостта е поставена в контекст спрямо prior work")

    if hype >= 5:
        caveats.append("Съдържа маркетингов език — внимавай с абсолютните твърдения")
    if novelty_v == "Претендира за новост":
        caveats.append("Твърди новост без да цитира предишна работа — провери дали идеята е наистина нова")
    if not has_grounds and hype >= 4:
        caveats.append("Липсват конкретни числа — твърденията са неизмерими")
    if not has_rebuttal and signal >= 5:
        caveats.append("Без признати ограничения — резултатите може да не се генерализират")

    # Overall level
    if signal >= 7 and hype <= 2:
        level   = "Висок"
        color   = "#10b981"
        summary = "Статията е добре аргументирана. Твърденията са подкрепени с данни и контекст."
    elif signal >= 5 and hype <= 4:
        level   = "Умерен"
        color   = "#3b82f6"
        summary = "Съдържа реална субстанция. Доверявай се на конкретните числа, но бъди скептичен към общите твърдения."
    elif signal >= 4 and hype >= 5:
        level   = "Умерен с резерви"
        color   = "#f59e0b"
        summary = "Вероятно има зърно истина, но е обвито в промоционален език. Търси конкретните факти, игнорирай суперлативите."
    elif hype >= 7 and signal <= 3:
        level   = "Нисък"
        color   = "#ef4444"
        summary = "Предимно маркетингов текст без подкрепящи данни. Не приемай твърденията без независима проверка."
    elif hype < 3 and signal < 3:
        level   = "Неясен"
        color   = "#64748b"
        summary = "Недостатъчно сигнали за категорична оценка. Провери допълнителни източници."
    else:
        level   = "Смесен"
        color   = "#f59e0b"
        summary = "Смесени сигнали — частично подкрепени твърдения. Подхождай селективно."

    return {
        "level":     level,
        "color":     color,
        "summary":   summary,
        "positives": positives,
        "caveats":   caveats,
    }


def _build_html(text: str, highlights: list[dict]) -> str:
    parts, pos = [], 0
    for hl in highlights:
        if pos < hl["start"]:
            parts.append(html_lib.escape(text[pos:hl["start"]]))
        col     = hl["color"]
        matched = html_lib.escape(text[hl["start"]:hl["end"]])
        side    = "hype" if hl["is_hype"] else "signal"
        parts.append(
            f'<span class="hl hl-{side}" '
            f'style="background:{col}22;border-bottom:2px solid {col};'
            f'border-radius:2px;cursor:default;" '
            f'title="{html_lib.escape(hl["category"])}">'
            f'{matched}</span>'
        )
        pos = hl["end"]
    if pos < len(text):
        parts.append(html_lib.escape(text[pos:]))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze(text: str) -> dict:
    word_count  = len(text.split())
    all_matches = _find_matches(text)
    highlights  = _remove_overlaps(all_matches)

    hype_score, signal_score = _compute_scores(all_matches)
    verdict, level = _verdict(hype_score, signal_score)

    # Group by category for display
    from collections import defaultdict
    hype_groups:   dict[str, list[str]] = defaultdict(list)
    signal_groups: dict[str, list[str]] = defaultdict(list)
    colors: dict[str, str] = {}

    for m in all_matches:
        phrase = m["text"].lower().strip()
        colors[m["category"]] = m["color"]
        if m["is_hype"]:
            if phrase not in hype_groups[m["category"]]:
                hype_groups[m["category"]].append(phrase)
        else:
            if phrase not in signal_groups[m["category"]]:
                signal_groups[m["category"]].append(phrase)

    # Fired categories summary (for Toulmin-style breakdown)
    toulmin_fired = {
        cat.label: cat.label in signal_groups
        for cat in SIGNAL_CATEGORIES
    }

    novelty = _assess_novelty(text)
    trust   = _trust_conclusion(hype_score, signal_score, toulmin_fired, novelty)
    claims  = _extract_claims(text)

    return {
        "hype_score":       hype_score,
        "signal_score":     signal_score,
        "verdict":          verdict,
        "verdict_level":    level,
        "novelty":          novelty,
        "trust":            trust,
        "claims":           claims,
        "highlighted_html": _build_html(text, highlights),
        "hype_triggers": [
            {"category": cat, "matches": phrases, "color": colors[cat]}
            for cat, phrases in hype_groups.items()
        ],
        "signal_triggers": [
            {"category": cat, "matches": phrases, "color": colors[cat]}
            for cat, phrases in signal_groups.items()
        ],
        "toulmin_fired":    toulmin_fired,
        "word_count":       word_count,
    }
