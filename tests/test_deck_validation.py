"""
Unit tests for the Pokémon TCG deck validator (opama_pokemon_tcg.decks.validation).

Pure / offline — a SimpleNamespace stands in for a catalog Card.

Run with:
    PLUGIN_PATHS=external_plugins pytest tests/test_deck_validation.py -v
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "external_plugins"))

from opama_pokemon_tcg.decks.validation import validate_deck


def card(name, supertype="Pokémon", subtypes="Basic",
         legal_standard=None, legal_expanded=None, legal_unlimited=None, stage=None):
    return SimpleNamespace(
        name=name, supertype=supertype, subtypes=subtypes, stage=stage or subtypes,
        legal_standard=legal_standard, legal_expanded=legal_expanded,
        legal_unlimited=legal_unlimited)


def codes(result):
    return {i["code"] for i in result.to_dict()["issues"]}


# A 60-card shell: 1 basic Pokémon ×4, 1 trainer ×4, basic energy ×52.
def _legal_shell():
    return [
        (card("Pikachu", "Pokémon", "Basic"), 4),
        (card("Professor's Research", "Trainer", "Supporter"), 4),
        (card("Lightning Energy", "Energy", "Basic"), 52),
    ]


def test_legal_deck_passes():
    r = validate_deck(_legal_shell(), "standard")
    # No legality data → a warning, but no errors → still "legal".
    assert r.legal is True
    assert r.total == 60
    assert codes(r) <= {"legality_unknown"}
    assert r.counts == {"pokemon": 4, "trainer": 4, "energy": 52}


def test_wrong_size_fails():
    deck = _legal_shell()
    deck[-1] = (deck[-1][0], 51)  # 59 cards
    r = validate_deck(deck, "standard")
    assert r.legal is False
    assert "deck_size" in codes(r)


def test_missing_basic_pokemon_fails():
    deck = [
        (card("Professor's Research", "Trainer", "Supporter"), 8),
        (card("Lightning Energy", "Energy", "Basic"), 52),
    ]
    r = validate_deck(deck, "standard")
    assert "no_basic" in codes(r) and r.legal is False


def test_copy_limit_by_name():
    deck = _legal_shell()
    deck[1] = (card("Boss's Orders", "Trainer", "Supporter"), 5)  # 5 copies
    deck[-1] = (deck[-1][0], 51)  # keep total 60
    r = validate_deck(deck, "standard")
    assert "copy_limit" in codes(r)


def test_basic_energy_exempt_from_copy_limit():
    # 52 basic energy is fine; ensure no copy_limit error fires for it.
    r = validate_deck(_legal_shell(), "standard")
    assert "copy_limit" not in codes(r)


def test_ace_spec_max_one():
    deck = [
        (card("Pikachu", "Pokémon", "Basic"), 4),
        (card("Computer Search", "Trainer", "Item,ACE SPEC"), 1),
        (card("Master Ball", "Trainer", "Item,ACE SPEC"), 1),
        (card("Lightning Energy", "Energy", "Basic"), 54),
    ]
    r = validate_deck(deck, "standard")
    assert "ace_spec" in codes(r)


def test_format_legality_enforced_when_data_present():
    deck = [
        (card("Pikachu", "Pokémon", "Basic", legal_standard="Legal"), 4),
        (card("Rotom V", "Pokémon", "Basic,V", legal_standard=None), 4),  # rotated out
        (card("Lightning Energy", "Energy", "Basic", legal_standard="Legal"), 52),
    ]
    r = validate_deck(deck, "standard")
    issues = codes(r)
    assert "not_legal" in issues
    assert "legality_unknown" not in issues  # data IS present
    assert r.legal is False


def test_unlimited_format_skips_legality():
    deck = _legal_shell()
    r = validate_deck(deck, "unlimited")
    assert "legality_unknown" not in codes(r)  # unlimited never rotation-checks
    assert r.legal is True
