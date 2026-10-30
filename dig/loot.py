"""Pure loot-roll rules for Dig (no Redbot dependencies)."""

from dataclasses import dataclass
import random
from typing import Dict

# Sale prices use the Royal Ribbit Reserve's existing Ribbucks economy.
SELL_PRICES = {"gold_ore": 55, "diamond": 160, "drug_stash": 95}
NAMES = {
    "gold_ore": "Gold ore",
    "diamond": "Diamond",
    "drug_stash": "Suspicious drug stash",
    "earthworm": "Earthworm",
    "golden_worm": "Golden worm",
}

# Conditional weights: these sum to 100, *after* the treasure-chest roll.
# Mishaps grant zero items and never remove credits or harm other cogs.
WEIGHTS = {
    "gold_ore": 34,
    "diamond": 10,
    "drug_stash": 20,
    "earthworm": 18,
    "mineshaft": 7,
    "bullfrog_den": 6,
    "sewer_pipe": 3,
    "cursed_idol": 2,
}

MISHAP_TEXT = {
    "mineshaft": [
        "Your shovel punches through an abandoned mineshaft. You tumble in and break a leg. No loot, just an extremely annoyed pond medic.",
        "The ground gives way to an old mineshaft. CRACK. You broke a leg and found absolutely nothing worth selling.",
    ],
    "bullfrog_den": [
        "You excavate a den of rabid bullfrogs. They swarm, bite your ankles, and drag your shovel into the darkness. Zero loot.",
        "A pack of rabid bullfrogs erupts from the mud like a tiny furious motorcycle gang. You escape with bite marks and nothing else.",
    ],
    "sewer_pipe": [
        "You hit a sewer pipe. The smell has lawyers. You flee empty-handed.",
        "A rotten sewer line explodes into your hole. The whole neighborhood hates you. Nothing recovered.",
    ],
    "cursed_idol": [
        "You uncover a cursed frog idol. It whispers your search history aloud. You immediately bury it again. No loot.",
        "You uncover a stone frog idol, and every tree starts judging you. You rebury it before anything gets worse. Nothing found.",
    ],
}

FOUND_TEXT = {
    "gold_ore": [
        "Your shovel clips something heavy: a chunk of GOLD ORE. The dirt is finally paying rent.",
        "The soil glitters. You dig out a lump of gold ore and hear a frog yell 'TAXABLE INCOME!'",
    ],
    "diamond": [
        "A DIAMOND sparkles inside the mud. Somewhere, an extremely jealous mole starts sobbing.",
        "You uncover a diamond. A nearby frog puts on sunglasses and pretends not to notice.",
    ],
    "drug_stash": [
        "A suspiciously wrapped DRUG STASH has been buried under the reeds. The underground pawn shop will buy it, no questions asked.",
        "You uncover an abandoned contraband stash. The marsh black market is interested, but the frogs deny knowing anything.",
    ],
    "earthworm": [
        "You find a squirming EARTHWORM. It's worthless to the bank, but a future fisherman may worship you.",
        "You pull an earthworm out of the mud. It stares at you like you interrupted an important meeting.",
    ],
}

# Future fishing integration: consuming golden_worm must result in MYTHIC fish.
BAIT_EFFECTS = {
    "earthworm": {"guaranteed_rarity": None},
    "golden_worm": {"guaranteed_rarity": "mythic"},
}


@dataclass(frozen=True)
class Outcome:
    kind: str
    loot: Dict[str, int]
    text: str


def roll_dig(chest_basis_points: int = 400, *, rng=None) -> Outcome:
    """Roll one dig. 400 basis points=4%; golden worm=2.5% of chests.

    A chest contains 2-4 of ONE valuable type (gold ore or diamonds),
    1-2 ordinary earthworms, plus a 2.5% chance of an extra golden worm.
    The caller must persist the outcome before presenting it as awarded.
    """
    if not (200 <= chest_basis_points <= 500):
        raise ValueError("Chest chance must be 2% to 5%.")
    rng = rng if rng is not None else random.SystemRandom()

    if rng.randrange(10000) < chest_basis_points:
        valuable = rng.choices(("gold_ore", "diamond"), weights=(3, 1), k=1)[0]
        quantity = rng.randint(2, 4)
        worms = rng.randint(1, 2)
        golden = rng.randrange(1000) < 25
        items = {valuable: quantity, "earthworm": worms}
        if golden:
            items["golden_worm"] = 1
        text = (
            "TREASURE CHEST! Your shovel smashes into an ancient lockbox. "
            "A frog in a velvet coat screams 'THAT'S MY RETIREMENT FUND!' and vanishes."
        )
        if golden:
            text += " A GOLDEN WORM wriggles out of the lining — future guaranteed MYTHIC fish bait!"
        return Outcome("chest", items, text)

    kind = rng.choices(tuple(WEIGHTS), weights=tuple(WEIGHTS.values()), k=1)[0]
    if kind in MISHAP_TEXT:
        return Outcome(kind, {}, rng.choice(MISHAP_TEXT[kind]))
    return Outcome(kind, {kind: 1}, rng.choice(FOUND_TEXT[kind]))


def inventory_sale(inventory: Dict[str, int], item: str, quantity: int):
    """Determine items/total without changing inventory. 'all' ignores unsellable bait."""
    if item == "all":
        selected = {key: int(inventory.get(key, 0)) for key in SELL_PRICES if int(inventory.get(key, 0)) > 0}
    else:
        if item not in SELL_PRICES or quantity < 1 or quantity > 100000:
            return {}, 0
        owned = int(inventory.get(item, 0))
        if owned < quantity:
            return {}, 0
        selected = {item: quantity}
    return selected, sum(SELL_PRICES[key] * count for key, count in selected.items())
