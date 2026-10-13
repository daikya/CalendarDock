import csv
import sqlite3
from contextlib import closing
from datetime import date, datetime

import pytest

from calendardock.database import (
    create_calendar_database,
    open_database,
)
from calendardock.importer import import_outlook_csv
from calendardock.repository import get_event_detail, list_events_for_day
from calendardock.search import search_events
from calendardock.service import (
    EventDraft,
    create_event,
    delete_event,
    update_event,
)


PASSWORD = "test-password"


def test_creates_current_empty_database(tmp_path):
    path = tmp_path / "data" / "calendar.db"
    create_calendar_database(path, PASSWORD)

    with closing(open_database(path, PASSWORD)) as connection:
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 3
        assert connection.execute(
            "SELECT count(*) FROM events"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM import_batches"
        ).fetchone()[0] == 0
        assert list_events_for_day(
            connection, date(2026, 10, 9)
        ) == []
        assert search_events(connection, "予定") == []
        assert connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []


def test_native_event_can_be_created_edited_and_deleted(tmp_path):
    path = tmp_path / "calendar.db"
    create_calendar_database(path, PASSWORD)

    with closing(open_database(path, PASSWORD)) as connection:
        event = EventDraft(
            subject="新規予定",
            starts_at=datetime(2026, 10, 9, 9),
            ends_at=datetime(2026, 10, 9, 10),
        )
        event_id = create_event(connection, event)

        assert get_event_detail(
            connection, event_id
        ).source_fields is None

        changed = EventDraft(
            subject="変更後",
            starts_at=event.starts_at,
            ends_at=event.ends_at,
        )
        update_event(connection, event_id, changed)
        assert search_events(connection, "変更後")[0].id == event_id

        delete_event(connection, event_id)
        assert get_event_detail(connection, event_id) is None
        assert search_events(connection, "変更後") == []


def test_csv_can_be_imported_into_current_database(tmp_path):
    path = tmp_path / "calendar.db"
    csv_path = tmp_path / "calendar.csv"
    row = {
        "件名": "取込予定",
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

    create_calendar_database(path, PASSWORD)

    with closing(open_database(path, PASSWORD)) as connection:
        result = import_outlook_csv(connection, csv_path)
        assert result.imported_count == 1

        summary = list_events_for_day(
            connection, date(2026, 10, 9)
        )[0]
        detail = get_event_detail(connection, summary.id)

        assert detail.subject == "取込予定"
        assert detail.source_fields == row
        assert detail.source_name == "calendar.csv"


def test_existing_database_is_not_overwritten(tmp_path):
    path = tmp_path / "calendar.db"
    create_calendar_database(path, PASSWORD)
    before = path.read_bytes()

    with pytest.raises(FileExistsError):
        create_calendar_database(path, "different-password")

    assert path.read_bytes() == before

    with closing(open_database(path, PASSWORD)) as connection:
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 3


def test_current_database_is_encrypted(tmp_path):
    path = tmp_path / "calendar.db"
    create_calendar_database(path, PASSWORD)

    with closing(sqlite3.connect(path)) as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(
                "SELECT count(*) FROM sqlite_master"
            ).fetchone()
