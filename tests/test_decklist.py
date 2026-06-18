"""
Unit tests for the PTCGL decklist parser/formatter
(opama_pokemon_tcg.decks.decklist). Pure / offline.

Run with:
    PLUGIN_PATHS=external_plugins pytest tests/test_decklist.py -v
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "external_plugins"))

from opama_pokemon_tcg.decks.decklist import (
    parse_decklist, format_decklist, ExportLine,
)


SAMPLE = """\
Pokémon: 6
4 Charizard ex OBF 125
2 Charmander MEW 4

Trainer: 2
2 Professor's Research SVI 189

Energy: 52
52 Fire Energy

Total Cards: 60
"""


def test_parse_basic():
    cards = parse_decklist(SAMPLE)
    # 4 card lines; headers + Total Cards + blanks skipped
    assert len(cards) == 4
    char = cards[0]
    assert char.qty == 4 and char.name == "Charizard ex"
    assert char.set_code == "OBF" and char.number == "125"


def test_parse_line_without_set_number():
    [c] = parse_decklist("52 Fire Energy")
    assert c.qty == 52 and c.name == "Fire Energy"
    assert c.set_code is None and c.number is None


def test_parse_handles_promo_and_tg_numbers():
    cards = parse_decklist("1 Pikachu PR-SV 50\n1 Giratina TG 12")
    assert (cards[0].set_code, cards[0].number) == ("PR-SV", "50")
    assert (cards[1].set_code, cards[1].number) == ("TG", "12")


def test_parse_skips_headers_and_junk():
    assert parse_decklist("Pokémon: 12\n\nTotal Cards: 60\n# comment") == []


def test_parse_name_with_trailing_words_not_setcode():
    # "Mewtwo & Mew-GX" has no set/number → whole thing is the name
    [c] = parse_decklist("3 Mewtwo & Mew-GX")
    assert c.name == "Mewtwo & Mew-GX" and c.set_code is None


def test_format_roundtrip_groups_and_totals():
    lines = [
        ExportLine("Pokémon", 4, "Charizard ex", "OBF", "125"),
        ExportLine("Trainer", 2, "Professor's Research", "SVI", "189"),
        ExportLine("Energy", 54, "Fire Energy", None, None),
    ]
    text = format_decklist(lines)
    assert "Pokémon: 4" in text
    assert "4 Charizard ex OBF 125" in text
    assert "54 Fire Energy" in text          # no set/number tail
    assert "Total Cards: 60" in text
    # and it re-parses to the same 3 lines
    assert len(parse_decklist(text)) == 3
