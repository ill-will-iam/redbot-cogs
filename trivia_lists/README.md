# Lily Pad Trivia Refresh

300 questions across 10 broad topics: 217 Easy and 83 Medium (editorial ratings).
Prepared on 2026-10-13 for Red-DiscordBot 3.5.24.

The questions use clear prompts, string-valued answers, alternate spellings and common name forms. There are no APIs, image hosts, new Python dependencies, dated news rounds, changing leaderboards or specialist patch/version questions. Recognizable classic films, music and history remain where the answer is stable.

## Quick installation: one combined list

1. Extract this ZIP.
2. Find `lists/lily_mix.yaml`.
3. As the bot owner, attach **that YAML file, not the ZIP**, to a Discord message containing:

```text
$triviaset custom upload
```

4. When the bot confirms that `lily_mix` was saved, play:

```text
$trivia lily_mix
```

No cog reload or bot restart is needed for a newly uploaded list.
The pack does not override your existing timing, score, payout or answer-reveal settings.

For a shorter command, use the existing Alias cog:

```text
$alias add quiz trivia lily_mix
$quiz
```

Use another alias name if `quiz` is already taken.

## Individual topics

Upload any individual YAML in `lists/` using `$triviaset custom upload` in the same way.

| Topic | File / command category | Questions |
| --- | --- | --- |
| General knowledge | `lily_general` | 30 |
| Science | `lily_science` | 30 |
| Geography | `lily_geography` | 30 |
| Animals | `lily_animals` | 30 |
| Food | `lily_food` | 30 |
| Music | `lily_music` | 30 |
| Movies | `lily_movies` | 30 |
| TV | `lily_tv` | 30 |
| Gaming | `lily_gaming` | 30 |
| Internet culture and basics | `lily_internet` | 30 |
| Combined mix | `lily_mix` | 300 |

Examples:

```text
$trivia lily_gaming
$trivia lily_movies lily_music
$trivia lily_mix
$trivia stop
$triviaset custom list
```

## What happens to old questions?

These lists are a curated alternative to the bundled collection. Starting `$trivia lily_mix` uses **only** the refreshed questions. It does not mix in bundled questions.

Red 3.5.24 rejects custom uploads using a bundled category's reserved name, so the pack uses `lily_` names. Existing built-in categories remain available through their old names; this download does not delete or patch files in your Python environment. Directly editing those packaged files is fragile because a Red update can restore them. Use `$quiz` or `$trivia lily_mix` as your refreshed default.

Existing custom lists can be removed individually with `$triviaset custom delete LIST_NAME` if you decide they are no longer wanted. That command removes custom lists, not built-in ones.

## Review and maintenance

- `QUESTION_REVIEW.md`: every question, difficulty rating and accepted answer.
- `questions.json`: structured editable question/answer catalog.
- `REVIEW_NOTES.md`: review scope, findings and source links.
- `lists/`: ten topic lists and their combined mix. The combined list contains the same 300 questions, not 300 additional questions.

The combined list prefixes questions with their topic. Individual lists use the same prompts without the prefix.

Validation checks all lists against Red's real trivia schema and parser, tests that every accepted answer is recognized by Red's answer-matching function, and checks question counts, duplicates, ZIP integrity and metadata. This is offline validation; upload and play a short round to confirm your running bot's setup.
