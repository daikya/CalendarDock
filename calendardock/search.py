"""予定の文字列検索。"""

from __future__ import annotations

import unicodedata

from calendardock.repository import (
    EventSummary,
    active_event_condition,
)
from datetime import datetime


def normalize_search_text(value: str) -> str:
    """全角・半角と英字の大文字・小文字の違いを吸収する。"""
    return unicodedata.normalize("NFKC", value).casefold()


def search_events(connection, query: str) -> list[EventSummary]:
    """件名・場所・内容を検索する。

    空白区切りの各語について、いずれかの項目に含まれる予定を返す。
    空の検索語は全件検索にせず、空の一覧を返す。
    """
    terms = normalize_search_text(query).split()
    if not terms:
        return []

    # 件名・場所・内容を結合せず、項目をまたぐ誤一致を避ける。
    def matches(subject, location, body):
        fields = [
            normalize_search_text(value or "")
            for value in (subject, location, body)
        ]
        return int(
            all(
                any(term in field for field in fields)
                for term in terms
            )
        )
    active = active_event_condition(connection)
    connection.create_function("calendar_matches", 3, matches)

    try:
        rows = connection.execute(
            f"""
            SELECT id, subject, starts_at, ends_at, all_day, location
            FROM events
            WHERE {active}
              AND calendar_matches(subject, location, body) = 1
            ORDER BY starts_at, all_day DESC, id
            """
        ).fetchall()
    finally:
        connection.create_function("calendar_matches", 3, None)

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
