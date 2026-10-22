# core/semantic/parsers/math_parser.py
"""Mathematical query parser for arithmetic, percentages, algebra, powers, roots, and statistics."""

import re
from typing import Optional

from core.semantic.models import SemanticAction

PCT_ADD_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:mein|me|\+)\s*(\d+(?:\.\d+)?)\s*(?:percent|%|pratishat)\s*(?:add|jod|plus|tax)',
    re.IGNORECASE
)
PCT_DISC_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:ka|ki|se|mein\s+se|-)?\s*(\d+(?:\.\d+)?)\s*(?:percent|%|pratishat)\s*(?:minus|discount|ghatao|kam)',
    re.IGNORECASE
)
PCT_OF_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:ka|ki|of)\s*(\d+(?:\.\d+)?)\s*(?:percent|%|pratishat)',
    re.IGNORECASE
)
SQRT_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:ka|ki|of)?\s*(?:square\s+root|vargmool|sqrt|root)\b',
    re.IGNORECASE
)
CBRT_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:ka|ki|of)?\s*(?:cube\s+root|ghanmool|cbrt)\b',
    re.IGNORECASE
)
SQUARE_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:ka|ki|of)?\s*(?:square|varg)\b(?!\s*root)',
    re.IGNORECASE
)
CUBE_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:ka|ki|of)?\s*(?:cube|ghan)\b(?!\s*root)',
    re.IGNORECASE
)
ALGEBRA_EQ_RE = re.compile(
    r'([a-zA-Z0-9\s\+\-\*\/\^\=]+?)(?:\s+(?:solve\s+karo|solve|nikalo|batao))?$',
    re.IGNORECASE
)
ARITH_RE = re.compile(
    r'^(?:calculate|compute|solve|eval|evaluate|what\s+is|what\'s|batao|hisaab\s+karo)?\s*\(?\s*\d+(?:\.\d+)?\s*(?:[\+\-\*\/\^%x]|times|plus|minus|into|divided\s+by|divide\s+by|multiplied\s+by)',
    re.IGNORECASE
)
FUNC_RE = re.compile(
    r'^(?:sqrt|cbrt|sin|cos|tan|log|log10|factorial)\(',
    re.IGNORECASE
)
EXPLICIT_CALC_RE = re.compile(
    r'^(?:calculate|hisaab\s+karo|solve)\s+.+\d+',
    re.IGNORECASE
)
STAT_RE = re.compile(
    r'\b(?:mean|average|ausat|median|mode)\s+(?:of|nikalo|batao)?\s*([0-9\s\,\.\-]+)',
    re.IGNORECASE
)
DIGITS_RE = re.compile(r'\d+')
CLEAN_EQ_PREFIX_RE = re.compile(
    r'^(?:jarvis|please|batao|solve|equation)\s*[,:]?\s*',
    re.IGNORECASE
)


def parse_math(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Detects arithmetic expressions, equation solving, powers, roots, percentages, and statistics."""
    # 1. Percentage Operations (add/tax, discount/minus, of)
    m_pct_add = PCT_ADD_RE.search(lowered)
    if m_pct_add:
        return SemanticAction(
            intent="PERCENTAGE",
            service="math",
            action="percentage",
            query=raw_text,
            parameters={"base": float(m_pct_add.group(1)), "percent": float(m_pct_add.group(2)), "action": "add"}
        )

    m_pct_disc = PCT_DISC_RE.search(lowered)
    if m_pct_disc:
        return SemanticAction(
            intent="PERCENTAGE",
            service="math",
            action="percentage",
            query=raw_text,
            parameters={"base": float(m_pct_disc.group(1)), "percent": float(m_pct_disc.group(2)), "action": "discount"}
        )

    m_pct_of = PCT_OF_RE.search(lowered)
    if m_pct_of:
        return SemanticAction(
            intent="PERCENTAGE",
            service="math",
            action="percentage",
            query=raw_text,
            parameters={"base": float(m_pct_of.group(1)), "percent": float(m_pct_of.group(2)), "action": "of"}
        )

    # 2. Powers and Roots
    m_sqrt = SQRT_RE.search(lowered)
    if m_sqrt:
        return SemanticAction(
            intent="POWER_ROOT",
            service="math",
            action="power_root",
            query=raw_text,
            parameters={"base": float(m_sqrt.group(1)), "operation": "sqrt"}
        )

    m_cbrt = CBRT_RE.search(lowered)
    if m_cbrt:
        return SemanticAction(
            intent="POWER_ROOT",
            service="math",
            action="power_root",
            query=raw_text,
            parameters={"base": float(m_cbrt.group(1)), "operation": "cbrt"}
        )

    m_sq = SQUARE_RE.search(lowered)
    if m_sq:
        return SemanticAction(
            intent="POWER_ROOT",
            service="math",
            action="power_root",
            query=raw_text,
            parameters={"base": float(m_sq.group(1)), "operation": "square"}
        )

    m_cb = CUBE_RE.search(lowered)
    if m_cb:
        return SemanticAction(
            intent="POWER_ROOT",
            service="math",
            action="power_root",
            query=raw_text,
            parameters={"base": float(m_cb.group(1)), "operation": "cube"}
        )

    # 3. Algebraic Equations
    if "=" in lowered and any(w in lowered for w in ["solve", "samikaran", "equation", " x ", " y ", "x+", "x-", "x*", "2x", "3x", "4x"]):
        m_eq = ALGEBRA_EQ_RE.search(lowered)
        if m_eq:
            clean_equation = CLEAN_EQ_PREFIX_RE.sub('', m_eq.group(1)).strip()
            return SemanticAction(
                intent="SOLVE_EQUATION",
                service="math",
                action="solve_equation",
                query=raw_text,
                parameters={"equation": clean_equation}
            )

    # 4. Statistics (Mean, Average, Median, Mode)
    m_stat = STAT_RE.search(lowered)
    if m_stat:
        nums_str = m_stat.group(1)
        nums = [
            float(n.strip())
            for n in re.split(r'[\s\,]+', nums_str)
            if n.strip() and n.strip().replace('.', '', 1).replace('-', '', 1).isdigit()
        ]
        if len(nums) >= 2:
            metric = "mean"
            if "median" in lowered:
                metric = "median"
            elif "mode" in lowered:
                metric = "mode"
            return SemanticAction(
                intent="CALCULATE",
                service="math",
                action="statistics",
                query=raw_text,
                parameters={"numbers": nums, "metric": metric}
            )

    # 5. Direct Arithmetic & Spoken Calculation
    is_arith = bool(ARITH_RE.search(lowered))
    is_func = bool(FUNC_RE.search(lowered))
    is_explicit_calc = bool(EXPLICIT_CALC_RE.search(lowered))
    is_spoken_arith = bool(
        any(w in lowered for w in ["jod do", "jod", "jodo", "ghatao", "guna karo", "guna", "bhaag do", "bhaag"])
        and DIGITS_RE.search(lowered)
    )

    if is_arith or is_func or is_explicit_calc or is_spoken_arith:
        return SemanticAction(
            intent="CALCULATE",
            service="math",
            action="calculate",
            query=raw_text,
            parameters={"expression": raw_text}
        )

    return None
