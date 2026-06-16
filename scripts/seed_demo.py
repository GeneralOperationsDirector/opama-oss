#!/usr/bin/env python3
"""Seed a running opama instance with a small demo collection.

Gives a fresh install something to look at: a handful of items across several
categories so the dashboard, Collections, and Portfolio views aren't empty.

Usage (stack must be running — `./opama.sh start`):

    python3 scripts/seed_demo.py
    API_BASE=http://localhost:6001 python3 scripts/seed_demo.py   # oss-test stack

Auth: with the default local auth provider the script signs in as (or creates)
a "demo" account. To seed an existing account instead, pass a bearer token:

    API_TOKEN=<token> python3 scripts/seed_demo.py

Idempotent: every seeded item is tagged "demo-seed"; the script exits without
writing if the account already has any such item. Uses only the stdlib.
"""

import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://localhost:6000").rstrip("/")
DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")  # passwordless by default
SEED_TAG = "demo-seed"

ITEMS = [
    {
        "name": "Seiko 5 SNK809",
        "category": "Watches",
        "condition": "Very Good",
        "purchase_price": 95.0,
        "estimated_value": 140.0,
        "description": "Automatic field watch, 37mm, black dial. Daily wearer.",
        "custom_fields": [
            {"key": "Movement", "value": "7S26 automatic"},
            {"key": "Year", "value": "2019"},
        ],
    },
    {
        "name": "Citizen Promaster Diver",
        "category": "Watches",
        "condition": "Excellent",
        "purchase_price": 250.0,
        "estimated_value": 320.0,
        "description": "Eco-Drive 200m diver on rubber strap. Full kit with box and papers.",
        "custom_fields": [{"key": "Movement", "value": "Eco-Drive E168"}],
    },
    {
        "name": "Moonrise Over the Harbour — limited print",
        "category": "Art",
        "condition": "Mint",
        "purchase_price": 180.0,
        "estimated_value": 260.0,
        "description": "Giclée print, edition 42/150, signed. Framed behind UV glass.",
        "custom_fields": [
            {"key": "Edition", "value": "42/150"},
            {"key": "Dimensions", "value": "60 × 40 cm"},
        ],
    },
    {
        "name": "Mid-century ceramic vase",
        "category": "Art",
        "condition": "Good",
        "purchase_price": 45.0,
        "estimated_value": 110.0,
        "description": "West German fat lava glaze, 1960s. Small chip on base rim.",
    },
    {
        "name": "Charizard — Base Set 4/102 (played)",
        "category": "Trading Cards",
        "condition": "Played",
        "purchase_price": 120.0,
        "estimated_value": 210.0,
        "description": "Unlimited print, holo. Edge wear, minor scratches on holo.",
        "custom_fields": [{"key": "Set", "value": "Base Set Unlimited"}],
    },
    {
        "name": "Pikachu — Jungle 60/64",
        "category": "Trading Cards",
        "condition": "Near Mint",
        "purchase_price": 8.0,
        "estimated_value": 15.0,
        "quantity": 3,
    },
    {
        "name": "1936 Buffalo Nickel",
        "category": "Coins",
        "condition": "Fine",
        "purchase_price": 4.0,
        "estimated_value": 7.5,
        "description": "Philadelphia mint, full horn partially visible.",
        "custom_fields": [{"key": "Mint mark", "value": "None (Philadelphia)"}],
    },
    {
        "name": "1oz Silver Maple Leaf 2023",
        "category": "Coins",
        "condition": "Brilliant Uncirculated",
        "purchase_price": 36.0,
        "estimated_value": 42.0,
        "quantity": 5,
        "description": "In original RCM capsule.",
    },
    {
        "name": "Kind of Blue — Miles Davis (1977 reissue)",
        "category": "Vinyl Records",
        "condition": "VG+",
        "purchase_price": 22.0,
        "estimated_value": 35.0,
        "description": "Columbia PC 8163. Sleeve has light ring wear.",
        "custom_fields": [{"key": "Pressing", "value": "1977 US reissue"}],
    },
    {
        "name": "Rumours — Fleetwood Mac (original 1977)",
        "category": "Vinyl Records",
        "condition": "VG",
        "purchase_price": 18.0,
        "estimated_value": 28.0,
    },
]


def request(method, path, token=None, body=None):
    req = urllib.request.Request(API_BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data=data, timeout=15) as res:
        return json.loads(res.read())


def get_token():
    token = os.environ.get("API_TOKEN")
    if token:
        return token, "API_TOKEN"

    config = request("GET", "/auth/config")
    if config.get("provider") != "local":
        sys.exit(
            "This instance uses Firebase auth — pass a bearer token via API_TOKEN "
            "instead (see docs/TESTING_GUIDE.md for how to obtain one)."
        )

    creds = {"username": DEMO_USERNAME, "password": DEMO_PASSWORD}
    try:
        out = request("POST", "/auth/login", body=creds)
        return out["token"], f"existing '{DEMO_USERNAME}' account"
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
    out = request("POST", "/auth/register", body={**creds, "display_name": "Demo"})
    return out["token"], f"new '{DEMO_USERNAME}' account"


def main():
    try:
        token, source = get_token()
    except urllib.error.URLError as exc:
        sys.exit(f"Cannot reach API at {API_BASE} ({exc.reason}). Is the stack running?")
    print(f"Authenticated via {source} against {API_BASE}")

    existing = request("GET", "/assets", token=token)
    if any(SEED_TAG in (a.get("tags") or "") for a in existing):
        print(f"Demo items already present (tag '{SEED_TAG}') — nothing to do.")
        return

    for item in ITEMS:
        created = request("POST", "/assets", token=token, body={**item, "tags": SEED_TAG})
        print(f"  + [{created['category']}] {created['name']}")

    ui_hint = " at http://localhost:5173" if API_BASE == "http://localhost:6000" else ""
    print(f"\nSeeded {len(ITEMS)} items. Open the dashboard{ui_hint} and sign in")
    if source != "API_TOKEN":
        print(f"as '{DEMO_USERNAME}' (no password) to explore the demo collection.")
    else:
        print("to explore the demo collection.")
    print(f"To remove later: delete items tagged '{SEED_TAG}' in Collections.")


if __name__ == "__main__":
    main()
