import csv
from contextlib import closing
from datetime import date, datetime

import pytest

from calendardock.database import create_database, open_database
from calendardock.importer import import_outlook_csv
from calendardock.repository import (
    get_event_detail,
    list_events_for_day,
)

HEADERS = [
    "件名",
    "開始日",
    "開始時刻",
    "終了日",
    "終了時刻",
    "終日イベント",
    "場所",
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
    }
    row.update(changes)
    return row


@pytest.fixture
def load_events(tmp_path):
    connections = []

    def load(rows):
        csv_path = tmp_path / "calendar.csv"
        with csv_path.open(
            "w", encoding="cp932", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)

        db_path = tmp_path / f"calendar_{len(connections)}.db"
        create_database(db_path, "test-password")
        connection = open_database(db_path, "test-password")
        connections.append(connection)
        import_outlook_csv(connection, csv_path)
        return connection

    yield load

    for connection in connections:
        connection.close()


def test_returns_event_summary(load_events):
    connection = load_events([make_row()])
    events = list_events_for_day(connection, date(2026, 10, 9))

    assert len(events) == 1
    event = events[0]
    assert event.id > 0
    assert event.subject == "予定"
    assert event.starts_at == datetime(2026, 10, 9, 9)
    assert event.ends_at == datetime(2026, 10, 9, 10)
    assert event.all_day is False
    assert event.location == "自宅"


def test_excludes_other_days(load_events):
    connection = load_events([make_row()])

    assert list_events_for_day(
        connection, date(2026, 10, 8)
    ) == []
    assert list_events_for_day(
        connection, date(2026, 10, 10)
    ) == []


def test_all_day_event_is_not_shown_on_end_date(load_events):
    connection = load_events(
        [
            make_row(
                開始時刻="0:00:00",
                終了日="2026/10/10",
                終了時刻="0:00:00",
                終日イベント="True",
            )
        ]
    )

    assert len(list_events_for_day(
        connection, date(2026, 10, 9)
    )) == 1
    assert list_events_for_day(
        connection, date(2026, 10, 10)
    ) == []


def test_multiday_event_appears_on_each_covered_day(load_events):
    connection = load_events(
        [
            make_row(
                開始日="2026/10/8",
                開始時刻="23:00:00",
                終了日="2026/10/10",
                終了時刻="1:00:00",
            )
        ]
    )

    for day in (8, 9, 10):
        assert len(list_events_for_day(
            connection, date(2026, 10, day)
        )) == 1

    assert list_events_for_day(
        connection, date(2026, 10, 11)
    ) == []


def test_event_ending_at_midnight_is_excluded_from_next_day(load_events):
    connection = load_events(
        [
            make_row(
                開始日="2026/10/8",
                開始時刻="23:00:00",
                終了時刻="0:00:00",
            )
        ]
    )

    assert len(list_events_for_day(
        connection, date(2026, 10, 8)
    )) == 1
    assert list_events_for_day(
        connection, date(2026, 10, 9)
    ) == []


def test_zero_duration_event_is_shown_on_start_day(load_events):
    connection = load_events(
        [
            make_row(
                開始時刻="0:00:00",
                終了時刻="0:00:00",
            )
        ]
    )

    assert len(list_events_for_day(
        connection, date(2026, 10, 9)
    )) == 1
    assert list_events_for_day(
        connection, date(2026, 10, 8)
    ) == []
    assert list_events_for_day(
        connection, date(2026, 10, 10)
    ) == []


def test_orders_all_day_first_then_start_time(load_events):
    connection = load_events(
        [
            make_row(件名="午後", 開始時刻="15:00:00",
                     終了時刻="16:00:00"),
            make_row(件名="午前"),
            make_row(
                件名="終日",
                開始時刻="0:00:00",
                終了日="2026/10/10",
                終了時刻="0:00:00",
                終日イベント="True",
            ),
        ]
    )

    events = list_events_for_day(connection, date(2026, 10, 9))
    assert [event.subject for event in events] == [
        "終日", "午前", "午後"
    ]


