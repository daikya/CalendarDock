from contextlib import closing
from datetime import date, datetime

import pytest

from calendardock.database import create_database, open_database
from calendardock.migrations import (
    upgrade_database,
    upgrade_for_deletion,
)
from calendardock.repository import get_event_detail, list_events_for_day
from calendardock.search import search_events
from calendardock.service import (
    EventDraft,
    EventNotFoundError,
    create_event,
    delete_event,
    update_event,
)


PASSWORD = "test-password"


def draft():
    return EventDraft(
        subject="削除確認用",
        starts_at=datetime(2026, 10, 9, 9),
        ends_at=datetime(2026, 10, 9, 10),
        body="残しておく内容",
    )


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "calendar.db"
    create_database(path, PASSWORD)

    with closing(open_database(path, PASSWORD)) as connection:
        upgrade_database(connection)
        yield path, connection


def test_upgrade_preserves_data_and_defaults_to_active(database):
    _, connection = database
    event_id = create_event(connection, draft())
    before = dict(connection.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone())

    assert upgrade_for_deletion(connection) is True

    after = dict(connection.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone())

    assert after.pop("is_deleted") == 0
    assert after == before
    assert connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0] == 3
    assert upgrade_for_deletion(connection) is False


def test_deleted_event_is_hidden_but_data_is_preserved(database):
    _, connection = database
    upgrade_for_deletion(connection)
    event_id = create_event(connection, draft())

    before = dict(connection.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone())
    delete_event(connection, event_id)

    assert list_events_for_day(connection, date(2026, 10, 9)) == []
    assert search_events(connection, "削除確認用") == []
    assert get_event_detail(connection, event_id) is None

    after = dict(connection.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone())
    assert after["is_deleted"] == 1
    after["is_deleted"] = 0
    assert after == before


def test_delete_does_not_hide_other_events(database):
    _, connection = database
    upgrade_for_deletion(connection)
    first = create_event(connection, draft())
    second = create_event(connection, draft())

    delete_event(connection, first)

    assert [
        event.id
        for event in list_events_for_day(connection, date(2026, 10, 9))
    ] == [second]
    assert [event.id for event in search_events(
        connection, "削除確認用"
    )] == [second]


def test_deleted_state_survives_reopening(database):
    path, connection = database
    upgrade_for_deletion(connection)
    event_id = create_event(connection, draft())
    delete_event(connection, event_id)

    with closing(open_database(path, PASSWORD)) as reopened:
        assert get_event_detail(reopened, event_id) is None
        assert reopened.execute(
            "SELECT is_deleted FROM events WHERE id = ?", (event_id,)
        ).fetchone()[0] == 1


def test_missing_or_already_deleted_event_is_rejected(database):
    _, connection = database
    upgrade_for_deletion(connection)
    event_id = create_event(connection, draft())

    with pytest.raises(EventNotFoundError):
        delete_event(connection, -1)

    delete_event(connection, event_id)

    with pytest.raises(EventNotFoundError):
        delete_event(connection, event_id)

    assert not connection.in_transaction


def test_deleted_event_cannot_be_edited(database):
    _, connection = database
    upgrade_for_deletion(connection)
    event_id = create_event(connection, draft())
    delete_event(connection, event_id)

    with pytest.raises(EventNotFoundError):
        update_event(connection, event_id, draft())


def test_deletion_requires_version_three(database):
    _, connection = database
    event_id = create_event(connection, draft())

    with pytest.raises(ValueError, match="バージョン3"):
        delete_event(connection, event_id)

    assert get_event_detail(connection, event_id) is not None


def test_upgrade_rejects_existing_transaction(database):
    _, connection = database
    connection.execute("BEGIN")

    try:
        with pytest.raises(RuntimeError, match="トランザクション"):
            upgrade_for_deletion(connection)
        assert connection.in_transaction
    finally:
        connection.rollback()
