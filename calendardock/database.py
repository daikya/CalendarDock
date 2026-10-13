"""CalendarDockの暗号化DB作成・接続。"""

from __future__ import annotations

from pathlib import Path

from sqlcipher3 import dbapi2 as sqlcipher


APPLICATION_ID = 0x43444B31
SCHEMA_VERSION = 1


class DatabaseOpenError(ValueError):
    """パスワード不一致やDB破損などで開けない場合。"""


class InvalidDatabaseError(ValueError):
    """CalendarDockの対応DBではない場合。"""


def _validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise TypeError("パスワードは文字列で指定してください。")
    if not password.strip():
        raise ValueError("空のパスワードは使用できません。")
    if "\x00" in password:
        raise ValueError("パスワードにNULL文字は使用できません。")


def _connect(path: Path, password: str):
    # mode=rwで、存在しないファイルの自動作成を防ぐ。
    connection = sqlcipher.connect(
        path.resolve().as_uri() + "?mode=rw",
        uri=True,
    )

    try:
        # PRAGMAではプレースホルダーを使えないため、
        # SQL文字列内のシングルクォートをエスケープする。
        escaped = password.replace("'", "''")
        connection.execute(f"PRAGMA key = '{escaped}'")

        version = connection.execute(
            "PRAGMA cipher_version"
        ).fetchone()
        if not version or not version[0]:
            raise RuntimeError("SQLCipherが有効ではありません。")

        connection.row_factory = sqlcipher.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    except Exception:
        connection.close()
        raise


def create_database(path: str | Path, password: str) -> None:
    """新しい暗号化DBを作成する。既存ファイルは上書きしない。"""
    _validate_password(password)
    path = Path(path)

    # 親フォルダーは必要になった時点で作成する。
    path.parent.mkdir(parents=True, exist_ok=True)

    # 排他的にファイルを作成する。既存ならFileExistsError。
    with path.open("xb"):
        pass

    connection = None
    try:
        connection = _connect(path, password)

        with connection:
            connection.execute(
                """
                CREATE TABLE app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
                ("application", "CalendarDock"),
            )
            connection.execute(
                f"PRAGMA application_id = {APPLICATION_ID}"
            )
            connection.execute(
                f"PRAGMA user_version = {SCHEMA_VERSION}"
            )

    except Exception:
        if connection is not None:
            connection.close()
            connection = None

        # この処理で新規作成したファイルだけを除去する。
        path.unlink(missing_ok=True)
        raise

    finally:
        if connection is not None:
            connection.close()


def open_database(path: str | Path, password: str):
    """既存の対応DBを開く。返された接続は呼び出し側で閉じる。"""
    _validate_password(password)
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(path)

    if path.stat().st_size == 0:
        raise InvalidDatabaseError("空のファイルは開けません。")

    connection = _connect(path, password)

    try:
        try:
            # 鍵の設定だけでは判定できないので実際に読み取る。
            connection.execute(
                "SELECT count(*) FROM sqlite_master"
            ).fetchone()
        except sqlcipher.DatabaseError:
            raise DatabaseOpenError(
                "DBを開けません。パスワードが異なるか、"
                "ファイルが破損している、または形式が異なります。"
            ) from None

        application_id = connection.execute(
            "PRAGMA application_id"
        ).fetchone()[0]
        schema_version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if application_id != APPLICATION_ID:
            raise InvalidDatabaseError(
                "CalendarDockのDBではありません。"
            )
        if schema_version not in (1, 2, 3):
            raise InvalidDatabaseError(
                f"未対応のDBバージョンです: {schema_version}"
            )

        try:
            application = connection.execute(
                "SELECT value FROM app_metadata WHERE key = ?",
                ("application",),
            ).fetchone()
        except sqlcipher.DatabaseError:
            raise InvalidDatabaseError(
                "CalendarDockの管理情報が不正です。"
            ) from None

        if application is None or application[0] != "CalendarDock":
            raise InvalidDatabaseError(
                "CalendarDockの管理情報が不正です。"
            )

        return connection

    except Exception:
        connection.close()
        raise


def create_calendar_database(path: str | Path, password: str) -> None:
    """通常利用向けに、最新版のCalendarDock DBを作成する。

    既存ファイルは上書きしない。
    作成完了後は、CSV未取込でも予定の登録・閲覧ができる。
    """
    # databaseとmigrationsの相互importを避けるため、
    # この関数内で読み込む。
    from contextlib import closing

    from calendardock.migrations import (
        upgrade_database,
        upgrade_for_deletion,
    )

    create_database(path, password)

    with closing(open_database(path, password)) as connection:
        upgrade_database(connection)
        upgrade_for_deletion(connection)

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        if version != 3:
            raise InvalidDatabaseError(
                "新規DBの構造更新が完了していません。"
            )

        if connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] != "ok":
            raise InvalidDatabaseError(
                "新規DBの整合性確認に失敗しました。"
            )

        if connection.execute(
            "PRAGMA cipher_integrity_check"
        ).fetchall():
            raise InvalidDatabaseError(
                "新規DBの暗号化整合性確認に失敗しました。"
            )
