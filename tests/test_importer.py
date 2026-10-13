import csv
import json
from contextlib import closing

import pytest
from sqlcipher3 import dbapi2 as sqlcipher

from calendardock.database import create_database, open_database
from calendardock.importer import (
    AlreadyImportedError,
    import_outlook_csv,
)
from calendardock.outlook_csv import OutlookCsvError


PASSWORD = "test-password"

HEADERS = [
    "件名",
    "開始日",
    "開始時刻",
    "終了日",
    "終了時刻",
    "終日イベント",
    "場所",
    "内容",
    "分類",
    "優先度",
]


def make_row(**changes):
    row = {
        "件名": "予定",
        "開始日": "2026/10/9",
        "開始時刻": "9:00:00",
        "終了日": "2026/10/9",
        "終了時刻": "10:00:00",
        "終日イベント": "False",
        "場所": "自宅",
        "内容": "メモ",
        "分類": "",
        "優先度": "標準",
    }
    row.update(changes)
    return row


def write_csv(tmp_path, rows, name="calendar.csv", encoding="cp932"):
    path = tmp_path / name
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def connection(tmp_path):
    path = tmp_path / "calendar.db"
    create_database(path, PASSWORD)
    with closing(open_database(path, PASSWORD)) as connection:
        yield connection


def test_import_and_reopen(tmp_path):
    db_path = tmp_path / "calendar.db"
    csv_path = write_csv(tmp_path, [make_row()])
    create_database(db_path, PASSWORD)

    with closing(open_database(db_path, PASSWORD)) as connection:
        result = import_outlook_csv(connection, csv_path)

    assert result.imported_count == 1

    with closing(open_database(db_path, PASSWORD)) as connection:
        event = connection.execute(
            "SELECT * FROM events"
        ).fetchone()

        assert event["subject"] == "予定"
        assert event["starts_at"] == "2026-10-09T09:00:00"
        assert event["ends_at"] == "2026-10-09T10:00:00"
        assert event["all_day"] == 0
        assert event["location"] == "自宅"
        assert event["source_row"] == 2
        assert event["import_batch_id"] == result.batch_id

        batch = connection.execute(
            "SELECT * FROM import_batches"
        ).fetchone()
        assert batch["source_name"] == "calendar.csv"
        assert batch["event_count"] == 1


def test_preserves_original_fields_and_multiline_body(
    tmp_path, connection
):
    body = '1行目, "引用"\r\n2行目'
    row = make_row(内容=body, 優先度="高")
    path = write_csv(tmp_path, [row])

    import_outlook_csv(connection, path)

    event = connection.execute("SELECT * FROM events").fetchone()
    assert event["body"] == body
    assert json.loads(event["source_fields_json"]) == row


def test_preserves_duplicates_empty_subject_and_equal_times(
    tmp_path, connection
):
    row = make_row(件名="", 終了時刻="9:00:00")
    path = write_csv(tmp_path, [row, row])

    result = import_outlook_csv(connection, path)
    events = connection.execute(
        "SELECT * FROM events ORDER BY id"
    ).fetchall()

    assert result.imported_count == 2
    assert len(events) == 2
    assert [event["source_row"] for event in events] == [2, 3]
    assert all(event["subject"] == "" for event in events)
    assert all(
        event["starts_at"] == event["ends_at"] for event in events
    )


def test_preserves_all_day_end_date(tmp_path, connection):
    path = write_csv(
        tmp_path,
        [
            make_row(
                開始時刻="0:00:00",
                終了日="2026/10/10",
                終了時刻="0:00:00",
                終日イベント="True",
            )
        ],
    )

    import_outlook_csv(connection, path)
    event = connection.execute("SELECT * FROM events").fetchone()

    assert event["all_day"] == 1
    assert event["starts_at"] == "2026-10-09T00:00:00"
    assert event["ends_at"] == "2026-10-10T00:00:00"


def test_rejects_same_data_with_different_name_and_encoding(
    tmp_path, connection
):
    rows = [make_row()]
    first = write_csv(tmp_path, rows)
    second = write_csv(
        tmp_path, rows, name="copy.csv", encoding="utf-8-sig"
    )
    import_outlook_csv(connection, first)

    with pytest.raises(AlreadyImportedError):
        import_outlook_csv(connection, second)

    assert connection.execute(
        "SELECT count(*) FROM events"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT count(*) FROM import_batches"
    ).fetchone()[0] == 1


def test_imports_different_data_as_another_batch(tmp_path, connection):
    first = write_csv(tmp_path, [make_row()], name="first.csv")
    second = write_csv(
        tmp_path, [make_row(件名="別の予定")], name="second.csv"
    )

    result1 = import_outlook_csv(connection, first)
    result2 = import_outlook_csv(connection, second)

    assert result1.batch_id != result2.batch_id
    assert connection.execute(
        "SELECT count(*) FROM events"
    ).fetchone()[0] == 2


def test_invalid_csv_does_not_change_existing_data(tmp_path, connection):
    first = write_csv(tmp_path, [make_row()], name="first.csv")
    import_outlook_csv(connection, first)
    invalid = write_csv(
        tmp_path,
        [make_row(), make_row(開始日="不正")],
        name="invalid.csv",
    )

    with pytest.raises(OutlookCsvError):
        import_outlook_csv(connection, invalid)

    assert connection.execute(
        "SELECT count(*) FROM events"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT count(*) FROM import_batches"
    ).fetchone()[0] == 1


def test_database_failure_rolls_back_entire_batch(tmp_path, connection):
    first = write_csv(tmp_path, [make_row()], name="first.csv")
    import_outlook_csv(connection, first)

    # 二つ目の予定保存で失敗させ、最初の予定も戻ることを確認。
    with connection:
        connection.execute(
            """
            CREATE TRIGGER reject_test_event
            BEFORE INSERT ON events
            WHEN NEW.subject = '保存失敗'
            BEGIN
                SELECT RAISE(ABORT, 'test failure');
            END
            """
        )

    path = write_csv(
        tmp_path,
        [make_row(件名="追加予定"), make_row(件名="保存失敗")],
        name="second.csv",
    )

    with pytest.raises(sqlcipher.IntegrityError):
        import_outlook_csv(connection, path)

    assert connection.execute(
        "SELECT count(*) FROM events"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT count(*) FROM import_batches"
    ).fetchone()[0] == 1
    assert not connection.in_transaction


def test_rejects_call_inside_existing_transaction(tmp_path, connection):
    path = write_csv(tmp_path, [make_row()])
    connection.execute("BEGIN")

    try:
        with pytest.raises(RuntimeError, match="トランザクション"):
            import_outlook_csv(connection, path)
        assert connection.in_transaction
    finally:
        connection.rollback()
