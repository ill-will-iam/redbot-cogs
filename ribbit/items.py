"""The Royal Ribbit Reserve's forage loot and cosmetic marketplace."""
import random

# Odds add to exactly 100: 85% edible catches, 15% setbacks.
# Edible catches go into inventory and only generate credits when sold.
# Mishaps never put anything in the inventory.
CATCHES = {
    "housefly": {"name": "Housefly", "weight": 23, "value": 6},
    "gnat": {"name": "Gnat", "weight": 15, "value": 3},
    "mosquito": {"name": "Mosquito", "weight": 12, "value": 9},
    "moth": {"name": "Moth", "weight": 10, "value": 15},
    "cricket": {"name": "Cricket", "weight": 8, "value": 25},
    "grasshopper": {"name": "Grasshopper", "weight": 7, "value": 40},
    "butterfly": {"name": "Butterfly", "weight": 4, "value": 70},
    "dragonfly": {"name": "Dragonfly", "weight": 3, "value": 110},
    "firefly": {"name": "Firefly", "weight": 2, "value": 175},
    "royal_moth": {"name": "Royal Moth", "weight": 1, "value": 350},
    "bee": {
        "name": "Bee", "weight": 5, "value": 0, "penalty": (5, 12),
        "incident": "You tried to munch a bee and got stung!",
    },
    "wasp": {
        "name": "Wasp", "weight": 4, "value": 0, "penalty": (10, 24),
        "incident": "A furious wasp chased you through the reeds and stung you!",
    },
    "fell_in_hole": {
        "name": "Fell in a Hole", "weight": 4, "value": 0, "penalty": (7, 20),
        "incident": "You missed a leap, fell in a hole, and had to pay for a rescue rope!",
    },
    "hit_by_car": {
        "name": "Hit by a Car", "weight": 2, "value": 0, "penalty": (25, 60),
        "incident": "You hopped across the road and got clipped by a passing car! The pond medic sent a bill.",
    },
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
