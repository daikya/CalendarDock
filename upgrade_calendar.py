"""実際のCalendarDock DBをバージョン2へ更新する。"""

from contextlib import closing
from getpass import getpass
from pathlib import Path

from calendardock.database import open_database
from calendardock.migrations import upgrade_database


def snapshot(connection, table):
    # 呼び出し元で指定した固定のテーブル名だけを許可する。
    if table not in ("events", "import_batches"):
        raise ValueError("未対応のテーブルです。")

    return [
        tuple(row)
        for row in connection.execute(
            f"SELECT * FROM {table} ORDER BY id"
        )
    ]


def main():
    db_path = (
        Path(__file__).resolve().parent / "data" / "calendar.db"
    )
    password = getpass("DBのパスワード: ")

    with closing(open_database(db_path, password)) as connection:
        before_version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        before_events = snapshot(connection, "events")
        before_batches = snapshot(connection, "import_batches")

        updated = upgrade_database(connection)

        if snapshot(connection, "events") != before_events:
            raise RuntimeError("更新前後で予定データが一致しません。")
        if snapshot(connection, "import_batches") != before_batches:
            raise RuntimeError("更新前後で取込履歴が一致しません。")

        if connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] != "ok":
            raise RuntimeError("DBの整合性確認に失敗しました。")

        if connection.execute(
            "PRAGMA cipher_integrity_check"
        ).fetchall():
            raise RuntimeError("暗号化DBの整合性確認に失敗しました。")

        if connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall():
            raise RuntimeError("参照関係の確認に失敗しました。")

    # 接続を閉じてから、再接続して確認する。
    with closing(open_database(db_path, password)) as connection:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version != 2:
            raise RuntimeError("DBバージョンが2ではありません。")
        if snapshot(connection, "events") != before_events:
            raise RuntimeError("再接続後の予定データが一致しません。")
        if snapshot(connection, "import_batches") != before_batches:
            raise RuntimeError("再接続後の取込履歴が一致しません。")

    print()
    print("DB構造更新完了" if updated else "DBはすでに更新済みです。")
    print("DBバージョン:", before_version, "→", version)
    print("予定件数:", len(before_events))
    print("取込履歴件数:", len(before_batches))
    print("予定データ・取込履歴の保持: OK")
    print("DB整合性・暗号化整合性・参照関係・再接続: OK")


if __name__ == "__main__":
    main()
