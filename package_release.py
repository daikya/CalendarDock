"""ビルド済みCalendarDockを文書付きZIPへまとめる。"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path


DOCUMENTS = (
    "DISTRIBUTION_README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
)

PERSONAL_FILE_PATTERN = re.compile(
    r"\.(csv|db|sqlite|sqlite3)(-wal|-shm|-journal)?$",
    re.IGNORECASE,
)


def package_release(project_dir: Path, version: str) -> Path:
    """配布ZIPを作成する。ビルド自体は行わない。"""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("バージョンは1.0.0のように指定してください。")

    project_dir = Path(project_dir)
    bundle = project_dir / "dist" / "CalendarDock"
    executable = bundle / "CalendarDock.exe"

    if not executable.is_file():
        raise FileNotFoundError(f"ビルド済みexeがありません: {executable}")
    if not (bundle / "_internal").is_dir():
        raise FileNotFoundError("_internalフォルダーがありません。")

    documents = []
    for name in DOCUMENTS:
        path = project_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"同梱文書がないか空です: {name}")
        documents.append(path)

    # ZIP作成前に、対象ファイルを確認する。
    entries = []
    for path in sorted(bundle.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"リンクは同梱できません: {path}")
        if not path.is_file():
            continue

        relative = path.relative_to(bundle)
        if PERSONAL_FILE_PATTERN.search(path.name):
            raise ValueError(
                f"個人データの可能性があるファイルがあります: {relative}"
            )

        # ビルド先に残った旧文書は使わず、プロジェクト直下から同梱。
        if (
            len(relative.parts) == 1
            and relative.name.casefold()
            in {name.casefold() for name in DOCUMENTS}
        ):
            continue

        entries.append((path, Path("CalendarDock") / relative))

    for path in documents:
        entries.append((path, Path("CalendarDock") / path.name))

    output = (
        project_dir / "dist"
        / f"CalendarDock-v{version}-Windows-x64.zip"
    )

    # 既存ZIPは上書きしない。
    created = False
    try:
        with zipfile.ZipFile(
            output, "x", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            created = True
            for source, destination in entries:
                archive.write(source, destination.as_posix())

        with zipfile.ZipFile(output) as archive:
            bad_file = archive.testzip()
            if bad_file is not None:
                raise ValueError(f"ZIP検証に失敗しました: {bad_file}")

            required = {
                "CalendarDock/CalendarDock.exe",
                *{
                    f"CalendarDock/{name}"
                    for name in DOCUMENTS
                },
            }
            if not required.issubset(archive.namelist()):
                raise ValueError("ZIPに必須ファイルが含まれていません。")

    except Exception:
        if created:
            output.unlink(missing_ok=True)
        raise

    return output


def main():
    parser = argparse.ArgumentParser(
        description="CalendarDockの配布ZIPを作成します。"
    )
    parser.add_argument(
        "--version",
        required=True,
        help="配布バージョン。例: 1.0.0",
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    output = package_release(project_dir, args.version)

    print("配布ZIP作成完了:", output)
    print("利用説明・MITライセンス・第三者通知: 同梱済み")
    print("ZIP整合性: OK")


if __name__ == "__main__":
    main()
