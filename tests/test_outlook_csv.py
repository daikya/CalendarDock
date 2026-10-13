import csv
from datetime import datetime

import pytest

from calendardock.outlook_csv import (
    OutlookCsvError,
    read_outlook_csv,
)


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


def write_csv(tmp_path, rows, encoding="cp932", headers=None):
    path = tmp_path / "calendar.csv"

    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=HEADERS if headers is None else headers,
        )
        writer.writeheader()
        writer.writerows(rows)

    return path


@pytest.mark.parametrize("encoding", ["cp932", "utf-8-sig"])
def test_reads_supported_encodings(tmp_path, encoding):
    path = write_csv(tmp_path, [make_row()], encoding)
    events = read_outlook_csv(path)

    assert len(events) == 1
    event = events[0]
    assert event.subject == "予定"
    assert event.starts_at == datetime(2026, 10, 9, 9)
    assert event.ends_at == datetime(2026, 10, 9, 10)
    assert event.all_day is False
    assert event.location == "自宅"
    assert event.source_row == 2
    assert event.source_fields["優先度"] == "標準"


def test_preserves_multiline_body_and_punctuation(tmp_path):
    body = '1行目, "引用"\r\n2行目'
    path = write_csv(tmp_path, [make_row(内容=body)])

    assert read_outlook_csv(path)[0].body == body


def test_preserves_all_day_end_date(tmp_path):
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
    event = read_outlook_csv(path)[0]

    assert event.all_day is True
    assert event.starts_at == datetime(2026, 10, 9)
    assert event.ends_at == datetime(2026, 10, 10)


def test_preserves_empty_subject(tmp_path):
    path = write_csv(tmp_path, [make_row(件名="")])

    assert read_outlook_csv(path)[0].subject == ""


def test_accepts_equal_start_and_end(tmp_path):
    path = write_csv(
        tmp_path, [make_row(終了時刻="9:00:00")]
    )
    event = read_outlook_csv(path)[0]

    assert event.starts_at == event.ends_at


def test_preserves_duplicate_records(tmp_path):
    row = make_row()
    path = write_csv(tmp_path, [row, row])

    events = read_outlook_csv(path)

    assert len(events) == 2
    assert events[0].source_fields == events[1].source_fields
    assert [event.source_row for event in events] == [2, 3]


def test_record_number_with_multiline_body(tmp_path):
    path = write_csv(
        tmp_path,
        [make_row(内容="1行目\n2行目"), make_row(件名="次の予定")],
    )

    assert [
        event.source_row for event in read_outlook_csv(path)
    ] == [2, 3]


def test_rejects_end_before_start(tmp_path):
    path = write_csv(
        tmp_path, [make_row(終了時刻="8:00:00")]
    )

    with pytest.raises(OutlookCsvError, match="終了日時"):
        read_outlook_csv(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"開始日": "2026/2/30"},
        {"開始時刻": "25:00:00"},
        {"終了日": ""},
        {"終了時刻": "不正"},
    ],
)
def test_rejects_invalid_datetime(tmp_path, changes):
    path = write_csv(tmp_path, [make_row(**changes)])

    with pytest.raises(OutlookCsvError, match="CSV行2"):
        read_outlook_csv(path)


def test_rejects_invalid_boolean(tmp_path):
    path = write_csv(
        tmp_path, [make_row(終日イベント="不明")]
    )

    with pytest.raises(OutlookCsvError, match="終日イベント"):
        read_outlook_csv(path)


def test_rejects_missing_required_column(tmp_path):
    headers = [column for column in HEADERS if column != "開始日"]
    path = write_csv(tmp_path, [], headers=headers)

    with pytest.raises(OutlookCsvError, match="開始日"):
        read_outlook_csv(path)


def test_rejects_duplicate_headers(tmp_path):
    path = tmp_path / "calendar.csv"
    path.write_text("件名,件名\n", encoding="cp932")

    with pytest.raises(OutlookCsvError, match="重複した列名"):
        read_outlook_csv(path)


def test_rejects_empty_file(tmp_path):
    path = tmp_path / "calendar.csv"
    path.write_bytes(b"")

    with pytest.raises(OutlookCsvError, match="ヘッダー"):
        read_outlook_csv(path)


@pytest.mark.parametrize(
    "data",
    [
        "予定,2026/10/9,9:00:00,2026/10/9,10:00:00,False,余分",
        "予定,2026/10/9,9:00:00,2026/10/9,10:00:00",
    ],
)
def test_rejects_wrong_column_count(tmp_path, data):
    path = tmp_path / "calendar.csv"
    headers = ",".join(HEADERS[:6])
    path.write_text(headers + "\n" + data + "\n", encoding="cp932")

    with pytest.raises(OutlookCsvError, match="列数"):
        read_outlook_csv(path)


def test_rejects_broken_csv_quotes(tmp_path):
    path = tmp_path / "calendar.csv"
    headers = ",".join(HEADERS[:6])
    path.write_text(
        headers + '\n"閉じていない引用符',
        encoding="cp932",
    )

    with pytest.raises(OutlookCsvError, match="構文"):
        read_outlook_csv(path)