def test_preserves_empty_subject_and_duplicate_events(load_events):
    row = make_row(件名="")
    connection = load_events([row, row])

    events = list_events_for_day(connection, date(2026, 10, 9))

    assert len(events) == 2
    assert all(event.subject == "" for event in events)
    assert events[0].id != events[1].id


def test_handles_year_boundary(load_events):
    connection = load_events(
        [
            make_row(
                開始日="2026/12/31",
                開始時刻="23:00:00",
                終了日="2027/1/1",
                終了時刻="1:00:00",
            )
        ]
    )

    assert len(list_events_for_day(
        connection, date(2026, 12, 31)
    )) == 1
    assert len(list_events_for_day(
        connection, date(2027, 1, 1)
    )) == 1


def test_empty_import_returns_empty_list(load_events):
    connection = load_events([])

    assert list_events_for_day(
        connection, date(2026, 10, 9)
    ) == []


def test_detail_returns_event_and_source_information(load_events):
    original = make_row(場所="会議室")
    connection = load_events([original])
    summary = list_events_for_day(
        connection, date(2026, 10, 9)
    )[0]

    detail = get_event_detail(connection, summary.id)

    assert detail is not None
    assert detail.id == summary.id
    assert detail.subject == "予定"
    assert detail.starts_at == datetime(2026, 10, 9, 9)
    assert detail.ends_at == datetime(2026, 10, 9, 10)
    assert detail.all_day is False
    assert detail.location == "会議室"
    assert detail.source_name == "calendar.csv"
    assert detail.source_row == 2
    assert detail.import_batch_id > 0
    assert detail.source_fields == original


def test_detail_returns_none_for_missing_id(load_events):
    connection = load_events([make_row()])

    assert get_event_detail(connection, -1) is None


def test_detail_preserves_multiline_body_and_categories(load_events):
    connection = load_events([make_row()])
    event_id = list_events_for_day(
        connection, date(2026, 10, 9)
    )[0].id
    body = '1行目, "引用"\n2行目'

    with connection:
        connection.execute(
            """
            UPDATE events
            SET body = ?, categories = ?
            WHERE id = ?
            """,
            (body, "個人;通院", event_id),
        )

    detail = get_event_detail(connection, event_id)

    assert detail.body == body
    assert detail.categories == "個人;通院"


def test_detail_preserves_all_day_dates(load_events):
    connection = load_events(
        [
            make_row(
                開始時刻="0:00:00",
                終了日="2026/10/10",
                終了時刻="0:00:00",
                終日イベント="True",
            )
        ]
    )
    event_id = list_events_for_day(
        connection, date(2026, 10, 9)
    )[0].id

    detail = get_event_detail(connection, event_id)

    assert detail.all_day is True
    assert detail.starts_at == datetime(2026, 10, 9)
    assert detail.ends_at == datetime(2026, 10, 10)


def test_detail_identifies_each_duplicate_source_record(load_events):
    row = make_row(件名="")
    connection = load_events([row, row])
    summaries = list_events_for_day(
        connection, date(2026, 10, 9)
    )

    first = get_event_detail(connection, summaries[0].id)
    second = get_event_detail(connection, summaries[1].id)

    assert first.id != second.id
    assert first.subject == second.subject == ""
    assert first.source_row == 2
    assert second.source_row == 3
    assert first.source_fields == second.source_fields


def test_detail_keeps_original_fields_after_event_update(load_events):
    original = make_row()
    connection = load_events([original])
    event_id = list_events_for_day(
        connection, date(2026, 10, 9)
    )[0].id

    with connection:
        connection.execute(
            "UPDATE events SET subject = ? WHERE id = ?",
            ("変更後の件名", event_id),
        )

    detail = get_event_detail(connection, event_id)

    assert detail.subject == "変更後の件名"
    assert detail.source_fields["件名"] == "予定"
    assert detail.source_fields == original
