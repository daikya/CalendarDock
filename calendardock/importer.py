"""Outlook予定表CSVの暗号化DBへの一括取り込み。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from calendardock.outlook_csv import read_outlook_csv


class AlreadyImportedError(ValueError):
    """同じ予定データがすでに取り込まれている場合。"""


@dataclass(frozen=True)
class ImportResult:
    batch_id: int
    imported_count: int


def _ensure_tables(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS import_batches (
            id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL UNIQUE,
            imported_at TEXT NOT NULL,
            event_count INTEGER NOT NULL CHECK (event_count >= 0)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            subject TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            all_day INTEGER NOT NULL CHECK (all_day IN (0, 1)),
            location TEXT NOT NULL,
            body TEXT NOT NULL,
            categories TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            source_fields_json TEXT NOT NULL,
            import_batch_id INTEGER NOT NULL
                REFERENCES import_batches(id),
            UNIQUE (import_batch_id, source_row)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_starts_at
        ON events (starts_at)
        """
    )


def import_outlook_csv(connection, path: str | Path) -> ImportResult:
    """CSVを一括取り込みする。

    専用の、トランザクション開始前の接続で呼び出す。
    成功時は確定し、失敗時は今回の変更をすべて取り消す。
    """
    if connection.in_transaction:
        raise RuntimeError(
            "CSV取込はトランザクション開始前に呼び出してください。"
        )

    path = Path(path)

    # DBを変更する前に、CSV全体の形式・日時を検証する。
    events = read_outlook_csv(path)

    # 文字コードや改行形式が違っても、解析後の全項目が
    # 同じ並び・同じ値なら同一の取込として扱う。
    source_jsons = [
        json.dumps(
            event.source_fields,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for event in events
    ]
    fingerprint_data = json.dumps(
        source_jsons,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    fingerprint = hashlib.sha256(fingerprint_data).hexdigest()

    imported_at = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )

    # DDLを含めて、明示的に一つのトランザクションにする。
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_tables(connection)

        existing = connection.execute(
            """
            SELECT id FROM import_batches
            WHERE source_fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()

        if existing is not None:
            raise AlreadyImportedError(
                "同じ予定データはすでに取り込まれています。"
            )

        cursor = connection.execute(
            """
            INSERT INTO import_batches (
                source_name,
                source_fingerprint,
                imported_at,
                event_count
            ) VALUES (?, ?, ?, ?)
            """,
            (
                path.name,
                fingerprint,
                imported_at,
                len(events),
            ),
        )
        batch_id = cursor.lastrowid

        connection.executemany(
            """
            INSERT INTO events (
                subject,
                starts_at,
                ends_at,
                all_day,
                location,
                body,
                categories,
                source_row,
                source_fields_json,
                import_batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    event.subject,
                    event.starts_at.isoformat(timespec="seconds"),
                    event.ends_at.isoformat(timespec="seconds"),
                    int(event.all_day),
                    event.location,
                    event.body,
                    event.categories,
                    event.source_row,
                    source_json,
                    batch_id,
                )
                for event, source_json in zip(events, source_jsons)
            ),
        )

    return ImportResult(
        batch_id=batch_id,
        imported_count=len(events),
    )
