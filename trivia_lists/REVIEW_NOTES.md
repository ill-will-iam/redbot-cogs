# Review notes

## Scope

Reviewed the bundled trivia collection and implementation distributed with Red-DiscordBot 3.5.24, matching the version reported by fatboy. It contains 54 YAML topic lists and 14,655 question entries. This is a catalog and targeted content review, not a claim that every one of those entries was individually fact-checked. Unseen custom trivia lists on your VPS were not reviewed.

The resulting pack is newly curated for a broad adult social audience. It keeps recognizable, stable knowledge and excludes unusually specialist material and date-sensitive records. Difficulty is an editorial estimate, not a measurement of your members' abilities.

## Findings and editorial decisions

| Existing material | Finding | Pack decision |
| --- | --- | --- |
| `2015` and `2016` | Year-specific news, chart details and event recall have limited replay value as general trivia. | Exclude year-specific news categories. |
| `computers` | Mixes common computer knowledge with certification-style network-security configuration details. | Use approachable internet and computing basics; omit specialist configuration questions. |
| `hockey` | Includes undated all-time records and claims that can become wrong. | Omit moving sports records from this broad pack. |
| `hockey`: Russia-born NHL points leader | The bundled answer names Fedorov; NHL reporting records Ovechkin passing him in 2019. | Do not carry forward the stale question. |
| Ability/item lists and franchise deep dives | Categories such as Dota 2 abilities/items, League ultimates and very specific franchise history are often expert trivia. | Use widely recognizable gaming characters, mechanics and terms. |
| Image-based geography/Pokemon categories | Require external images and can be harder to read or dependent on host availability. | Use text-only questions. |
| Exact obscure dates, episode details and record totals | Can turn casual play into memorization exercises. | Prefer recognizable characters, places, ideas and basic terminology. |
| Classic media/history | Age alone does not make a stable fact incorrect. | Keep familiar examples, alongside more recent recognizable media. |

## Compatibility findings

The installed version supports custom YAML uploads. Its upload method rejects built-in category names, so the new names start with `lily_`. The new lists have no `CONFIG` overrides and preserve your settings. Its answer matching is case-insensitive and uses token/phrase matching rather than punctuation normalization; each list includes appropriate common spellings and aliases. Numeric answers remain quoted strings where YAML requires that.

A category selection only loads the lists you name. `$trivia lily_mix` therefore provides an updated question pool without replacing the core cog or deleting original packaged data.

## Primary sources consulted

These sources cross-check selected disputed, scientific and media details; the full catalog also contains established general-knowledge prompts.

- Red 3.5.24 trivia source and bundled lists: https://github.com/Cog-Creators/Red-DiscordBot/tree/3.5.24/redbot/cogs/trivia
- Red trivia commands: https://docs.discord.red/en/stable/cog_guides/trivia.html
- Red list-creation guide: https://docs.discord.red/en/stable/guide_trivia_list_creation.html
- NHL on Ovechkin passing Fedorov: https://www.nhl.com/news/ovechkin-proud-to-pass-fedorov-for-most-points-by-russia-born-player-304525240
- NASA planets: https://science.nasa.gov/solar-system/planets/
- NASA planetary temperatures: https://science.nasa.gov/solar-system/temperatures-across-our-solar-system/
- Smithsonian bats: https://www.si.edu/spotlight/bats/batfacts
- Smithsonian cephalopods: https://ocean.si.edu/ocean-life/invertebrates/octopuses-squids-and-relatives
- Pixar films: https://www.pixar.com/feature-films/
- Pixar Inside Out: https://www.pixar.com/inside-out
- Pixar Inside Out 2: https://www.pixar.com/inside-out-2
- Disney on Maya Hawke/Anxiety: https://thewaltdisneycompany.com/news/maya-hawke-inside-out-2-anxiety/
- Nintendo Animal Crossing: https://www.nintendo.com/en-ca/store/products/animal-crossing-new-horizons-switch/
- Nintendo Tom Nook: https://www.nintendo.com/us/amiibo/detail/tom-nook-amiibo-animal-crossing-series/
- Nintendo Isabelle: https://www.nintendo.com/en-ca/amiibo/detail/isabelle-amiibo-animal-crossing-series/
- Minecraft dimensions: https://help.minecraft.net/hc/en-us/articles/360046470431-Minecraft-Types-of-Biomes
- Tim Hortons history: https://www.news.timhortons.com/en/articles/tims-turns-60--may-17th--2024-marks-the-60th-anniversary-of-the-
- Louvre Mona Lisa: https://www.louvre.fr/en/explore/visitor-trails/the-louvre-s-masterpieces/a-superstar-and-a-wedding-crowd
