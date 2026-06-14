# fetch_cards_for_set.py
# Usage: python fetch_cards_for_set.py SV9 --api_key YOUR_KEY --out cards_SV9.csv
import argparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://api.pokemontcg.io/v2"

CARD_FIELDS = [
    "id","name","set.id","set.name","set.series","number","rarity","supertype","subtypes",
    "types","hp","evolvesFrom","regulationMark","artist","abilities","attacks",
    "weaknesses","resistances","retreatCost","rules","flavorText",
    "legalities.standard","legalities.expanded","legalities.unlimited",
    "nationalPokedexNumbers","releaseDate","tcgplayer.productId","images.small","images.large"
]

def flatten_card(c):
    def get(path, default=None):
        cur = c
        for part in path.split("."):
            if isinstance(cur, list):
                return default
            cur = cur.get(part) if isinstance(cur, dict) else default
            if cur is None:
                return default
        return cur
    row = {
        "id": c.get("id"),
        "name": c.get("name"),
        "set_code": get("set.id"),
        "set_name": get("set.name"),
        "series": get("set.series"),
        "number": c.get("number"),
        "rarity": c.get("rarity"),
        "supertype": c.get("supertype"),
        "subtypes": ",".join(c.get("subtypes", []) or []),
        "types": ",".join(c.get("types", []) or []),
        "stage": ",".join(c.get("subtypes", []) or []),
        "hp": c.get("hp"),
        "evolves_from": c.get("evolvesFrom"),
        "regulation_mark": c.get("regulationMark"),
        "illustrator": c.get("artist"),
        "ability_name": (c.get("abilities") or [{}])[0].get("name") if c.get("abilities") else None,
        "ability_text": (c.get("abilities") or [{}])[0].get("text") if c.get("abilities") else None,
        "ability_type": (c.get("abilities") or [{}])[0].get("type") if c.get("abilities") else None,
        "attack1_name": (c.get("attacks") or [{}])[0].get("name") if c.get("attacks") else None,
        "attack1_cost": ",".join((c.get("attacks") or [{}])[0].get("cost", []) if c.get("attacks") else []),
        "attack1_damage": (c.get("attacks") or [{}])[0].get("damage") if c.get("attacks") else None,
        "attack1_text": (c.get("attacks") or [{}])[0].get("text") if c.get("attacks") else None,
        "attack2_name": (c.get("attacks") or [{}, {}] )[1].get("name") if len(c.get("attacks", []))>1 else None,
        "attack2_cost": ",".join((c.get("attacks") or [{}, {}])[1].get("cost", []) if len(c.get("attacks") or [])>1 else []),
        "attack2_damage": (c.get("attacks") or [{}, {}])[1].get("damage") if len(c.get("attacks") or [])>1 else None,
        "attack2_text": (c.get("attacks") or [{}, {}])[1].get("text") if len(c.get("attacks") or [])>1 else None,
        "attack3_name": (c.get("attacks") or [{}, {}, {}])[2].get("name") if len(c.get("attacks") or [])>2 else None,
        "attack3_cost": ",".join((c.get("attacks") or [{}, {}, {}])[2].get("cost", []) if len(c.get("attacks") or [])>2 else []),
        "attack3_damage": (c.get("attacks") or [{}, {}, {}])[2].get("damage") if len(c.get("attacks") or [])>2 else None,
        "attack3_text": (c.get("attacks") or [{}, {}, {}])[2].get("text") if len(c.get("attacks") or [])>2 else None,
        "weaknesses": ";".join([f"{w.get('type')}:{w.get('value')}" for w in (c.get("weaknesses") or [])]),
        "resistances": ";".join([f"{r.get('type')}:{r.get('value')}" for r in (c.get('resistances') or [])]),
        "retreat_cost": len(c.get("retreatCost") or []),
        "rules_text": " | ".join(c.get("rules") or []),
        "flavor_text": c.get("flavorText"),
        "legal_standard": get("legalities.standard"),
        "legal_expanded": get("legalities.expanded"),
        "legal_unlimited": get("legalities.unlimited"),
        "national_pokedex_numbers": ",".join([str(n) for n in c.get("nationalPokedexNumbers", []) or [] ]),
        "release_date": get("set.releaseDate") or c.get("releaseDate"),
        "tcgplayer_product_id": get("tcgplayer.productId"),
        "image_small": get("images.small"),
        "image_large": get("images.large"),
    }
    return row

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set_code", help="Example: SV9 or SVI (API set id). Try the API 'sets' endpoint to list ids.")
    ap.add_argument("--api_key", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    page = 1
    page_size = getattr(args, "page_size", None) or 100

    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.6,          # 0.6, 1.2, 2.4, 4.8, 9.6s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"X-Api-Key": args.api_key, "Accept-Encoding": "gzip"})

    rows = []
    while True:
        params = {
            "q": f"set.id:{args.set_code}",
            "page": page,
            "pageSize": page_size,
            "select": ",".join(CARD_FIELDS),
        }
        r = session.get(f"{BASE}/cards", params=params, timeout=(5, 60))
        r.raise_for_status()
        data = r.json()
        cards = data.get("data", [])
        if not cards:
            break
        for c in cards:
            rows.append(flatten_card(c))
        if len(cards) < page_size:
            break
        page += 1

if __name__ == "__main__":
    main()
