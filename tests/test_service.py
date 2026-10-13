import csv
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from calendardock.database import create_database, open_database
from calendardock.importer import import_outlook_csv
from calendardock.migrations import upgrade_database
from calendardock.repository import get_event_detail, list_events_for_day
from calendardock.search import search_events
from calendardock.service import (
    EventDraft,
    EventNotFoundError,
    create_event,
    update_event,
)


PASSWORD = "test-password"


def draft(**changes):
    value = EventDraft(
        subject="新規予定",
        starts_at=datetime(2026, 10, 9, 9),
        ends_at=datetime(2026, 10, 9, 10),
        location="自宅",
        body="1行目\n2行目",
        categories="個人",
    )
    return replace(value, **changes)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "calendar.db"
    create_database(path, PASSWORD)

    with closing(open_database(path, PASSWORD)) as connection:
        upgrade_database(connection)
        yield path, connection


def test_create_and_reopen_without_source_information(database):
    path, connection = database
    event_id = create_event(connection, draft())

    with closing(open_database(path, PASSWORD)) as reopened:
        detail = get_event_detail(reopened, event_id)

    assert detail.subject == "新規予定"
    assert detail.body == "1行目\n2行目"
    assert detail.location == "自宅"
    assert detail.categories == "個人"
    assert detail.source_row is None
    assert detail.source_fields is None
    assert detail.import_batch_id is None
    assert detail.source_name is None


def test_new_event_appears_in_day_list_and_search(database):
    _, connection = database
    event_id = create_event(connection, draft())

    assert list_events_for_day(
        connection, date(2026, 10, 9)
    )[0].id == event_id
    assert search_events(connection, "2行目")[0].id == event_id


def test_updates_native_event_and_moves_it_to_another_day(database):
    _, connection = database
    event_id = create_event(connection, draft())

    update_event(
        connection,
        event_id,
        draft(
            subject="変更後",
            starts_at=datetime(2026, 10, 10, 13),
            ends_at=datetime(2026, 10, 10, 14),
            body="変更した内容",
        ),
    )

    detail = get_event_detail(connection, event_id)
    assert detail.subject == "変更後"
    assert detail.body == "変更した内容"
    assert list_events_for_day(
        connection, date(2026, 10, 9)
    ) == []
    assert list_events_for_day(
        connection, date(2026, 10, 10)
    )[0].id == event_id


def test_edit_keeps_imported_source_information(tmp_path, database):
    _, connection = database
    csv_path = tmp_path / "calendar.csv"
    row = {
        "件名": "元の件名",
        "開始日": "2026/10/9",
        "開始時刻": "9:00:00",
        "終了日": "2026/10/9",
        "終了時刻": "10:00:00",
        "終日イベント": "False",
    }
    with csv_path.open("w", encoding="cp932", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    import_outlook_csv(connection, csv_path)
    event_id = list_events_for_day(
        connection, date(2026, 10, 9)
    )[0].id
    before = get_event_detail(connection, event_id)

    update_event(connection, event_id, draft(subject="変更後"))
    after = get_event_detail(connection, event_id)

    assert after.subject == "変更後"
    assert after.source_fields == before.source_fields == row
    assert after.source_row == before.source_row
    assert after.import_batch_id == before.import_batch_id
    assert after.source_name == before.source_name


def test_all_day_and_equal_time_events(database):
    _, connection = database
    all_day_id = create_event(
        connection,
        draft(
            all_day=True,
            starts_at=datetime(2026, 10, 9),
            ends_at=datetime(2026, 10, 10),
        ),
    )
    equal_time_id = create_event(
        connection,
        draft(ends_at=datetime(2026, 10, 9, 9)),
    )

    assert get_event_detail(connection, all_day_id).all_day is True
    assert get_event_detail(connection, equal_time_id) is not None
    assert list_events_for_day(
        connection, date(2026, 10, 10)
    ) == []


def test_invalid_input_does_not_create_or_change_events(database):
    _, connection = database
    event_id = create_event(connection, draft())
    before = get_event_detail(connection, event_id)

    invalid_drafts = [
        draft(ends_at=datetime(2026, 10, 9, 8)),
        draft(all_day=True),
        draft(
            all_day=True,
            starts_at=datetime(2026, 10, 9),
            ends_at=datetime(2026, 10, 9),
        ),
        draft(
            starts_at=datetime(2026, 10, 9, 9, tzinfo=timezone.utc)
        ),
        draft(starts_at=datetime(2026, 10, 9, 9, microsecond=1)),
    ]

    for value in invalid_drafts:
        with pytest.raises(ValueError):
            create_event(connection, value)
        with pytest.raises(ValueError):
            update_event(connection, event_id, value)

    assert connection.execute(
        "SELECT count(*) FROM events"
    ).fetchone()[0] == 1
    assert get_event_detail(connection, event_id) == before


def test_update_missing_event_does_not_create_one(database):
    _, connection = database

    with pytest.raises(EventNotFoundError):
        update_event(connection, -1, draft())

    assert connection.execute(
        "SELECT count(*) FROM events"
    ).fetchone()[0] == 0
    assert not connection.in_transaction


def test_rejects_save_inside_existing_transaction(database):
    _, connection = database
    connection.execute("BEGIN")

    try:
        with pytest.raises(RuntimeError, match="トランザクション"):
            create_event(connection, draft())
        assert connection.in_transaction
    finally:
        connection.rollback()
