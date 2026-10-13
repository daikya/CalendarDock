import csv
from contextlib import closing

import pytest
from sqlcipher3 import dbapi2 as sqlcipher

import calendardock.migrations as migrations
from calendardock.database import create_database, open_database
from calendardock.importer import import_outlook_csv
from calendardock.migrations import upgrade_database


PASSWORD = "test-password"


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "calendar.db"
    create_database(path, PASSWORD)

    with closing(open_database(path, PASSWORD)) as connection:
        yield path, connection


def import_sample(tmp_path, connection):
    path = tmp_path / "calendar.csv"
    headers = [
        "件名", "開始日", "開始時刻", "終了日",
        "終了時刻", "終日イベント", "内容",
    ]
    row = {
        "件名": "予定",
        "開始日": "2026/10/9",
        "開始時刻": "9:00:00",
        "終了日": "2026/10/9",
        "終了時刻": "10:00:00",
        "終日イベント": "False",
        "内容": "1行目\n2行目",
    }

    with path.open("w", encoding="cp932", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerow(row)

    import_outlook_csv(connection, path)


def insert_native_event(connection):
    return connection.execute(
        """
        INSERT INTO events (
            subject, starts_at, ends_at, all_day,
            location, body, categories
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "新規予定",
            "2026-10-10T09:00:00",
            "2026-10-10T10:00:00",
            0,
            "",
            "新しいメモ",
            "",
        ),
    ).lastrowid


def test_preserves_events_and_import_history(tmp_path, database):
    _, connection = database
    import_sample(tmp_path, connection)

    before_events = [
        dict(row)
        for row in connection.execute("SELECT * FROM events")
    ]
    before_batches = [
        dict(row)
        for row in connection.execute("SELECT * FROM import_batches")
    ]

    assert upgrade_database(connection) is True

    assert [
        dict(row)
        for row in connection.execute("SELECT * FROM events")
    ] == before_events
    assert [
        dict(row)
        for row in connection.execute("SELECT * FROM import_batches")
    ] == before_batches
    assert connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0] == 2
    assert connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall() == []


def test_accepts_native_event_without_source_information(database):
    _, connection = database
    upgrade_database(connection)

    with connection:
        event_id = insert_native_event(connection)

    row = connection.execute(
        "SELECT * FROM events WHERE id = ?", (event_id,)
    ).fetchone()

    assert row["subject"] == "新規予定"
    assert row["source_row"] is None
    assert row["source_fields_json"] is None
    assert row["import_batch_id"] is None


def test_rejects_partial_source_information(database):
    _, connection = database
    upgrade_database(connection)

    with connection:
        event_id = insert_native_event(connection)

    with pytest.raises(sqlcipher.IntegrityError):
        with connection:
            connection.execute(
                "UPDATE events SET source_row = 2 WHERE id = ?",
                (event_id,),
            )

    assert connection.execute(
        "SELECT source_row FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()[0] is None


def test_second_upgrade_does_nothing(tmp_path, database):
    _, connection = database
    import_sample(tmp_path, connection)

    assert upgrade_database(connection) is True
    before = [
        dict(row)
        for row in connection.execute("SELECT * FROM events")
    ]

    assert upgrade_database(connection) is False
    assert [
        dict(row)
        for row in connection.execute("SELECT * FROM events")
    ] == before


def test_upgrades_unimported_database_and_reopens(database):
    path, connection = database

    assert upgrade_database(connection) is True

    with closing(open_database(path, PASSWORD)) as reopened:
        assert reopened.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 2
        assert reopened.execute(
            "SELECT count(*) FROM events"
        ).fetchone()[0] == 0


def test_rejects_existing_transaction(database):
    _, connection = database
    connection.execute("BEGIN")

    try:
        with pytest.raises(RuntimeError, match="トランザクション"):
            upgrade_database(connection)
        assert connection.in_transaction
    finally:
        connection.rollback()


def test_rejects_unsupported_version(database):
    _, connection = database
    with connection:
        connection.execute("PRAGMA user_version = 999")

    with pytest.raises(ValueError, match="バージョン"):
        upgrade_database(connection)

    assert connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0] == 999


def test_failure_rolls_back_schema_and_data(
    tmp_path, database, monkeypatch
):
    _, connection = database
    import_sample(tmp_path, connection)
    before = [
        dict(row)
        for row in connection.execute("SELECT * FROM events")
    ]
    original_rebuild = migrations._rebuild_events

    def fail_after_rebuild(connection):
        original_rebuild(connection)
        raise RuntimeError("更新失敗のテスト")

    monkeypatch.setattr(
        migrations, "_rebuild_events", fail_after_rebuild
    )

    with pytest.raises(RuntimeError, match="更新失敗"):
        upgrade_database(connection)

    assert connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0] == 1
    assert [
        dict(row)
        for row in connection.execute("SELECT * FROM events")
    ] == before

    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(events)")
    }
    assert columns["source_row"]["notnull"] == 1
    assert not connection.in_transaction
