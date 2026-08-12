#!/usr/bin/env python3
"""Generate a top-100 players seed JSON for Agentic Football Managers.

Run from repo root (or inside gaming/src/stack/agentic):

python gaming/src/stack/agentic/data/generate_players_seed.py

This will write `players_top100.json` in the same folder.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "players_top100.json"

base_prices = {5: 12000, 4: 7000, 3: 3000, 2: 1000, 1: 300}

players = []

# seed with a few named examples
players.append({"id": "p001", "name": "Top Andre", "rating": 92, "ranking": 1, "price": 12000, "wage": 700, "stars": 5, "stats": {"goals": 12, "assists": 8, "appearances": 15}})
players.append({"id": "p002", "name": "M. Mbappé (sample)", "rating": 91, "ranking": 2, "price": 11500, "wage": 680, "stars": 5, "stats": {"goals": 10, "assists": 7, "appearances": 14}})
players.append({"id": "p003", "name": "La Min (sample)", "rating": 90, "ranking": 3, "price": 11000, "wage": 650, "stars": 5, "stats": {"goals": 9, "assists": 10, "appearances": 16}})

# generate remaining players up to 100
for i in range(4, 101):
    pid = f"p{i:03d}"
    name = f"Player {i}"
    # simple rating curve
    rating = max(60, 92 - i)
    if rating >= 90:
        stars = 5
    elif rating >= 85:
        stars = 4
    elif rating >= 75:
        stars = 3
    elif rating >= 65:
        stars = 2
    else:
        stars = 1
    price = base_prices[stars] + (rating - (60 if stars == 1 else 0)) * 10
    wage = int(price * 0.06)
    stats = {"goals": max(0, (rating - 60) // 3), "assists": max(0, (rating - 70) // 4), "appearances": 5 + (rating - 60) // 2}
    players.append({
        "id": pid,
        "name": name,
        "rating": rating,
        "ranking": i,
        "price": price,
        "wage": wage,
        "stars": stars,
        "stats": stats,
    })

OUT.write_text(json.dumps(players, indent=2))
print(f"Wrote {OUT} with {len(players)} players")
