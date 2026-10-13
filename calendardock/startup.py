"""DBの選択・新規作成を行う起動画面。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from calendardock.database import (
    create_calendar_database,
    open_database,
)
from calendardock.window_settings import remember_window


class StartupDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.connection = None
        self.db_path = None

        self.title("CalendarDock — DBを開く")
        self.minsize(420, 240)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        frame = ttk.Frame(self, padding=24)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame, text="CalendarDock", font=("", 16, "bold")
        ).pack(pady=(0, 12))

        ttk.Label(
            frame,
            text="使用する予定表のDBを選択してください。",
        ).pack(pady=(0, 16))

        ttk.Button(
            frame,
            text="既存DBを開く",
            command=self.open_existing,
        ).pack(fill="x", pady=4)

        ttk.Button(
            frame,
            text="DBを新規作成",
            command=self.create_new,
        ).pack(fill="x", pady=4)

        ttk.Button(
            frame,
            text="終了",
            command=self.destroy,
        ).pack(fill="x", pady=(12, 0))

        remember_window(self, "startup", default=(460, 300))
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        self.focus_set()

    @staticmethod
    def initial_directory():
        directory = Path.home() / "Documents"
        return directory if directory.is_dir() else Path.home()

    def open_existing(self):
        selected = filedialog.askopenfilename(
            parent=self,
            title="CalendarDockのDBを選択",
            initialdir=self.initial_directory(),
            filetypes=[
                ("CalendarDock DB", "*.db"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if not selected:
            return

        password = simpledialog.askstring(
            "DBを開く",
            "DBのパスワードを入力してください。",
            show="*",
            parent=self,
        )
        if password is None:
            return

        try:
            connection = open_database(selected, password)
        except Exception as exc:
            messagebox.showerror(
                "DBを開けません", str(exc), parent=self
            )
            return

        # この画面からは、登録・編集・削除に対応したDBだけを開く。
        try:
            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
        except Exception as exc:
            connection.close()
            messagebox.showerror(
                "DB確認エラー", str(exc), parent=self
            )
            return

        if version != 3:
            connection.close()
            messagebox.showerror(
                "DB構造の確認",
                "このDBは構造更新が必要です。\n"
                f"現在のバージョン: {version}\n"
                "バージョン3へ更新してから開いてください。",
                parent=self,
            )
            return

        self.connection = connection
        self.db_path = Path(selected)
        self.destroy()

    def create_new(self):
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="新しいDBの保存先",
            initialdir=self.initial_directory(),
            initialfile="calendar.db",
            defaultextension=".db",
            filetypes=[("CalendarDock DB", "*.db")],
        )
        if not selected:
            return

        path = Path(selected)
        if path.exists():
            messagebox.showerror(
                "DBを作成できません",
                "既存ファイルは上書きできません。\n"
                "別のファイル名を指定してください。",
                parent=self,
            )
            return

        password = simpledialog.askstring(
            "DBを新規作成",
            "新しいDBのパスワードを入力してください。",
            show="*",
            parent=self,
        )
        if password is None:
            return

        confirmation = simpledialog.askstring(
            "パスワード確認",
            "確認のため、もう一度入力してください。",
            show="*",
            parent=self,
        )
        if confirmation is None:
            return

        if password != confirmation:
            messagebox.showerror(
                "パスワード確認",
                "パスワードが一致しません。",
                parent=self,
            )
            return

        try:
            create_calendar_database(path, password)
            connection = open_database(path, password)
        except Exception as exc:
            messagebox.showerror(
                "DBを作成できません", str(exc), parent=self
            )
            return

        self.connection = connection
        self.db_path = path
        self.destroy()
