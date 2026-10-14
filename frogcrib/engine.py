"""Pure Python engine for standard two-player, 121-point cribbage.

Cards are stored as rank/suit strings, for example 'TH' is ten of hearts.
No Discord or bank code belongs in this module; it can be unit tested alone.
"""

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
import random
import time

RANKS = 'A23456789TJQK'
SUITS = 'CDHS'
SUIT_SYMBOLS = {'C': '♣', 'D': '♦', 'H': '♥', 'S': '♠'}
RANK_VALUES = {'A': 1, 'T': 10, 'J': 10, 'Q': 10, 'K': 10}
TARGET = 121


def rank(card):
    return RANKS.index(card[0]) + 1


def value(card):
    return RANK_VALUES.get(card[0], rank(card))


def display(card):
    return ('10' if card[0] == 'T' else card[0]) + SUIT_SYMBOLS[card[1]]


def ordered(cards):
    return sorted(cards, key=lambda c: (rank(c), SUITS.index(c[1])))


def hand_score(hand, starter, crib=False):
    """Return (points, breakdown) for exactly four hand/crib cards + starter."""
    if len(hand) != 4 or starter in hand or len(set(hand)) != 4:
        raise ValueError('Expected four unique cards and a distinct starter')
    cards = list(hand) + [starter]
    fifteen = sum(2 for n in range(2, 6) for subset in combinations(cards, n)
                  if sum(value(card) for card in subset) == 15)
    pairs = sum(2 for a, b in combinations(cards, 2) if rank(a) == rank(b))
    runs = 0
    for n in (5, 4, 3):
        ways = sum(1 for subset in combinations(cards, n)
                   if len(set(rank(card) for card in subset)) == n
                   and max(rank(card) for card in subset) - min(rank(card) for card in subset) == n - 1)
        if ways:
            runs = n * ways
            break
    flush = 0
    if len({card[1] for card in hand}) == 1:
        if starter[1] == hand[0][1]:
            flush = 5
        elif not crib:
            flush = 4
    nobs = int(any(card[0] == 'J' and card[1] == starter[1] for card in hand))
    breakdown = {'fifteens': fifteen, 'pairs': pairs, 'runs': runs,
                 'flush': flush, 'nobs': nobs}
    return sum(breakdown.values()), breakdown


def peg_score(sequence):
    """Return pegging points for the last played card, excluding exactly 31."""
    if not sequence:
        return 0
    points = 2 if sum(value(c) for c in sequence) == 15 else 0
    same = 1
    for card in reversed(sequence[:-1]):
        if rank(card) != rank(sequence[-1]):
            break
        same += 1
    points += {2: 2, 3: 6, 4: 12}.get(same, 0)
    for n in range(len(sequence), 2, -1):
        ranks = [rank(c) for c in sequence[-n:]]
        if len(set(ranks)) == n and max(ranks) - min(ranks) == n - 1:
            points += n
            break
    return points


