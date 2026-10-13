"""予定の新規登録・編集。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from calendardock.repository import active_event_condition

class EventNotFoundError(ValueError):
    """編集対象の予定が存在しない場合。"""


@dataclass(frozen=True)
class EventDraft:
    subject: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool = False
    location: str = ""
    body: str = ""
    categories: str = ""


def _validate(draft: EventDraft) -> None:
    for name in ("subject", "location", "body", "categories"):
        if not isinstance(getattr(draft, name), str):
            raise ValueError("件名・場所・内容・分類は文字列が必要です。")

    if not isinstance(draft.all_day, bool):
        raise ValueError("終日指定はTrueまたはFalseが必要です。")

    for value in (draft.starts_at, draft.ends_at):
        if not isinstance(value, datetime):
            raise ValueError("開始・終了には日時が必要です。")
        if value.tzinfo is not None:
            raise ValueError("日時はタイムゾーンなしで指定してください。")
        if value.microsecond:
            raise ValueError("日時は秒単位で指定してください。")

    if draft.ends_at < draft.starts_at:
        raise ValueError("終了日時が開始日時より前です。")

    if draft.all_day:
        if (
            draft.starts_at.time() != time.min
            or draft.ends_at.time() != time.min
        ):
            raise ValueError("終日予定の開始・終了時刻は0時が必要です。")
        if draft.ends_at <= draft.starts_at:
            raise ValueError(
                "終日予定の終了には最終日の翌日を指定してください。"
            )


def _check_connection(connection) -> None:
    if connection.in_transaction:
        raise RuntimeError(
            "予定保存はトランザクション開始前に呼び出してください。"
        )
    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    if version not in (2, 3):
        raise ValueError("予定保存にはDBバージョン2または3が必要です。")


def _values(draft: EventDraft) -> tuple:
    return (
        draft.subject,
        draft.starts_at.isoformat(timespec="seconds"),
        draft.ends_at.isoformat(timespec="seconds"),
        int(draft.all_day),
        draft.location,
        draft.body,
        draft.categories,
    )


def create_event(connection, draft: EventDraft) -> int:
    """予定を新規登録し、IDを返す。"""
    _validate(draft)
    _check_connection(connection)

    with connection:
        cursor = connection.execute(
            """
            INSERT INTO events (
                subject, starts_at, ends_at, all_day,
                location, body, categories
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            _values(draft),
        )
        event_id = cursor.lastrowid

    return event_id


def update_event(connection, event_id: int, draft: EventDraft) -> None:
    """削除されていない予定を編集する。元CSV情報は変更しない。"""
    _validate(draft)
    _check_connection(connection)
    active = active_event_condition(connection)

    with connection:
        cursor = connection.execute(
            f"""
            UPDATE events
            SET
                subject = ?,
                starts_at = ?,
                ends_at = ?,
                all_day = ?,
                location = ?,
                body = ?,
                categories = ?
            WHERE id = ? AND {active}
            """,
            (*_values(draft), event_id),
        )
        if cursor.rowcount != 1:
            raise EventNotFoundError("編集対象の予定がありません。")


def delete_event(connection, event_id: int) -> None:
    """予定を削除済みにする。予定データと移行元情報は保持する。"""
    _check_connection(connection)

    version = connection.execute(
        "PRAGMA user_version"
    ).fetchone()[0]
    if version != 3:
        raise ValueError("削除にはDBバージョン3が必要です。")

    with connection:
        cursor = connection.execute(
            """
            UPDATE events
            SET is_deleted = 1
            WHERE id = ? AND is_deleted = 0
            """,
            (event_id,),
        )
        if cursor.rowcount != 1:
            raise EventNotFoundError("削除対象の予定がありません。")
