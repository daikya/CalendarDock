"""実際のOutlook CSVを新しい暗号化DBへ取り込む。"""

from contextlib import closing
from getpass import getpass
from pathlib import Path

from calendardock.database import create_database, open_database
from calendardock.importer import import_outlook_csv
from calendardock.outlook_csv import read_outlook_csv


def main():
    project_dir = Path(__file__).resolve().parent
    csv_path = project_dir / "calendar.csv"
    db_path = project_dir / "data" / "calendar.db"

    if not csv_path.is_file():
        raise SystemExit(f"CSVがありません: {csv_path}")

    if db_path.exists():
        raise SystemExit(
            f"既存DBがあるため処理を停止しました: {db_path}"
        )

    # 不正なCSVなら、DBを作成する前に停止する。
    events = read_outlook_csv(csv_path)
    if not events:
        raise SystemExit("CSVに予定がありません。")

    print(f"取込対象: {len(events):,}件")
    print(f"作成先: {db_path}")

    password = getpass("新しいDBのパスワード: ")
    confirmation = getpass("確認のため再入力: ")

    if password != confirmation:
        raise SystemExit("パスワードが一致しません。")

    create_database(db_path, password)

    with closing(open_database(db_path, password)) as connection:
        result = import_outlook_csv(connection, csv_path)

        summary = connection.execute(
            """
            SELECT
                count(*) AS total,
                coalesce(sum(all_day), 0) AS all_day_count,
                min(starts_at) AS first_start,
                max(starts_at) AS last_start
            FROM events
            """
        ).fetchone()

        if summary["total"] != len(events):
            raise RuntimeError("CSV件数とDB件数が一致しません。")

        if connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] != "ok":
            raise RuntimeError("DBの整合性確認に失敗しました。")

        if connection.execute(
            "PRAGMA cipher_integrity_check"
        ).fetchall():
            raise RuntimeError("暗号化DBの整合性確認に失敗しました。")

    # 接続を閉じた後、同じパスワードで再び開けるか確認する。
    with closing(open_database(db_path, password)) as connection:
        reopened_count = connection.execute(
            "SELECT count(*) FROM events"
        ).fetchone()[0]

    if reopened_count != len(events):
        raise RuntimeError("再接続後のDB件数が一致しません。")

    print()
    print("取り込み完了")
    print("今回の取込件数:", result.imported_count)
    print("DB内の予定件数:", summary["total"])
    print("終日予定:", summary["all_day_count"])
    print(
        "開始日の範囲:",
        summary["first_start"][:10],
        "～",
        summary["last_start"][:10],
    )
    print("DB整合性・暗号化整合性・再接続: OK")


if __name__ == "__main__":
    main()
