# Redbot Cogs

A starter repository for custom [Red-DiscordBot](https://docs.discord.red/en/stable/) V3 cogs.

| Cog | Command | Purpose |
| --- | --- | --- |
| `hellocog` | `[p]coghello` | Confirms the repository's sample cog is installed and loaded. |
| `acrogame` | `[p]acro start` | Starts an acronym game using **3–5 random letters**, chat submissions, anonymous voting, and points. |

`[p]` means your bot's command prefix. If your prefix is `$`, use `$coghello`.

## Put this repository on GitHub

1. Sign in and open [GitHub's new repository page](https://github.com/new).
2. Name the repository `redbot-cogs` and add the description `Custom cogs for Red-DiscordBot.`
3. Choose **Public** if you want easy installation through Red's Downloader without Git authentication. Public repositories expose their files to everyone. A private repository needs Git authentication configured on the machine running Red.
4. Turn **Add README** on so the repository is initialized. Leave **Add .gitignore** set to **None**; a starter ignore file is included here.
5. Choose a license if you are ready to allow others to use your code under it. For an open source project, **MIT** is one common option. You can also leave the license unset and decide later.
6. Click **Create repository**.
7. Extract `redbot-cogs-starter.zip`. In the repository, choose **Add file → Upload files**.
8. Drag the **contents** of the extracted `redbot-cogs` folder into the uploader. Keep the `hellocog` folder intact. Upload `.gitignore`, `README.md`, and the root `info.json` beside that folder. Do not upload the ZIP or place everything inside another `redbot-cogs` folder.
9. If the uploader reports that `README.md` will be replaced, that is expected: this README replaces the initial generated one.
10. Enter the commit message `Add starter Red cog repository`, choose to commit directly to the default branch for this initial setup, and save the commit.
11. Confirm that the main repository page lists `hellocog`, `info.json`, and `README.md` at its top level. If `.gitignore` was skipped by your file picker, use **Add file → Create new file** to add it.
12. Edit the `author` list in each `info.json` if you prefer another author name.

A **commit** is a saved change in the repository's history.

## Install the sample cog

As the bot owner, run these commands in Discord. Replace `YOUR_USERNAME` with your GitHub username and `[p]` with your bot's prefix:

```text
[p]load downloader
[p]repo add redbot-cogs https://github.com/YOUR_USERNAME/redbot-cogs
[p]cog list redbot-cogs
[p]cog install redbot-cogs hellocog
[p]load hellocog
[p]coghello
```

The final command should reply:

> Your Red cog repository is working!

If Downloader requests confirmation, read its prompt and confirm to continue.

## Repository layout

Each cog package belongs directly in the repository root.

| Path | Purpose |
| --- | --- |
| `README.md` | Repository description and instructions. |
| `.gitignore` | Exclusions for local Git operations. |
| `info.json` | Repository metadata for Red. |
| `hellocog/__init__.py` | Loads the cog with the async `setup` function. |
| `hellocog/hellocog.py` | The cog's Python implementation. |
| `hellocog/info.json` | Cog metadata, requirements, and data statement. |

`acrogame/` is the acronym game package. Running `[p]acro start` chooses 3–5 random letters (not preset words). Players type their answers directly into the game channel; the bot stores and deletes those messages, then reveals anonymous submissions for voting after 30 seconds. Note that Discord messages may briefly appear before deletion.

## Add another cog

1. Create a folder at the repository root with a lowercase package name, such as `acro`.
2. Add `__init__.py` with an async `setup(bot)` function.
3. Add the cog's implementation file and its own `info.json`.
4. Describe any stored user data accurately and implement Red's data-deletion hook if needed.
5. Commit the files to GitHub.
6. Run `[p]repo update redbot-cogs`, then `[p]cog install redbot-cogs acro` and `[p]load acro`.

## Install AcroGame

```text
[p]repo update redbot-cogs
[p]cog install redbot-cogs acrogame
[p]load acrogame
[p]acro start
```

When the submissions are revealed, **type only the number** of the entry you want to vote for (for example, `1`, `2`, or `3`) directly into the same channel. Your vote message is deleted after it is captured, self-votes are rejected, and you can change your vote until voting ends. The older `$acro vote <number>` command still works, but is no longer needed. To begin a game, use `$acro start`; `$acro start KZP` supplies custom 3–5-letter prompts. The game awards leaderboard points, and optional Red economy credits can be configured with `$acro setcoins`.

## Update installed code

After committing changes to an already installed cog:

```text
[p]cog update hellocog
```

Follow Red's reload prompt if it appears. If you need to reload manually, run `[p]reload hellocog`.

`repo update` refreshes the repository clone; it does not update the installed cog copies. Use `cog update` for those.

## Keep configuration separate

Commit cog source files and documentation. Keep bot tokens, API keys, passwords, and Red's live data directory outside the repository. Git's ignore rules do not prevent you from manually uploading a file through GitHub's website.

## Validation

This starter's Python syntax, JSON metadata, package structure, and ZIP integrity were checked. It has not been run against a live Red instance; the `coghello` command above provides that check on your bot.

## References

- [Red's publishing guide](https://docs.discord.red/en/stable/guide_publish_cogs.html)
- [Red's cog creation guide](https://docs.discord.red/en/stable/guide_cog_creation.html)
- [Red's Downloader commands](https://docs.discord.red/en/stable/cog_guides/downloader.html)
- [GitHub repository creation](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
- [Uploading files to GitHub](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
