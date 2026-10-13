"""CalendarDockのDB構造更新。"""

from __future__ import annotations

from calendardock.importer import _ensure_tables


def _rebuild_events(connection):
    connection.execute(
        """
        CREATE TABLE events_v2 (
            id INTEGER PRIMARY KEY,
            subject TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            all_day INTEGER NOT NULL CHECK (all_day IN (0, 1)),
            location TEXT NOT NULL,
            body TEXT NOT NULL,
            categories TEXT NOT NULL,
            source_row INTEGER,
            source_fields_json TEXT,
            import_batch_id INTEGER REFERENCES import_batches(id),

            CHECK (
                (
                    source_row IS NULL
                    AND source_fields_json IS NULL
                    AND import_batch_id IS NULL
                )
                OR
                (
                    source_row IS NOT NULL
                    AND source_row >= 2
                    AND source_fields_json IS NOT NULL
                    AND import_batch_id IS NOT NULL
                )
            ),

            UNIQUE (import_batch_id, source_row)
        )
        """
    )

    connection.execute(
        """
        INSERT INTO events_v2 (
            id, subject, starts_at, ends_at, all_day,
            location, body, categories,
            source_row, source_fields_json, import_batch_id
        )
        SELECT
            id, subject, starts_at, ends_at, all_day,
            location, body, categories,
            source_row, source_fields_json, import_batch_id
        FROM events
        """
    )

    connection.execute("DROP TABLE events")
    connection.execute("ALTER TABLE events_v2 RENAME TO events")
    connection.execute(
        "CREATE INDEX idx_events_starts_at ON events (starts_at)"
    )


def upgrade_database(connection) -> bool:
    """バージョン1を2へ更新する。

    更新した場合はTrue、すでに2の場合はFalseを返す。
    呼び出し元の既存トランザクションには参加しない。
    """
    if connection.in_transaction:
        raise RuntimeError(
            "DB更新はトランザクション開始前に呼び出してください。"
        )

    with connection:
        connection.execute("BEGIN IMMEDIATE")

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version == 2:
            return False
        if version != 1:
            raise ValueError(f"未対応のDBバージョンです: {version}")

        # CSV未取込のDBにも対応する。
        _ensure_tables(connection)
        _rebuild_events(connection)

        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("DB内の参照関係に不整合があります。")

        connection.execute("PRAGMA user_version = 2")

    return True


def upgrade_for_deletion(connection) -> bool:
    """バージョン2を3へ更新し、削除済みフラグを追加する。"""
    if connection.in_transaction:
        raise RuntimeError(
            "DB更新はトランザクション開始前に呼び出してください。"
        )

    with connection:
        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version == 3:
            return False
        if version != 2:
            raise ValueError(
                "削除機能の追加にはDBバージョン2が必要です。"
            )

        connection.execute(
            """
            ALTER TABLE events
            ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0
                CHECK (is_deleted IN (0, 1))
            """
        )
        connection.execute("PRAGMA user_version = 3")

    return True
