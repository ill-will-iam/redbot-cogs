"""Small bounded in-memory store for recently deleted Discord messages."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SnipedMessage:
    message_id: int
    author_id: int
    author_name: str
    content: str
    attachments: Tuple[Tuple[str, str], ...]
    stickers: Tuple[str, ...]
    deleted_at: datetime


class SnipeStore:
    """Keep the newest messages first, isolated by guild and channel."""

    def __init__(self, max_per_channel: int = 50, retention_hours: int = 24):
        self.max_per_channel = max_per_channel
        self.retention = timedelta(hours=retention_hours)
        self._channels: Dict[Tuple[int, int], Deque[SnipedMessage]] = {}

    def _prune(self, key: Tuple[int, int], now: Optional[datetime] = None) -> None:
        entries = self._channels.get(key)
        if entries is None:
            return
        if now is None:
            now = datetime.now(timezone.utc)
        cutoff = now - self.retention
        current = deque(
            (entry for entry in entries if entry.deleted_at > cutoff),
            maxlen=self.max_per_channel,
        )
        if current:
            self._channels[key] = current
        else:
            self._channels.pop(key, None)

    def remember(self, guild_id: int, channel_id: int, entry: SnipedMessage) -> None:
        key = (guild_id, channel_id)
        self._prune(key)
        if entry.deleted_at <= datetime.now(timezone.utc) - self.retention:
            return
        self._channels.setdefault(key, deque(maxlen=self.max_per_channel)).appendleft(entry)

    def recent(self, guild_id: int, channel_id: int, count: int) -> List[SnipedMessage]:
        key = (guild_id, channel_id)
        self._prune(key)
        return list(self._channels.get(key, ()))[:count]

    def get(self, guild_id: int, channel_id: int, message_id: int) -> Optional[SnipedMessage]:
        key = (guild_id, channel_id)
        self._prune(key)
        return next(
            (entry for entry in self._channels.get(key, ()) if entry.message_id == message_id),
            None,
        )

    def clear(self, guild_id: int, channel_id: Optional[int] = None) -> int:
        keys = [
            key for key in self._channels
            if key[0] == guild_id and (channel_id is None or key[1] == channel_id)
        ]
        count = 0
        for key in keys:
            count += len(self._channels.pop(key))
        return count

    def delete_user(self, user_id: int) -> int:
        """Forget all cached data belonging to a user across all guilds."""
        removed = 0
        for key, entries in list(self._channels.items()):
            filtered = [entry for entry in entries if entry.author_id != user_id]
            removed += len(entries) - len(filtered)
            if filtered:
                self._channels[key] = deque(filtered, maxlen=self.max_per_channel)
            else:
                del self._channels[key]
        return removed
