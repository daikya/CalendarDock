import zipfile

import pytest

from package_release import DOCUMENTS, package_release


@pytest.fixture
def project(tmp_path):
    bundle = tmp_path / "dist" / "CalendarDock"
    internal = bundle / "_internal"
    internal.mkdir(parents=True)

    (bundle / "CalendarDock.exe").write_bytes(b"test executable")
    (internal / "python312.dll").write_bytes(b"test runtime")

    for name in DOCUMENTS:
        (tmp_path / name).write_text(
            f"current {name}", encoding="utf-8"
        )

    return tmp_path


def test_packages_runtime_and_current_documents(project):
    bundle = project / "dist" / "CalendarDock"
    (bundle / "LICENSE").write_text("old license", encoding="utf-8")

    output = package_release(project, "1.0.0")

    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert "CalendarDock/CalendarDock.exe" in archive.namelist()
        assert (
            "CalendarDock/_internal/python312.dll"
            in archive.namelist()
        )

        for name in DOCUMENTS:
            assert archive.read(
                f"CalendarDock/{name}"
            ).decode("utf-8") == f"current {name}"

        assert len(archive.namelist()) == 5


def test_rejects_missing_document(project):
    (project / "THIRD_PARTY_NOTICES.md").unlink()

    with pytest.raises(FileNotFoundError, match="THIRD_PARTY_NOTICES"):
        package_release(project, "1.0.0")

    assert not (
        project / "dist" / "CalendarDock-v1.0.0-Windows-x64.zip"
    ).exists()


def test_rejects_personal_database(project):
    bundle = project / "dist" / "CalendarDock"
    (bundle / "calendar.db").write_bytes(b"personal data")

    with pytest.raises(ValueError, match="個人データ"):
        package_release(project, "1.0.0")

    assert not (
        project / "dist" / "CalendarDock-v1.0.0-Windows-x64.zip"
    ).exists()


def test_does_not_overwrite_existing_zip(project):
    output = package_release(project, "1.0.0")
    before = output.read_bytes()

    with pytest.raises(FileExistsError):
        package_release(project, "1.0.0")

    assert output.read_bytes() == before


def test_rejects_invalid_version(project):
    with pytest.raises(ValueError, match="バージョン"):
        package_release(project, "../invalid")

    assert list((project / "dist").glob("*.zip")) == []
