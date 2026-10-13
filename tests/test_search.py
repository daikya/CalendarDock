import csv
from contextlib import closing
from datetime import datetime

import pytest

from calendardock.database import create_database, open_database
from calendardock.importer import import_outlook_csv
from calendardock.search import search_events


HEADERS = [
    "件名",
    "開始日",
    "開始時刻",
    "終了日",
    "終了時刻",
    "終日イベント",
    "場所",
    "内容",
]


def make_row(**changes):
    row = {
        "件名": "予定",
        "開始日": "2026/10/9",
        "開始時刻": "9:00:00",
        "終了日": "2026/10/9",
        "終了時刻": "10:00:00",
        "終日イベント": "False",
        "場所": "",
        "内容": "",
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


@pytest.mark.parametrize(
    "field",
    ["件名", "場所", "内容"],
)
def test_searches_each_field(load_events, field):
    connection = load_events([make_row(**{field: "病院の予約"})])

    assert len(search_events(connection, "病院")) == 1


def test_normalizes_width_and_case(load_events):
    connection = load_events(
        [make_row(件名="Ｐｙｔｈｏｎ カレンダー")]
    )

    assert len(search_events(connection, "python")) == 1
    assert len(search_events(connection, "ｶﾚﾝﾀﾞｰ")) == 1


def test_multiple_terms_can_match_different_fields(load_events):
    connection = load_events(
        [
            make_row(件名="通院", 場所="松戸の病院"),
            make_row(件名="通院", 場所="東京の病院"),
        ]
    )

    results = search_events(connection, "通院　松戸")

    assert len(results) == 1
    assert results[0].location == "松戸の病院"


def test_does_not_match_across_field_boundaries(load_events):
    connection = load_events([make_row(件名="abc", 場所="def")])

    assert search_events(connection, "cde") == []


def test_empty_query_returns_no_results(load_events):
    connection = load_events([make_row()])

    assert search_events(connection, "") == []
    assert search_events(connection, " \t\n　") == []


def test_no_match_returns_empty_list(load_events):
    connection = load_events([make_row(件名="通院")])

    assert search_events(connection, "旅行") == []


def test_searches_multiline_body(load_events):
    connection = load_events(
        [make_row(内容="1行目\n次回の予約は午後")]
    )

    assert len(search_events(connection, "予約")) == 1


def test_treats_sql_wildcards_and_quotes_as_literal_text(load_events):
    connection = load_events(
        [
            make_row(件名="100%完了"),
            make_row(件名="test_note"),
            make_row(件名="O'Brien"),
            make_row(件名="通常の予定"),
        ]
    )

    assert len(search_events(connection, "%")) == 1
    assert len(search_events(connection, "_")) == 1
    assert len(search_events(connection, "'")) == 1


def test_returns_summary_in_chronological_order(load_events):
    connection = load_events(
        [
            make_row(
                件名="予定B",
                開始日="2026/10/10",
                終了日="2026/10/10",
            ),
            make_row(件名="予定A"),
        ]
    )

    results = search_events(connection, "予定")

    assert [event.subject for event in results] == [
        "予定A", "予定B"
    ]
    assert results[0].starts_at == datetime(2026, 10, 9, 9)
    assert results[0].all_day is False


def test_preserves_duplicate_results(load_events):
    row = make_row(件名="通院")
    connection = load_events([row, row])

    results = search_events(connection, "通院")

    assert len(results) == 2
    assert results[0].id != results[1].id


def test_repeated_searches_work(load_events):
    connection = load_events(
        [make_row(件名="通院"), make_row(件名="旅行")]
    )

    assert search_events(connection, "通院")[0].subject == "通院"
    assert search_events(connection, "旅行")[0].subject == "旅行"
