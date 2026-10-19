"""Private, persistent guild management checklists and memos for Red-DiscordBot."""

from __future__ import annotations

from datetime import date, datetime, timezone
import re
from typing import List, Optional, Tuple

import discord
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import pagify

BOARD_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,23}\Z")
PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
MAX_TASKS = 300
MAX_BOARDS = 20
MAX_MEMOS = 100
PAGE_SIZE = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def clean_text(text: str, limit: int) -> Optional[str]:
    cleaned = " ".join(text.split()).strip()
    return cleaned if 0 < len(cleaned) <= limit else None


def board_key(name: str) -> Optional[str]:
    name = name.strip()
    return name.lower() if BOARD_PATTERN.fullmatch(name) else None


def safe(text: str) -> str:
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text))


def task_sort(task: dict) -> tuple:
    return (
        bool(task["done"]),
        PRIORITY_ORDER.get(task["priority"], 2),
        task.get("due") or "9999-12-31",
        task["id"],
    )


def locate_task(store: dict, task_id: int) -> Tuple[Optional[str], Optional[dict]]:
    for key, board in store["boards"].items():
        for task in board["tasks"]:
            if task["id"] == task_id:
                return key, task
    return None, None


class Notes(commands.Cog):
    """Staff-only server to-do lists and short management notes."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=829741065203, force_registration=True)
        self.config.register_guild(
            store={
                "next_task_id": 1,
                "next_memo_id": 1,
                "boards": {"general": {"name": "general", "tasks": []}},
                "memos": [],
            }
        )

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Recheck permissions for every nested command, not only the parent group."""
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return False
        if ctx.author.guild_permissions.manage_guild:
            return True
        return await ctx.bot.is_admin(ctx.author) or await ctx.bot.is_owner(ctx.author)

    async def _say(self, ctx: commands.Context, content: str):
        for page in pagify(content, page_length=1800):
            await ctx.send(page, allowed_mentions=discord.AllowedMentions.none())

    async def _render_board(self, ctx: commands.Context, key: str, page: int):
        store = await self.config.guild(ctx.guild).store()
        board = store["boards"].get(key)
        if board is None:
            return await self._say(ctx, "No list by that name. Use `{}notes boards`.".format(ctx.clean_prefix))
        tasks = sorted(board["tasks"], key=task_sort)
        await self._render_tasks(ctx, tasks, f"List: {board['name']}", page)

    async def _render_tasks(self, ctx: commands.Context, tasks: List[dict], label: str, page: int):
        if page < 1:
            return await self._say(ctx, "Page must be 1 or greater.")
        pages = max(1, (len(tasks) + PAGE_SIZE - 1) // PAGE_SIZE)
        if page > pages:
            return await self._say(ctx, f"There are only {pages} pages.")
        open_count = sum(not task["done"] for task in tasks)
        items = tasks[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        lines = [f"**{safe(label)}** — {open_count} open / {len(tasks)} total — page {page}/{pages}"]
        for task in items:
            check = "[x]" if task["done"] else "[ ]"
            priority = task.get("priority", "normal")
            due = f" | due {task['due']}" if task.get("due") else ""
            if due and not task["done"] and task["due"] < datetime.now(timezone.utc).date().isoformat():
                due += " (OVERDUE)"
            assignee = f" | <@{task['assignee']}>" if task.get("assignee") else ""
            preview = task["text"][:100] + ("…" if len(task["text"]) > 100 else "")
            board_label = f" | {task['board']}" if label == "All lists" else ""
            lines.append(
                f"`#{task['id']}` {check} **{priority}**{due}{assignee}{board_label} — {safe(preview)}"
            )
        if not items:
            lines.append("*No tasks yet.*")
        lines.append(f"`{ctx.clean_prefix}notes add <task>` · `{ctx.clean_prefix}notes task <id>`")
        await self._say(ctx, "\n".join(lines))

    @commands.group(name="notes", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def notes(self, ctx: commands.Context):
        """Staff to-do lists. Run without arguments to view the general list."""
        await self._render_board(ctx, "general", 1)

    @notes.command(name="list")
    async def notes_list(self, ctx: commands.Context, page: int = 1):
        """View the general to-do list: notes list [page]."""
        await self._render_board(ctx, "general", page)

    @notes.command(name="show")
    async def notes_show(self, ctx: commands.Context, board: str, page: int = 1):
        """View a named list: notes show staff [page]."""
        key = board_key(board)
        if key is None:
            return await self._say(ctx, "List names use letters, numbers, `_`, `-` (max 24 chars).")
        await self._render_board(ctx, key, page)

    @notes.command(name="all")
    async def notes_all(self, ctx: commands.Context, page: int = 1):
        """Show tasks across all of this server's lists."""
        store = await self.config.guild(ctx.guild).store()
        tasks = []
        for key, board in store["boards"].items():
            tasks.extend({**task, "board": key} for task in board["tasks"])
        await self._render_tasks(ctx, sorted(tasks, key=task_sort), "All lists", page)

    async def _add_task(self, ctx: commands.Context, board: str, text: str):
        key = board_key(board)
        task_text = clean_text(text, 400)
        if key is None:
            return await self._say(ctx, "Invalid list name. Use `{}notes boards`.".format(ctx.clean_prefix))
        if task_text is None:
            return await self._say(ctx, "Task text must be between 1 and 400 characters.")
        async with self.config.guild(ctx.guild).store() as store:
            if key not in store["boards"]:
                message = f"List `{key}` does not exist. Create it with `{ctx.clean_prefix}notes board create {key}`."
            elif sum(len(b["tasks"]) for b in store["boards"].values()) >= MAX_TASKS:
                message = f"This server has reached its limit of {MAX_TASKS} tasks."
            else:
                task_id = store["next_task_id"]
                store["next_task_id"] += 1
                store["boards"][key]["tasks"].append(
                    {
                        "id": task_id,
                        "text": task_text,
                        "priority": "normal",
                        "due": None,
                        "assignee": None,
                        "done": False,
                        "created_by": ctx.author.id,
                        "created_at": utc_now(),
                        "completed_by": None,
                        "completed_at": None,
                    }
                )
                message = f"Added task `#{task_id}` to **{key}**: {safe(task_text)}"
        await self._say(ctx, message)

    @notes.command(name="add")
    async def notes_add(self, ctx: commands.Context, *, text: str):
        """Add a task to general: notes add Fix channel permissions."""
        await self._add_task(ctx, "general", text)

    @notes.command(name="addto")
    async def notes_addto(self, ctx: commands.Context, board: str, *, text: str):
        """Add to a named list: notes addto staff Review moderator applications."""
        await self._add_task(ctx, board, text)

    @notes.command(name="task")
    async def notes_task(self, ctx: commands.Context, task_id: int):
        """See full task details by its permanent ID."""
        store = await self.config.guild(ctx.guild).store()
        key, task = locate_task(store, task_id)
        if task is None:
            return await self._say(ctx, f"Task `#{task_id}` was not found.")
        info = [
            f"**Task #{task_id}** — {'Done' if task['done'] else 'Open'} — list **{key}**",
            safe(task["text"]),
            f"Priority: **{task['priority']}** | Due: {task.get('due') or 'none'}",
            f"Assigned: {('<@' + str(task['assignee']) + '>') if task.get('assignee') else 'nobody'}",
            f"Created: {task['created_at']}",
        ]
        if task.get("completed_at"):
            info.append(f"Completed: {task['completed_at']}")
        await self._say(ctx, "\n".join(info))

    async def _set_completion(self, ctx: commands.Context, task_id: int, completed: bool):
        async with self.config.guild(ctx.guild).store() as store:
            _, task = locate_task(store, task_id)
            if task is None:
                message = f"Task `#{task_id}` was not found."
            elif task["done"] == completed:
                message = f"Task `#{task_id}` is already {'done' if completed else 'open'}."
            else:
                task["done"] = completed
                task["completed_by"] = ctx.author.id if completed else None
                task["completed_at"] = utc_now() if completed else None
                message = f"Task `#{task_id}` marked {'complete' if completed else 'open again'}."
        await self._say(ctx, message)

    @notes.command(name="done")
    async def notes_done(self, ctx: commands.Context, task_id: int):
        """Mark a task complete: notes done 3."""
        await self._set_completion(ctx, task_id, True)

    @notes.command(name="undo", aliases=["reopen"])
    async def notes_undo(self, ctx: commands.Context, task_id: int):
        """Reopen a completed task: notes undo 3."""
        await self._set_completion(ctx, task_id, False)

    @notes.command(name="edit")
    async def notes_edit(self, ctx: commands.Context, task_id: int, *, text: str):
        """Change a task's text: notes edit 3 Review all staff permissions."""
        task_text = clean_text(text, 400)
        if task_text is None:
            return await self._say(ctx, "Task text must be between 1 and 400 characters.")
        async with self.config.guild(ctx.guild).store() as store:
            _, task = locate_task(store, task_id)
            if task is None:
                message = f"Task `#{task_id}` was not found."
            else:
                task["text"] = task_text
                message = f"Updated task `#{task_id}`: {safe(task_text)}"
        await self._say(ctx, message)

    @notes.command(name="remove", aliases=["delete"])
    async def notes_remove(self, ctx: commands.Context, task_id: int):
        """Permanently delete a task: notes remove 3."""
        async with self.config.guild(ctx.guild).store() as store:
            key, task = locate_task(store, task_id)
            if task is None:
                message = f"Task `#{task_id}` was not found."
            else:
                store["boards"][key]["tasks"].remove(task)
                message = f"Deleted task `#{task_id}` from **{key}**."
        await self._say(ctx, message)

    @notes.command(name="priority")
    async def notes_priority(self, ctx: commands.Context, task_id: int, priority: str):
        """Set priority: notes priority 3 urgent|high|normal|low."""
        priority = priority.lower()
        if priority not in PRIORITY_ORDER:
            return await self._say(ctx, "Use one of: `urgent`, `high`, `normal`, `low`.")
        async with self.config.guild(ctx.guild).store() as store:
            _, task = locate_task(store, task_id)
            if task is None:
                message = f"Task `#{task_id}` was not found."
            else:
                task["priority"] = priority
                message = f"Task `#{task_id}` priority set to **{priority}**."
        await self._say(ctx, message)

    @notes.command(name="due")
    async def notes_due(self, ctx: commands.Context, task_id: int, due: str):
        """Set a UTC due date: notes due 3 2026-10-25; use clear to remove it."""
        if due.lower() == "clear":
            due_value = None
        else:
            try:
                due_value = date.fromisoformat(due).isoformat()
            except ValueError:
                return await self._say(ctx, "Use `YYYY-MM-DD` or `clear`.")
        async with self.config.guild(ctx.guild).store() as store:
            _, task = locate_task(store, task_id)
            if task is None:
                message = f"Task `#{task_id}` was not found."
            else:
                task["due"] = due_value
                message = f"Task `#{task_id}` due date: **{due_value or 'none'}**."
        await self._say(ctx, message)

    @notes.command(name="assign")
    async def notes_assign(self, ctx: commands.Context, task_id: int, member: discord.Member):
        """Assign a task to a member: notes assign 3 @Moderator."""
        async with self.config.guild(ctx.guild).store() as store:
            _, task = locate_task(store, task_id)
            if task is None:
                message = f"Task `#{task_id}` was not found."
            else:
                task["assignee"] = member.id
                message = f"Task `#{task_id}` assigned to {safe(member.display_name)}."
        await self._say(ctx, message)

    @notes.command(name="unassign")
    async def notes_unassign(self, ctx: commands.Context, task_id: int):
        """Remove the assigned member from a task."""
        async with self.config.guild(ctx.guild).store() as store:
            _, task = locate_task(store, task_id)
            if task is None:
                message = f"Task `#{task_id}` was not found."
            else:
                task["assignee"] = None
                message = f"Task `#{task_id}` is unassigned."
        await self._say(ctx, message)

    @notes.command(name="move")
    async def notes_move(self, ctx: commands.Context, task_id: int, board: str):
        """Move a task to another list: notes move 3 moderation."""
        key = board_key(board)
        if key is None:
            return await self._say(ctx, "List names use letters, numbers, `_`, `-` (max 24 chars).")
        async with self.config.guild(ctx.guild).store() as store:
            old, task = locate_task(store, task_id)
            if task is None:
                message = f"Task `#{task_id}` was not found."
            elif key not in store["boards"]:
                message = f"List `{key}` does not exist."
            elif old == key:
                message = f"Task `#{task_id}` is already in **{key}**."
            else:
                store["boards"][old]["tasks"].remove(task)
                store["boards"][key]["tasks"].append(task)
                message = f"Moved task `#{task_id}` from **{old}** to **{key}**."
        await self._say(ctx, message)

    @notes.command(name="boards")
    async def notes_boards(self, ctx: commands.Context):
        """Show lists and open task counts."""
        store = await self.config.guild(ctx.guild).store()
        lines = ["**Server management lists**"]
        for key, board in sorted(store["boards"].items()):
            count = sum(not task["done"] for task in board["tasks"])
            lines.append(f"• `{key}` — {count} open / {len(board['tasks'])} total")
        lines.append(f"Create: `{ctx.clean_prefix}notes board create moderation`")
        await self._say(ctx, "\n".join(lines))

    @notes.group(name="board", invoke_without_command=True)
    async def notes_board(self, ctx: commands.Context):
        """Create, rename, or delete named lists."""
        await self._say(ctx, f"Use `{ctx.clean_prefix}help notes board` for list management.")

    @notes_board.command(name="create")
    async def board_create(self, ctx: commands.Context, name: str):
        """Create a list: notes board create moderation."""
        key = board_key(name)
        if key is None:
            return await self._say(ctx, "List names must start with a letter and use letters, numbers, `_`, `-` (max 24 chars).")
        async with self.config.guild(ctx.guild).store() as store:
            if key in store["boards"]:
                message = f"List `{key}` already exists."
            elif len(store["boards"]) >= MAX_BOARDS:
                message = f"Maximum {MAX_BOARDS} lists per server."
            else:
                store["boards"][key] = {"name": key, "tasks": []}
                message = f"Created list **{key}**. Add items with `{ctx.clean_prefix}notes addto {key} <task>`."
        await self._say(ctx, message)

    @notes_board.command(name="rename")
    async def board_rename(self, ctx: commands.Context, current: str, new: str):
        """Rename a list: notes board rename staff staffing."""
        old, key = board_key(current), board_key(new)
        if old is None or key is None:
            return await self._say(ctx, "Both list names must start with a letter, max 24 characters.")
        async with self.config.guild(ctx.guild).store() as store:
            if old == "general":
                message = "The `general` list cannot be renamed."
            elif old not in store["boards"]:
                message = f"List `{old}` does not exist."
            elif key in store["boards"]:
                message = f"List `{key}` already exists."
            else:
                store["boards"][key] = store["boards"].pop(old)
                store["boards"][key]["name"] = key
                message = f"Renamed list **{old}** to **{key}**."
        await self._say(ctx, message)

    @notes_board.command(name="delete")
    async def board_delete(self, ctx: commands.Context, name: str):
        """Delete an EMPTY list (move/remove its tasks first)."""
        key = board_key(name)
        if key is None:
            return await self._say(ctx, "Invalid list name.")
        async with self.config.guild(ctx.guild).store() as store:
            if key == "general":
                message = "The `general` list cannot be deleted."
            elif key not in store["boards"]:
                message = f"List `{key}` does not exist."
            elif store["boards"][key]["tasks"]:
                message = "This list contains tasks. Move or remove them first; no tasks were deleted."
            else:
                del store["boards"][key]
                message = f"Deleted empty list **{key}**."
        await self._say(ctx, message)

    @notes.group(name="memo", invoke_without_command=True)
    async def notes_memo(self, ctx: commands.Context):
        """Short server management reference notes."""
        await self._say(ctx, f"Use `{ctx.clean_prefix}notes memo list` or `{ctx.clean_prefix}help notes memo`.")

    @notes_memo.command(name="add")
    async def memo_add(self, ctx: commands.Context, *, text: str):
        """Save a reference note: notes memo add We review appeals weekly."""
        memo_text = clean_text(text, 1000)
        if memo_text is None:
            return await self._say(ctx, "Memo text must be between 1 and 1000 characters.")
        async with self.config.guild(ctx.guild).store() as store:
            if len(store["memos"]) >= MAX_MEMOS:
                message = f"Limit reached: {MAX_MEMOS} memos per server."
            else:
                memo_id = store["next_memo_id"]
                store["next_memo_id"] += 1
                store["memos"].append(
                    {"id": memo_id, "text": memo_text, "by": ctx.author.id, "created_at": utc_now()}
                )
                message = f"Saved memo `#{memo_id}`: {safe(memo_text[:180])}"
        await self._say(ctx, message)

    @notes_memo.command(name="list")
    async def memo_list(self, ctx: commands.Context, page: int = 1):
        """List saved memos: notes memo list [page]."""
        store = await self.config.guild(ctx.guild).store()
        memos = store["memos"]
        pages = max(1, (len(memos) + PAGE_SIZE - 1) // PAGE_SIZE)
        if not 1 <= page <= pages:
            return await self._say(ctx, f"Page must be between 1 and {pages}.")
        subset = memos[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        lines = [f"**Server memos** — {len(memos)} total — page {page}/{pages}"]
        for memo in subset:
            preview = memo["text"][:115] + ("…" if len(memo["text"]) > 115 else "")
            lines.append(f"`#{memo['id']}` {safe(preview)}")
        if not subset:
            lines.append("*No memos saved.*")
        lines.append(f"`{ctx.clean_prefix}notes memo show <id>`")
        await self._say(ctx, "\n".join(lines))

    @notes_memo.command(name="show")
    async def memo_show(self, ctx: commands.Context, memo_id: int):
        """Read the complete saved memo."""
        store = await self.config.guild(ctx.guild).store()
        memo = next((m for m in store["memos"] if m["id"] == memo_id), None)
        if memo is None:
            return await self._say(ctx, f"Memo `#{memo_id}` was not found.")
        await self._say(ctx, f"**Memo #{memo_id}** — {memo['created_at']}\n{safe(memo['text'])}")

    @notes_memo.command(name="delete", aliases=["remove"])
    async def memo_delete(self, ctx: commands.Context, memo_id: int):
        """Permanently delete a memo."""
        async with self.config.guild(ctx.guild).store() as store:
            memo = next((m for m in store["memos"] if m["id"] == memo_id), None)
            if memo is None:
                message = f"Memo `#{memo_id}` was not found."
            else:
                store["memos"].remove(memo)
                message = f"Deleted memo `#{memo_id}`."
        await self._say(ctx, message)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Disassociate a user from staff notes, preserving operational checklist data."""
        guilds = await self.config.all_guilds()
        for guild_id in guilds:
            async with self.config.guild_from_id(guild_id).store() as store:
                for board in store["boards"].values():
                    for task in board["tasks"]:
                        for field in ("created_by", "completed_by", "assignee"):
                            if task.get(field) == user_id:
                                task[field] = None
                for memo in store["memos"]:
                    if memo.get("by") == user_id:
                        memo["by"] = None
