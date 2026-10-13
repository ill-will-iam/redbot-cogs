"""The Royal Ribbit Reserve's forage loot and cosmetic marketplace."""
import random

# Probability weights intentionally add up to 100.
CATCHES = {
    "housefly": {"name": "Housefly", "weight": 26, "value": 10},
    "gnat": {"name": "Gnat", "weight": 18, "value": 4},
    "mosquito": {"name": "Mosquito", "weight": 14, "value": 8},
    "moth": {"name": "Moth", "weight": 12, "value": 18},
    "cricket": {"name": "Cricket", "weight": 9, "value": 25},
    "grasshopper": {"name": "Grasshopper", "weight": 8, "value": 35},
    "butterfly": {"name": "Butterfly", "weight": 5, "value": 55},
    "dragonfly": {"name": "Dragonfly", "weight": 3, "value": 90},
    "firefly": {"name": "Firefly", "weight": 2, "value": 125},
    "royal_moth": {"name": "Royal Moth", "weight": 1, "value": 280},
    "bee": {"name": "Bee", "weight": 1, "value": 0, "sting": (5, 15)},
    "wasp": {"name": "Wasp", "weight": 1, "value": 0, "sting": (15, 30)},
}

SHOP = {
    "lilypad_hat": {"name": "Lilypad Hat", "price": 250},
    "reed_flute": {"name": "Reed Flute", "price": 450},
    "moon_lily": {"name": "Moon Lily", "price": 800},
    "amber_tadpole": {"name": "Amber Tadpole", "price": 1500},
    "royal_lily": {"name": "Royal Lily", "price": 4000},
}

WORK = (
    "polished the Royal Ribbit Reserve's lily pads",
    "stood guard over the tadpole nursery",
    "repaired a bridge across the marsh",
    "organized a choir of croaking frogs",
    "delivered rush parcels by dragonfly",
    "counted the Reserve's emergency mosquito supply",
    "cleaned the pond's enchanted fountains",
)

def catch_random():
    names = list(CATCHES)
    return random.choices(names, weights=[CATCHES[k]["weight"] for k in names], k=1)[0]
