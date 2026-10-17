"""Pure-stdlib tests for Snipe's retention, boundaries and clearing."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

MODULE_PATH = Path(__file__).resolve().parents[1] / "snipe" / "cache.py"
spec = importlib.util.spec_from_file_location("snipe_cache_for_tests", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
SnipedMessage = module.SnipedMessage
SnipeStore = module.SnipeStore


def make_entry(i, *, author_id=2, deleted_at=None):
    return SnipedMessage(
        message_id=i, author_id=author_id, author_name="name",
        content=f"message {i}", attachments=(), stickers=(),
        deleted_at=deleted_at or datetime.now(timezone.utc),
    )


def test_newest_first_and_maximum():
    store = SnipeStore(max_per_channel=3)
    for i in range(1, 6):
        store.remember(1, 2, make_entry(i))
    assert [x.message_id for x in store.recent(1, 2, 50)] == [5, 4, 3]
    assert store.get(1, 2, 2) is None


def test_channels_and_guilds_are_isolated():
    store = SnipeStore()
    store.remember(1, 10, make_entry(1))
    store.remember(1, 11, make_entry(2))
    store.remember(2, 10, make_entry(3))
    assert [x.message_id for x in store.recent(1, 10, 5)] == [1]
    assert store.clear(1, 10) == 1
    assert len(store.recent(1, 11, 5)) == 1
    assert store.clear(1) == 1
    assert [x.message_id for x in store.recent(2, 10, 5)] == [3]


def test_expired_messages_are_removed_on_access_and_not_recaptured():
    store = SnipeStore(retention_hours=24)
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    store.remember(1, 2, make_entry(1, deleted_at=old))
    assert store.recent(1, 2, 2) == []
    store.remember(1, 2, make_entry(2))
    store._channels[(1, 2)].append(make_entry(3, deleted_at=old))
    assert [x.message_id for x in store.recent(1, 2, 5)] == [2]


def test_red_user_deletion_purges_every_guild():
    store = SnipeStore()
    store.remember(1, 1, make_entry(10, author_id=111))
    store.remember(1, 1, make_entry(11, author_id=222))
    store.remember(2, 2, make_entry(12, author_id=111))
    assert store.delete_user(111) == 2
    assert [x.message_id for x in store.recent(1, 1, 5)] == [11]
    assert store.recent(2, 2, 5) == []
