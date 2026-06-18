"""
Pokémon TCG deck construction + format-legality validation.

Pure functions over (card, quantity) entries — no DB, no FastAPI — so they're
trivially testable. The catalog already carries everything we need: `supertype`,
`subtypes`/`stage` (comma-separated, e.g. "Basic,V"), and per-format legality
(`legal_standard`/`legal_expanded`/`legal_unlimited`, "Legal" when the card is
legal in that format).

Rules enforced (constructed Standard/Expanded):
  - exactly 60 cards;
  - at least one Basic Pokémon;
  - at most 4 copies of any card *by name* — basic Energy is exempt (unlimited);
  - at most 1 ACE SPEC and at most 1 Radiant Pokémon per deck;
  - every card legal in the chosen format.

Legality degrades gracefully: if the catalog has no legality data loaded yet
(e.g. running off the bundled seed rather than a live sync), the per-card
legality check is skipped with a single warning instead of failing every card.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, Sequence

DECK_SIZE = 60
MAX_COPIES = 4
VALID_FORMATS = ("standard", "expanded", "unlimited")


class CardLike(Protocol):
    name: str
    supertype: Optional[str]
    subtypes: Optional[str]
    stage: Optional[str]
    legal_standard: Optional[str]
    legal_expanded: Optional[str]
    legal_unlimited: Optional[str]


@dataclass
class DeckIssue:
    code: str          # deck_size | no_basic | copy_limit | ace_spec | radiant | not_legal | legality_unknown | unknown_card
    severity: str      # "error" | "warning"
    message: str
    card_name: Optional[str] = None


@dataclass
class DeckValidation:
    format: str
    legal: bool
    total: int
    counts: dict           # {"pokemon": int, "trainer": int, "energy": int}
    issues: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "legal": self.legal,
            "total": self.total,
            "counts": self.counts,
            "issues": [vars(i) for i in self.issues],
        }


def _subtypes(card: CardLike) -> set[str]:
    raw = card.subtypes or card.stage or ""
    return {s.strip() for s in raw.split(",") if s.strip()}


def _is_basic_energy(card: CardLike) -> bool:
    return (card.supertype == "Energy") and ("Basic" in _subtypes(card))


def _is_basic_pokemon(card: CardLike) -> bool:
    return (card.supertype == "Pokémon") and ("Basic" in _subtypes(card))


def _legal_attr(fmt: str) -> Optional[str]:
    return {"standard": "legal_standard", "expanded": "legal_expanded"}.get(fmt)


def validate_deck(entries: Sequence[tuple[CardLike, int]], fmt: str = "standard") -> DeckValidation:
    """Validate a deck given (card, quantity) entries against ``fmt``."""
    fmt = (fmt or "standard").strip().lower()
    if fmt not in VALID_FORMATS:
        fmt = "standard"

    issues: list[DeckIssue] = []
    total = sum(q for _, q in entries)
    counts = {
        "pokemon": sum(q for c, q in entries if c.supertype == "Pokémon"),
        "trainer": sum(q for c, q in entries if c.supertype == "Trainer"),
        "energy": sum(q for c, q in entries if c.supertype == "Energy"),
    }

    # 1. Deck size — exactly 60.
    if total != DECK_SIZE:
        issues.append(DeckIssue(
            "deck_size", "error",
            f"Deck has {total} cards; must be exactly {DECK_SIZE}."))

    # 2. At least one Basic Pokémon (you can't start a game without one).
    if not any(_is_basic_pokemon(c) for c, _ in entries):
        issues.append(DeckIssue(
            "no_basic", "error", "Deck must include at least one Basic Pokémon."))

    # 3. Copy limit — max 4 by card *name*; basic Energy is unlimited.
    by_name: dict[str, list] = {}
    for c, q in entries:
        slot = by_name.setdefault(c.name, [0, _is_basic_energy(c)])
        slot[0] += q
    for name, (qty, basic_energy) in by_name.items():
        if not basic_energy and qty > MAX_COPIES:
            issues.append(DeckIssue(
                "copy_limit", "error",
                f"{qty}× '{name}' exceeds the {MAX_COPIES}-copy limit.", card_name=name))

    # 4. ACE SPEC — at most 1 per deck (across all ACE SPEC cards).
    ace = sum(q for c, q in entries if "ACE SPEC" in _subtypes(c))
    if ace > 1:
        issues.append(DeckIssue(
            "ace_spec", "error", f"{ace} ACE SPEC cards; only 1 is allowed per deck."))

    # 5. Radiant Pokémon — at most 1 per deck.
    radiant = sum(q for c, q in entries if "Radiant" in _subtypes(c))
    if radiant > 1:
        issues.append(DeckIssue(
            "radiant", "error", f"{radiant} Radiant Pokémon; only 1 is allowed per deck."))

    # 6. Format legality (Unlimited has no rotation, so nothing to check).
    legal_attr = _legal_attr(fmt)
    if legal_attr:
        has_data = any(
            (c.legal_standard or c.legal_expanded or c.legal_unlimited) for c, _ in entries)
        if not has_data:
            issues.append(DeckIssue(
                "legality_unknown", "warning",
                "Format legality not checked — the catalog has no legality data yet "
                "(sync the catalog to enable this)."))
        else:
            seen: set[str] = set()
            for c, _ in entries:
                if c.name in seen:
                    continue
                seen.add(c.name)
                val = (getattr(c, legal_attr) or "").strip().lower()
                if val != "legal":
                    issues.append(DeckIssue(
                        "not_legal", "error",
                        f"'{c.name}' is not {fmt.title()}-legal.", card_name=c.name))

    legal = not any(i.severity == "error" for i in issues)
    return DeckValidation(format=fmt, legal=legal, total=total, counts=counts, issues=issues)
