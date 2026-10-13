"""実DBに削除済みフラグを追加する。"""

from contextlib import closing
from getpass import getpass
from pathlib import Path

from calendardock.database import open_database
from calendardock.migrations import upgrade_for_deletion


def events_snapshot(connection):
    # 今回追加するis_deleted以外の全項目を比較する。
    return [
        tuple(row)
        for row in connection.execute(
            """
            SELECT
                id, subject, starts_at, ends_at, all_day,
                location, body, categories,
                source_row, source_fields_json, import_batch_id
            FROM events
            ORDER BY id
            """
        )
    ]


def batches_snapshot(connection):
    return [
        tuple(row)
        for row in connection.execute(
            "SELECT * FROM import_batches ORDER BY id"
        )
    ]


def main():
    path = Path(__file__).resolve().parent / "data" / "calendar.db"
    password = getpass("DBのパスワード: ")

    with closing(open_database(path, password)) as connection:
        before_version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        before_events = events_snapshot(connection)
        before_batches = batches_snapshot(connection)

        updated = upgrade_for_deletion(connection)

        if events_snapshot(connection) != before_events:
            raise RuntimeError("更新前後で予定データが一致しません。")
        if batches_snapshot(connection) != before_batches:
            raise RuntimeError("更新前後で取込履歴が一致しません。")

        if connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] != "ok":
            raise RuntimeError("DBの整合性確認に失敗しました。")
        if connection.execute(
            "PRAGMA cipher_integrity_check"
        ).fetchall():
            raise RuntimeError("暗号化整合性確認に失敗しました。")
        if connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall():
            raise RuntimeError("参照関係の確認に失敗しました。")

        deleted_count = connection.execute(
            "SELECT count(*) FROM events WHERE is_deleted = 1"
        ).fetchone()[0]

        if updated and deleted_count != 0:
            raise RuntimeError("更新直後の削除済み件数が不正です。")

    with closing(open_database(path, password)) as connection:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        if version != 3:
            raise RuntimeError("DBバージョンが3ではありません。")
        if events_snapshot(connection) != before_events:
            raise RuntimeError("再接続後の予定データが一致しません。")
        if batches_snapshot(connection) != before_batches:
            raise RuntimeError("再接続後の取込履歴が一致しません。")

    print()
    print("DB構造更新完了" if updated else "DBはすでに更新済みです。")
    print("DBバージョン:", before_version, "→", version)
    print("予定件数（削除済みを含む）:", len(before_events))
    print("削除済み件数:", deleted_count)
    print("予定データ・取込履歴の保持: OK")
    print("DB整合性・暗号化整合性・参照関係・再接続: OK")


if __name__ == "__main__":
    main()
