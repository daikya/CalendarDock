"""Outlook予定表CSVの読み取りと予定データへの変換。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REQUIRED_COLUMNS = (
    "件名",
    "開始日",
    "開始時刻",
    "終了日",
    "終了時刻",
    "終日イベント",
)


class OutlookCsvError(ValueError):
    """Outlook CSVの形式またはデータが不正な場合の例外。"""


@dataclass(frozen=True)
class ImportedEvent:
    subject: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    location: str
    body: str
    categories: str
    source_row: int
    source_fields: dict[str, str]


def _parse_datetime(
    row: dict[str, str],
    date_column: str,
    time_column: str,
    source_row: int,
) -> datetime:
    value = f"{row[date_column].strip()} {row[time_column].strip()}"

    try:
        return datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
    except ValueError as exc:
        raise OutlookCsvError(
            f"CSV行{source_row}: "
            f"{date_column}・{time_column}が不正です: {value!r}"
        ) from exc


def _parse_bool(value: str, column: str, source_row: int) -> bool:
    normalized = value.strip().casefold()

    if normalized == "true":
        return True
    if normalized == "false":
        return False

    raise OutlookCsvError(
        f"CSV行{source_row}: {column}が不正です: {value!r}"
    )


def _convert_row(row: dict[str, str], source_row: int) -> ImportedEvent:
    starts_at = _parse_datetime(
        row, "開始日", "開始時刻", source_row
    )
    ends_at = _parse_datetime(
        row, "終了日", "終了時刻", source_row
    )

    if ends_at < starts_at:
        raise OutlookCsvError(
            f"CSV行{source_row}: 終了日時が開始日時より前です。"
        )

    return ImportedEvent(
        subject=row["件名"],
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=_parse_bool(
            row["終日イベント"], "終日イベント", source_row
        ),
        location=row.get("場所", ""),
        body=row.get("内容", ""),
        categories=row.get("分類", ""),
        source_row=source_row,
        source_fields=dict(row),
    )


def read_outlook_csv(path: str | Path) -> list[ImportedEvent]:
    """CP932またはUTF-8のOutlook CSVを読み取る。

    source_rowは、ヘッダーを1行目としたCSVレコード番号。
    複数行の内容があるため、ファイル上の物理行番号とは異なる。

    空の件名、同時刻の開始・終了、重複レコードは保持する。
    日時にはタイムゾーンを付与せず、CSVの現地日時を保持する。
    """
    path = Path(path)

    # UTF-8で読めなければ、Windows日本語CSVのCP932を試す。
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return _read_with_encoding(path, encoding)
        except UnicodeDecodeError:
            if encoding == "cp932":
                raise OutlookCsvError(
                    "CSVをUTF-8またはCP932で読み取れません。"
                ) from None

    raise AssertionError("到達しない処理です。")


def _read_with_encoding(
    path: Path, encoding: str
) -> list[ImportedEvent]:
    events: list[ImportedEvent] = []

    with path.open(
        "r", encoding=encoding, newline=""
    ) as stream:
        reader = csv.DictReader(stream, strict=True)

        try:
            headers = reader.fieldnames
            if not headers:
                raise OutlookCsvError("CSVにヘッダーがありません。")

            if len(headers) != len(set(headers)):
                raise OutlookCsvError("CSVに重複した列名があります。")

            missing = [
                column
                for column in REQUIRED_COLUMNS
                if column not in headers
            ]
            if missing:
                raise OutlookCsvError(
                    "必須列がありません: " + "、".join(missing)
                )

            for source_row, raw_row in enumerate(reader, start=2):
                if None in raw_row:
                    raise OutlookCsvError(
                        f"CSV行{source_row}: 列数がヘッダーより多いです。"
                    )

                if any(value is None for value in raw_row.values()):
                    raise OutlookCsvError(
                        f"CSV行{source_row}: 列数がヘッダーより少ないです。"
                    )

                events.append(_convert_row(raw_row, source_row))

        except csv.Error as exc:
            raise OutlookCsvError(
                f"CSVの構文が不正です"
                f"（物理行{reader.line_num}付近）: {exc}"
            ) from exc

    return events
