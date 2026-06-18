"""
PTCGO / PTCG Live decklist text format — parse + format.

The format players paste in and out of PTCG Live looks like:

    Pokémon: 12
    4 Charizard ex OBF 125
    3 Charmander MEW 4

    Trainer: 36
    4 Professor's Research SVI 189

    Energy: 12
    9 Fire Energy SVE 2

Each card line is ``<qty> <name> <SETCODE> <number>`` (set code + number are
optional — some exports and basic energies use just ``<qty> <name>``). Section
headers (``Pokémon:``/``Trainer:``/``Energy:``/``Total Cards:``) and blank lines
are ignored on parse.

These are pure string functions — resolving a parsed line to a catalog card_id
happens in the router (it needs the DB).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

_SECTION_RE = re.compile(r"^\s*(pok[eé]mon|trainer|energy|total cards?)\s*:", re.IGNORECASE)
_QTY_RE = re.compile(r"^\s*(?:[*x]\s*)?(\d+)\s+(.*\S)\s*$")

# A trailing "<SETCODE> <number>": set code is short and upper/digit/hyphen,
# number contains at least one digit (handles "125", "TG12", "SV122", "H1").
_SETCODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,6}$")
_NUMBER_RE = re.compile(r"^[A-Za-z]{0,3}\d+[A-Za-z]?$")


@dataclass
class ParsedCard:
    qty: int
    name: str
    set_code: Optional[str]   # PTCGO set code, e.g. "OBF" (None if the line omitted it)
    number: Optional[str]     # card number within the set


def parse_decklist(text: str) -> list[ParsedCard]:
    """Parse decklist text into ParsedCard entries (skips headers/blank lines)."""
    out: list[ParsedCard] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or _SECTION_RE.match(line):
            continue
        m = _QTY_RE.match(line)
        if not m:
            continue
        qty = int(m.group(1))
        rest = m.group(2).split()
        set_code = number = None
        # Peel a trailing "<SETCODE> <number>" if the last two tokens look like one.
        if len(rest) >= 3 and _SETCODE_RE.match(rest[-2]) and _NUMBER_RE.match(rest[-1]):
            set_code, number = rest[-2], rest[-1]
            name = " ".join(rest[:-2])
        else:
            name = " ".join(rest)
        if qty > 0 and name:
            out.append(ParsedCard(qty=qty, name=name, set_code=set_code, number=number))
    return out


@dataclass
class ExportLine:
    category: str       # "Pokémon" | "Trainer" | "Energy"
    qty: int
    name: str
    set_code: Optional[str]
    number: Optional[str]


_CATEGORY_ORDER = ("Pokémon", "Trainer", "Energy")


def format_decklist(lines: Sequence[ExportLine]) -> str:
    """Render ExportLines as PTCG Live decklist text, grouped by category."""
    blocks: list[str] = []
    for cat in _CATEGORY_ORDER:
        group = [ln for ln in lines if ln.category == cat]
        if not group:
            continue
        total = sum(ln.qty for ln in group)
        rows = [f"{cat}: {total}"]
        for ln in group:
            tail = f" {ln.set_code} {ln.number}" if ln.set_code and ln.number else ""
            rows.append(f"{ln.qty} {ln.name}{tail}")
        blocks.append("\n".join(rows))
    grand = sum(ln.qty for ln in lines)
    body = "\n\n".join(blocks)
    return f"{body}\n\nTotal Cards: {grand}\n" if body else f"Total Cards: {grand}\n"
