import sqlite3
from contextlib import closing

import pytest

from calendardock.database import (
    DatabaseOpenError,
    InvalidDatabaseError,
    create_database,
    open_database,
)


def test_create_and_reopen(tmp_path):
    path = tmp_path / "calendar.db"
    create_database(path, "test-password")

    assert path.is_file()
    assert path.stat().st_size > 0

    with closing(open_database(path, "test-password")) as connection:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?",
            ("application",),
        ).fetchone()

        assert row[0] == "CalendarDock"
        assert connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0] == 1
        assert connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"
        assert connection.execute(
            "PRAGMA cipher_integrity_check"
        ).fetchall() == []


def test_wrong_password_does_not_damage_database(tmp_path):
    path = tmp_path / "calendar.db"
    create_database(path, "correct-password")
    original = path.read_bytes()

    with pytest.raises(DatabaseOpenError):
        open_database(path, "wrong-password")

    assert path.read_bytes() == original

    with closing(open_database(path, "correct-password")) as connection:
        assert connection.execute(
            "SELECT count(*) FROM app_metadata"
        ).fetchone()[0] == 1


def test_standard_sqlite_cannot_read_database(tmp_path):
    path = tmp_path / "calendar.db"
    create_database(path, "test-password")

    with closing(sqlite3.connect(path)) as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(
                "SELECT count(*) FROM sqlite_master"
            ).fetchone()


def test_existing_file_is_not_overwritten(tmp_path):
    path = tmp_path / "calendar.db"
    original = b"existing file"
    path.write_bytes(original)

    with pytest.raises(FileExistsError):
        create_database(path, "test-password")

    assert path.read_bytes() == original


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "missing" / "calendar.db"

    with pytest.raises(FileNotFoundError):
        open_database(path, "test-password")

    assert not path.exists()
    assert not path.parent.exists()


def test_parent_directory_is_created_when_needed(tmp_path):
    path = tmp_path / "data" / "calendar.db"

    assert not path.parent.exists()
    create_database(path, "test-password")

    assert path.is_file()


@pytest.mark.parametrize("password", ["", " ", "\t\n", "abc\x00def"])
def test_invalid_password_does_not_create_file(tmp_path, password):
    path = tmp_path / "data" / "calendar.db"

    with pytest.raises(ValueError):
        create_database(path, password)

    assert not path.exists()
    assert not path.parent.exists()


def test_password_with_japanese_and_quote(tmp_path):
    path = tmp_path / "calendar.db"
    password = "予定表'パスワード123"
    create_database(path, password)

    with closing(open_database(path, password)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM app_metadata"
        ).fetchone()[0] == 1


def test_japanese_multiline_roundtrip(tmp_path):
    path = tmp_path / "calendar.db"
    password = "test-password"
    text = '予定の詳細\n2行目, "引用"'

    create_database(path, password)

    with closing(open_database(path, password)) as connection:
        with connection:
            connection.execute(
                "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
                ("test_note", text),
            )

    with closing(open_database(path, password)) as connection:
        assert connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?",
            ("test_note",),
        ).fetchone()[0] == text


def test_rejects_empty_file(tmp_path):
    path = tmp_path / "calendar.db"
    path.write_bytes(b"")

    with pytest.raises(InvalidDatabaseError, match="空"):
        open_database(path, "test-password")


def test_rejects_other_application_database(tmp_path):
    path = tmp_path / "calendar.db"
    password = "test-password"
    create_database(path, password)

    with closing(open_database(path, password)) as connection:
        with connection:
            connection.execute("PRAGMA application_id = 0")

    with pytest.raises(InvalidDatabaseError, match="CalendarDockのDB"):
        open_database(path, password)


def test_rejects_unsupported_schema_version(tmp_path):
    path = tmp_path / "calendar.db"
    password = "test-password"
    create_database(path, password)

    with closing(open_database(path, password)) as connection:
        with connection:
            connection.execute("PRAGMA user_version = 999")

    with pytest.raises(InvalidDatabaseError, match="バージョン"):
        open_database(path, password)


def test_rejects_missing_application_metadata(tmp_path):
    path = tmp_path / "calendar.db"
    password = "test-password"
    create_database(path, password)

    with closing(open_database(path, password)) as connection:
        with connection:
            connection.execute(
                "DELETE FROM app_metadata WHERE key = ?",
                ("application",),
            )

    with pytest.raises(InvalidDatabaseError, match="管理情報"):
        open_database(path, password)
