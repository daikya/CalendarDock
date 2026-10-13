# CalendarDock

OutlookからCSV出力した予定表を移行し、パスワード付きの暗号化SQLite DBで管理する、個人向けのWindowsデスクトップアプリです。

Python・Tkinter・SQLCipherで作成しています。PSTファイルを直接読み取る機能はありません。

## 主な機能

- 暗号化DBの新規作成・選択・パスワードでの接続。
- Outlook予定表CSVの一括取り込み（CP932・UTF-8）。
- 月間カレンダー、日別の予定一覧、予定詳細の表示。
- 件名・場所・内容の検索。全角・半角と英字の大文字・小文字を正規化。
- 予定の新規登録・編集・論理削除。
- 終日予定・日付をまたぐ予定への対応。
- 元CSV情報の保持・表示。
- 各画面の位置・サイズの保存と復元。

通知・繰り返し規則・クラウド同期は実装していません。削除済み予定の復元画面と完全削除機能もありません。

## Windows版の利用

1. 配布ZIPをすべて展開します。
2. `CalendarDock`フォルダー内の`CalendarDock.exe`を起動します。
3. 「DBを新規作成」または「既存DBを開く」を選択します。

exe利用時はPythonやOutlookのインストールは不要です。`_internal`等を含むフォルダー全体を保持してください。

動作確認環境はWindows 11 x64です。その他の環境での動作は未確認です。

詳しい操作方法は[利用説明](DISTRIBUTION_README.md)をご覧ください。

## データの扱い

- DBはSQLCipherで暗号化します。パスワードを忘れた場合の復旧機能はありません。
- DBの保存先は利用者が選択します。パスワードは設定ファイルに保存しません。
- バックアップはアプリを終了してからDBファイルをコピーしてください。
- 元CSVは暗号化されていないため、別途管理してください。
- CSV内の重複して見える予定も保存します。同一データ・同一行順の再取込は拒否しますが、異なるCSV間の予定単位の重複照合はしません。
- CSV由来の予定を編集しても、元CSV情報を保持します。
- 削除は`is_deleted`による論理削除で、通常の一覧・検索から除外します。

画面設定の保存先は`%LOCALAPPDATA%\CalendarDock\window_settings.json`です。

## 開発環境

WindowsのPowerShellで、プロジェクトのルートから実行します。開発時の確認環境はPython 3.12.0です。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m calendardock
```

実行時の外部依存は`sqlcipher3==0.6.3`です。開発・ビルド時はpytestとPyInstallerも使用します。依存関係は`requirements.txt`と`requirements-dev.txt`で管理します。

## テスト

```powershell
python -m pytest -q
```

CSV読取、暗号化、構造更新、取り込み、一覧・詳細、検索、登録・編集・削除、画面設定、配布ZIP作成をテストしています。GUI操作とexeの動作は別途実機で確認します。

## Windows版のビルドとZIP作成

アプリを終了してから、Windowsの開発環境で実行します。

```powershell
python -m PyInstaller --noconfirm --clean --onedir --windowed --name CalendarDock --collect-all sqlcipher3 --icon assets\CalendarDock.ico --add-data "assets;assets" run_calendardock.py
python package_release.py --version 1.0.0
```

生成先:

- アプリ: `dist\CalendarDock\CalendarDock.exe`
- 配布ZIP: `dist\CalendarDock-v1.0.0-Windows-x64.zip`

ZIPには利用説明・MITライセンス・第三者通知を同梱します。既存の同名ZIPは上書きしません。`package_release.py`はビルド済みフォルダーを梱包する処理であり、exeの再ビルドは行いません。

ソース変更時は、先にexeを再ビルドしてください。配布対象フォルダーへ個人用CSV・DB・バックアップを置かないでください。

## 文書

- [利用説明](DISTRIBUTION_README.md)
- [DBのテーブル構造・項目の意味・Outlook CSVとの対応](docs/Database_Layout.md)
- [第三者ソフトウェアの通知](THIRD_PARTY_NOTICES.md)

通常利用の新規DBは構造バージョン3で作成します。旧DBの構造更新と開発時の移行スクリプトについては、DB仕様書を参照してください。

## ライセンス

CalendarDock本体は[MIT License](LICENSE)です。同梱ライブラリには、それぞれのライセンスが適用されます。詳細は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。