@dataclass
class CribbageGame:
    players: tuple
    dealer: int
    scores: list = field(default_factory=lambda: [0, 0])
    round_number: int = 0
    phase: str = 'invited'
    hands: list = field(default_factory=lambda: [[], []])
    kept: list = field(default_factory=lambda: [[], []])
    crib: list = field(default_factory=list)
    deck: list = field(default_factory=list)
    starter: str = ''
    turn: int = 0
    count: int = 0
    segment: list = field(default_factory=list)
    last_player: int = -1
    winner: int = -1
    updated_at: float = field(default_factory=time.monotonic)

    def touch(self):
        self.updated_at = time.monotonic()

    def begin(self):
        if self.phase != 'invited':
            raise ValueError('This game has already started')
        return self._deal()

    def _deal(self):
        self.round_number += 1
        self.phase = 'discard'
        self.deck = [r + s for r in RANKS for s in SUITS]
        random.SystemRandom().shuffle(self.deck)
        self.hands = [ordered([self.deck.pop() for _ in range(6)]) for _ in range(2)]
        self.kept = [[], []]
        self.crib = []
        self.starter = ''
        self.turn = 1 - self.dealer
        self.count = 0
        self.segment = []
        self.last_player = -1
        self.touch()
        return [f'**Deal {self.round_number}** — <@{self.players[self.dealer]}> has the crib. '
                'Each player: check your DMs and use `$crib discard <number> <number>`.']

    def discard(self, player, first, second):
        if self.phase != 'discard' or player not in (0, 1):
            raise ValueError('Not in the discard phase')
        if self.kept[player]:
            raise ValueError('You already contributed to this crib')
        hand = self.hands[player]
        if first == second or not all(1 <= i <= 6 for i in (first, second)):
            raise ValueError('Choose two different card numbers from 1 to 6')
        selected = [hand[first - 1], hand[second - 1]]
        self.crib.extend(selected)
        self.hands[player] = ordered([card for i, card in enumerate(hand, 1) if i not in (first, second)])
        self.kept[player] = list(self.hands[player])
        self.touch()
        if not all(self.kept):
            return ['Two cards were put into the crib. Waiting for the other frog.']
        self.starter = self.deck.pop()
        self.phase = 'pegging'
        self.turn = 1 - self.dealer
        events = [f'**Starter card:** {display(self.starter)}. '
                  f'<@{self.players[self.turn]}> pegs first. Play with `$crib play <number>`.']
        if self.starter[0] == 'J':
            events.insert(0, f'**His heels!** Dealer gets 2 points for a starter Jack.')
            self._score(self.dealer, 2, events)
        return events

    def _score(self, player, points, events):
        if points <= 0 or self.phase == 'finished':
            return
        self.scores[player] += points
        if self.scores[player] >= TARGET:
            self.phase = 'finished'
            self.winner = player
            events.append(f'**121!** <@{self.players[player]}> wins '
                          f'**{self.scores[0]}–{self.scores[1]}**!')

    def can_play(self, player):
        return any(value(card) + self.count <= 31 for card in self.hands[player])

    def play(self, player, number):
        if self.phase != 'pegging' or player != self.turn:
            raise ValueError('It is not your pegging turn')
        hand = self.hands[player]
        if not 1 <= number <= len(hand):
            raise ValueError('Invalid card number. Check `$crib hand`.')
        card = hand[number - 1]
        if self.count + value(card) > 31:
            raise ValueError('That card would exceed 31. Choose another or use `$crib go`.')
        del hand[number - 1]
        self.segment.append(card)
        self.count += value(card)
        self.last_player = player
        self.touch()
        points = peg_score(self.segment) + (2 if self.count == 31 else 0)
        events = [f'<@{self.players[player]}> plays **{display(card)}** — count **{self.count}**'
                  + (f', **+{points} points**.' if points else '.')]
        self._score(player, points, events)
        if self.phase == 'finished':
            return events
        if self.count == 31:
            self._restart_segment(events, last=player, award_last=False)
        elif not any(self.hands):
            self._restart_segment(events, last=player, award_last=True)
        else:
            other = 1 - player
            if self.can_play(other):
                self.turn = other
            elif self.can_play(player):
                self.turn = player
                events.append(f'<@{self.players[other]}> has no legal play (go). '
                              f'<@{self.players[player]}> plays again.')
            else:
                self._restart_segment(events, last=player, award_last=True)
        return events

    def go(self, player):
        if self.phase != 'pegging' or player != self.turn:
            raise ValueError('It is not your pegging turn')
        if self.can_play(player):
            raise ValueError('You have a playable card; you cannot say go yet')
        self.touch()
        events = [f'<@{self.players[player]}> says **go**.']
        if self.can_play(1 - player):
            self.turn = 1 - player
        else:
            self._restart_segment(events, last=self.last_player, award_last=True)
        return events

    def _restart_segment(self, events, last, award_last):
        if award_last and last != -1:
            events.append(f'<@{self.players[last]}> gets **+1** for go/last card.')
            self._score(last, 1, events)
            if self.phase == 'finished':
                return
        self.count = 0
        self.segment = []
        self.last_player = -1
        if not any(self.hands):
            self._show(events)
            return
        lead = 1 - last if last != -1 else 1 - self.dealer
        self.turn = lead if self.hands[lead] else 1 - lead
        events.append(f'Count resets to **0**. <@{self.players[self.turn]}> leads.')

    def _show(self, events):
        self.phase = 'show'
        events.append(f'**Show time!** Starter: **{display(self.starter)}**.')
        pone = 1 - self.dealer
        for player, is_crib in ((pone, False), (self.dealer, False), (self.dealer, True)):
            hand = self.crib if is_crib else self.kept[player]
            points, breakdown = hand_score(hand, self.starter, crib=is_crib)
            what = 'crib' if is_crib else 'hand'
            cards = ', '.join(display(card) for card in ordered(hand))
            parts = ', '.join(f'{k} {v}' for k, v in breakdown.items() if v)
            events.append(f'<@{self.players[player]}> **{what}** [{cards}]: '
                          f'**{points} points** ({parts or "no points"}).')
            self._score(player, points, events)
            if self.phase == 'finished':
                return
        events.append(f'**Board:** {self.scores[0]}–{self.scores[1]}. Next deal!')
        self.dealer = 1 - self.dealer
        events.extend(self._deal())

    def board(self):
        return (f'**Frog Cribbage — Deal {self.round_number}**\n'
                f'<@{self.players[0]}>: **{self.scores[0]}/121** | '
                f'<@{self.players[1]}>: **{self.scores[1]}/121**\n'
                f'Dealer: <@{self.players[self.dealer]}> | Stage: **{self.phase}**'
                + (f' | Count: **{self.count}/31** | Turn: <@{self.players[self.turn]}>'
                   if self.phase == 'pegging' else '')
                + (f' | Starter: {display(self.starter)}' if self.starter else ''))
