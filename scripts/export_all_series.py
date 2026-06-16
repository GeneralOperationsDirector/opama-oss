# export_all_series.py
# Export ALL Pokémon TCG cards into per-set CSVs, organized by series.
# Features:
#   - Discovers every set via /v2/sets
#   - Organizes outputs: ./data/<series_slug>/<set_id>_<set_name_sanitized>.csv
#   - Pulls cards with pageSize=25 and enforces a 120s delay between *every* API call
#   - Retries aggressively on errors/timeouts; continues until all pages of every set are exported
#   - Saves progress to resume after interruptions (progress.json)
#
# Usage:
#   python export_all_series.py --api_key YOUR_KEY --outdir data
#
# Notes:
#   - This will take a long time due to the 2-minute delay per request (as requested).
#   - Uses a compact, denormalized schema suitable for analytics and deck-building.

import argparse
import os
import csv
import time
import re
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://api.pokemontcg.io/v2"
FIXED_PAGE_SIZE = 50           # User requirement
INTER_REQUEST_DELAY = 60.0    # seconds

CARD_FIELDS = [
    "id","name","set.id","set.name","set.series","number","rarity","supertype","subtypes",
    "types","hp","evolvesFrom","regulationMark","artist","abilities","attacks",
    "weaknesses","resistances","retreatCost","rules","flavorText",
    "legalities.standard","legalities.expanded","legalities.unlimited",
    "nationalPokedexNumbers","releaseDate","tcgplayer.productId","images.small","images.large"
]

def make_session(api_key: str) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=10,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"X-Api-Key": api_key, "Accept-Encoding": "gzip"})
    return s

def sanitize(name: str) -> str:
    if not name:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("_")

def flatten_card(c: dict) -> dict:
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
        "attack2_name": (c.get("attacks") or [{}, {}])[1].get("name") if len(c.get("attacks", []))>1 else None,
        "attack2_cost": ",".join((c.get("attacks") or [{}, {}])[1].get("cost", []) if len(c.get("attacks") or [])>1 else []),
        "attack2_damage": (c.get("attacks") or [{}, {}])[1].get("damage") if len(c.get("attacks") or [])>1 else None,
        "attack2_text": (c.get("attacks") or [{}, {}])[1].get("text") if len(c.get("attacks") or [])>1 else None,
        "attack3_name": (c.get("attacks") or [{}, {}, {}])[2].get("name") if len(c.get("attacks") or [])>2 else None,
        "attack3_cost": ",".join((c.get("attacks") or [{}, {}, {}])[2].get("cost", []) if len(c.get("attacks") or [])>2 else []),
        "attack3_damage": (c.get("attacks") or [{}, {}, {}])[2].get("damage") if len(c.get("attacks") or [])>2 else None,
        "attack3_text": (c.get("attacks") or [{}, {}, {}])[2].get("text") if len(c.get("attacks") or [])>2 else None,
        "weaknesses": ";".join([f"{w.get('type')}:{w.get('value')}" for w in (c.get("weaknesses") or [])]),
        "resistances": ";".join([f"{r.get('type')}:{r.get('value')}" for r in (c.get("resistances") or [])]),
        "retreat_cost": len(c.get("retreatCost") or []),
        "rules_text": " | ".join(c.get("rules") or []),
        "flavor_text": c.get("flavorText"),
        "legal_standard": get("legalities.standard"),
        "legal_expanded": get("legalities.expanded"),
        "legal_unlimited": get("legalities.unlimited"),
        "national_pokedex_numbers": ",".join([str(n) for n in (c.get("nationalPokedexNumbers") or [])]),
        "release_date": get("set.releaseDate") or c.get("releaseDate"),
        "tcgplayer_product_id": get("tcgplayer.productId"),
        "image_small": get("images.small"),
        "image_large": get("images.large"),
    }
    # numeric sort helper
    num = row["number"] or ""
    m = re.match(r"^(\d+)", str(num))
    row["number_sort"] = int(m.group(1)) if m else None
    return row

