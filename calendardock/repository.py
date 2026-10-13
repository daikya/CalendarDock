"""予定の取得処理。"""

from __future__ import annotations

import json

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


def active_event_condition(connection, alias="") -> str:
    """対応DBに応じて、削除済み除外のSQL条件を返す。"""
    if alias not in ("", "e"):
        raise ValueError("未対応のテーブル別名です。")

    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]

    if version in (1, 2):
        return "1 = 1"
    if version == 3:
        prefix = "e." if alias else ""
        return f"{prefix}is_deleted = 0"

    raise ValueError(f"未対応のDBバージョンです: {version}")


@dataclass(frozen=True)
class EventSummary:
    id: int
    subject: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    location: str


def list_events_for_day(connection, day: date) -> list[EventSummary]:
    """指定日に重なる、削除されていない予定を取得する。"""
    day_start = datetime.combine(day, time.min)
    day_end = day_start + timedelta(days=1)
    active = active_event_condition(connection)

    rows = connection.execute(
        f"""
        SELECT
            id, subject, starts_at, ends_at, all_day, location
        FROM events
        WHERE {active}
          AND (
              (starts_at < ? AND ends_at > ?)
              OR
              (
                  starts_at = ends_at
                  AND starts_at >= ?
                  AND starts_at < ?
              )
          )
        ORDER BY all_day DESC, starts_at, id
        """,
        (
            day_end.isoformat(timespec="seconds"),
            day_start.isoformat(timespec="seconds"),
            day_start.isoformat(timespec="seconds"),
            day_end.isoformat(timespec="seconds"),
        ),
    ).fetchall()

    return [
        EventSummary(
            id=row["id"],
            subject=row["subject"],
            starts_at=datetime.fromisoformat(row["starts_at"]),
            ends_at=datetime.fromisoformat(row["ends_at"]),
            all_day=bool(row["all_day"]),
            location=row["location"],
        )
        for row in rows
    ]


@dataclass(frozen=True)
class EventDetail(EventSummary):
    body: str
    categories: str
    source_row: int | None
    source_fields: dict[str, str] | None
    import_batch_id: int | None
    source_name: str | None


def get_event_detail(connection, event_id: int) -> EventDetail | None:
    """予定の詳細とOutlook移行元情報を取得する。

    指定したIDが存在しない場合はNoneを返す。
    """
    active = active_event_condition(connection, "e")
    row = connection.execute(
        f"""
        SELECT
            e.id,
            e.subject,
            e.starts_at,
            e.ends_at,
            e.all_day,
            e.location,
            e.body,
            e.categories,
            e.source_row,
            e.source_fields_json,
            e.import_batch_id,
            b.source_name
        FROM events AS e
        LEFT JOIN import_batches AS b ON b.id = e.import_batch_id
        WHERE e.id = ? AND {active}
        """,
        (event_id,),
    ).fetchone()

    if row is None:
        return None

    return EventDetail(
        id=row["id"],
        subject=row["subject"],
        starts_at=datetime.fromisoformat(row["starts_at"]),
        ends_at=datetime.fromisoformat(row["ends_at"]),
        all_day=bool(row["all_day"]),
        location=row["location"],
        body=row["body"],
        categories=row["categories"],
        source_row=row["source_row"],
        source_fields=(
            json.loads(row["source_fields_json"])
            if row["source_fields_json"] is not None
            else None
        ),
        import_batch_id=row["import_batch_id"],
        source_name=row["source_name"],
    )
