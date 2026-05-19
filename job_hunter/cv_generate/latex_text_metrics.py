"""Plain-text word counts for LaTeX CV sections."""

from __future__ import annotations

import re


def strip_latex_to_plain_text(latex: str) -> str:
    """Remove common LaTeX markup for approximate word counting."""
    text = latex
    text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\\textbf\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\textit\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\emph\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z@]+(\[[^\]]*\])?\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\[a-zA-Z@]+", "", text)
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def count_textbf_spans(latex: str) -> int:
    """Count ``\\textbf{...}`` occurrences in a LaTeX fragment."""
    return len(re.findall(r"\\textbf\{", latex))


def count_plain_words(text: str) -> int:
    plain = strip_latex_to_plain_text(text)
    if not plain:
        return 0
    return len(re.findall(r"\b[\w'-]+\b", plain, flags=re.UNICODE))


def count_latex_item_bullets(latex: str) -> int:
    return latex.count(r"\item")


def cap_latex_item_bullets(latex: str, max_items: int) -> str:
    """Keep only the first ``max_items`` ``\\item`` entries in ``latex``."""
    if max_items < 0:
        return latex

    item_starts = list(re.finditer(r"\\item\b", latex))
    if len(item_starts) <= max_items:
        return latex

    trimmed = latex[: item_starts[max_items].start()].rstrip()
    open_zitemize = trimmed.count(r"\begin{zitemize}") - trimmed.count(r"\end{zitemize}")
    for _ in range(open_zitemize):
        trimmed += "\n\\end{zitemize}"
    return trimmed + "\n"


def extract_zitemize_bullets(latex: str) -> list[str]:
    """Return inner text of each ``\\item`` inside ``zitemize`` environments."""
    bullets: list[str] = []
    for block in re.finditer(r"\\begin\{zitemize\}(.*?)\\end\{zitemize\}", latex, re.DOTALL):
        for part in re.split(r"\\item\b", block.group(1)):
            bullet = part.strip()
            if bullet:
                bullets.append(bullet)
    return bullets