def sleep_with_progress(seconds: float):
    end = time.time() + seconds
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            break
        time.sleep(min(1.0, remaining))

def robust_get(session, url, params):
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = session.get(url, params=params, timeout=(5, 60))
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = min(600, 2 ** min(attempt, 10))
                print(f"[warn] HTTP {resp.status_code} on {url}. attempt={attempt} waiting {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            wait = min(600, 2 ** min(attempt, 10))
            print(f"[error] {e.__class__.__name__}: {e} | attempt={attempt} waiting {wait}s")
            time.sleep(wait)

def list_all_sets(session):
    sets = []
    page = 1
    while True:
        params = {"page": page, "pageSize": 250}
        resp = robust_get(session, f"{BASE}/sets", params)
        data = resp.json().get("data", [])
        sets.extend(data)
        sleep_with_progress(INTER_REQUEST_DELAY)
        if len(data) < 250:
            break
        page += 1
    return sets

def progress_load(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_sets": [], "in_progress_set": None, "exported_cards": 0}

def progress_save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def write_csv(out_path, rows):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        else:
            writer = csv.writer(f); writer.writerow([])

def fetch_set_cards(session, set_id: str, delay_seconds: float):
    all_rows = []
    page = 1
    while True:
        params = {
            "q": f"set.id:{set_id}",
            "page": page,
            "pageSize": FIXED_PAGE_SIZE,
            "select": ",".join(CARD_FIELDS),
        }
        resp = robust_get(session, f"{BASE}/cards", params)
        payload = resp.json()
        data = payload.get("data", [])
        for c in data:
            all_rows.append(flatten_card(c))
        sleep_with_progress(delay_seconds)
        if len(data) < FIXED_PAGE_SIZE:
            break
        page += 1
    return all_rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api_key", required=True)
    ap.add_argument("--outdir", default="data")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    progress_path = os.path.join(args.outdir, "progress.json")
    session = make_session(args.api_key)

    print("[*] Discovering all sets... (this may take a while)")
    sets = list_all_sets(session)
    print(f"[*] Found {len(sets)} sets total")

    by_series = {}
    for s in sets:
        series = s.get("series") or "Unknown"
        by_series.setdefault(series, []).append(s)

    manifest = []
    for series, lst in sorted(by_series.items()):
        for s in lst:
            manifest.append({
                "series": series,
                "set_id": s.get("id"),
                "set_name": s.get("name"),
                "releaseDate": s.get("releaseDate"),
                "printedTotal": s.get("printedTotal"),
                "total": s.get("total"),
                "ptcgoCode": s.get("ptcgoCode"),
            })
    manifest_path = os.path.join(args.outdir, "sets_manifest_all_series.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[*] Wrote manifest: {manifest_path}")

    prog = progress_load(progress_path)
    completed = set(prog.get("completed_sets", []))

    for series, lst in sorted(by_series.items()):
        series_slug = sanitize(series.lower())
        series_dir = os.path.join(args.outdir, series_slug)
        os.makedirs(series_dir, exist_ok=True)

        for s in sorted(lst, key=lambda x: (x.get("releaseDate") or "" , x.get("id") or "")):
            sid = s.get("id")
            sname = s.get("name") or "unknown_set"
            if not sid:
                continue
            if sid in completed:
                print(f"[skip] {sid} already completed")
                continue

            set_file = os.path.join(series_dir, f"{sid}_{sanitize(sname)}.csv")
            print(f"[*] Exporting set {sid} — {sname} -> {set_file}")
            prog["in_progress_set"] = sid
            progress_save(progress_path, prog)

            rows = fetch_set_cards(session, sid, INTER_REQUEST_DELAY)
            write_csv(set_file, rows)
            print(f"[done] {sid}: {len(rows)} cards")

            completed.add(sid)
            prog["completed_sets"] = sorted(list(completed))
            prog["in_progress_set"] = None
            prog["exported_cards"] = prog.get("exported_cards", 0) + len(rows)
            progress_save(progress_path, prog)

    print("[*] All sets processed.")

if __name__ == "__main__":
    main()
