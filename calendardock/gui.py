"""CalendarDockの予定閲覧GUI。"""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date, timedelta
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from calendardock.repository import (
    get_event_detail,
    list_events_for_day,
)
from calendardock.search import search_events
from calendardock.editor import EventEditor
from calendardock.service import delete_event
from calendardock.window_settings import remember_window
from calendardock.startup import StartupDialog
from calendardock.importer import AlreadyImportedError, import_outlook_csv


class CalendarWindow:
    def __init__(self, root, connection):
        self.root = root
        self.connection = connection
        self.selected_day = date.today()
        self.display_month = self.selected_day.replace(day=1)

        root.title("CalendarDock")
        root.geometry("1100x800")
        root.minsize(900, 780)

        container = ttk.Frame(root, padding=12)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        left = ttk.Frame(container)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 16))

        navigation = ttk.Frame(left)
        navigation.pack(fill="x")
        ttk.Button(
            navigation,
            text="＜",
            width=4,
            command=lambda: self.change_month(-1),
        ).pack(side="left")

        self.month_label = ttk.Label(
            navigation, anchor="center", width=18
        )
        self.month_label.pack(side="left", expand=True)

        ttk.Button(
            navigation,
            text="＞",
            width=4,
            command=lambda: self.change_month(1),
        ).pack(side="right")

        self.calendar_frame = ttk.Frame(left)
        self.calendar_frame.pack(pady=10)

        ttk.Button(
            left, text="今日", command=self.go_today
        ).pack(fill="x")

        jump = ttk.Frame(left)
        jump.pack(fill="x", pady=(16, 0))
        ttk.Label(jump, text="日付（YYYY-MM-DD）").pack(anchor="w")

        self.date_input = ttk.Entry(jump)
        self.date_input.pack(fill="x", pady=4)
        self.date_input.bind("<Return>", lambda event: self.jump_to_date())
        ttk.Button(
            jump, text="移動", command=self.jump_to_date
        ).pack(fill="x")
        search_frame = ttk.LabelFrame(left, text="予定を検索", padding=8)
        search_frame.pack(fill="x", pady=(8, 0))

        ttk.Label(
            search_frame, text="件名・場所・内容"
        ).pack(anchor="w")

        self.search_input = ttk.Entry(search_frame)
        self.search_input.pack(fill="x", pady=4)
        self.search_input.bind(
            "<Return>", lambda event: self.run_search()
        )

        ttk.Button(
            search_frame,
            text="検索",
            command=self.run_search,
        ).pack(fill="x")

        ttk.Button(
            search_frame,
            text="選択日の一覧へ戻る",
            command=lambda: self.select_day(self.selected_day),
        ).pack(fill="x", pady=(6, 0))

        edit_buttons = ttk.LabelFrame(
            left, text="予定の登録・編集", padding=8
        )
        edit_buttons.pack(fill="x", pady=(8, 0))

        ttk.Button(
            edit_buttons,
            text="新規登録",
            command=self.new_event,
        ).pack(fill="x")

        ttk.Button(
            edit_buttons,
            text="選択した予定を編集",
            command=self.edit_event,
        ).pack(fill="x", pady=(6, 0))
        ttk.Button(
            edit_buttons,
            text="選択した予定を削除",
            command=self.delete_selected_event,
        ).pack(fill="x", pady=(6, 0))
        import_frame = ttk.LabelFrame(
            left, text="Outlookから移行", padding=8
        )
        import_frame.pack(fill="x", pady=(8, 0))

        ttk.Style(root).configure(
            "CalendarDock.Import.TButton",
            padding=(8, 6),
        )

        ttk.Button(
            import_frame,
            text="CSVを取り込む",
            command=self.import_csv,
            style="CalendarDock.Import.TButton",
        ).pack(fill="x")
        right = ttk.Frame(container)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=2)

        self.day_label = ttk.Label(right, font=("", 12, "bold"))
        self.day_label.grid(row=0, column=0, sticky="w", pady=(0, 8))

        list_frame = ttk.Frame(right)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.event_list = ttk.Treeview(
            list_frame,
            columns=("time", "subject", "location"),
            show="headings",
            selectmode="browse",
        )
        for column, label, width in (
            ("time", "時間", 160),
            ("subject", "件名", 330),
            ("location", "場所", 180),
        ):
            self.event_list.heading(column, text=label)
            self.event_list.column(column, width=width)

        self.event_list.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.event_list.yview
        )
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.event_list.configure(yscrollcommand=list_scroll.set)
        self.event_list.bind("<<TreeviewSelect>>", self.show_detail)

        notebook = ttk.Notebook(right)
        notebook.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.detail_text = self.add_text_tab(notebook, "予定詳細")
        self.source_text = self.add_text_tab(notebook, "Outlook移行元情報")

        self.render_month()
        self.select_day(self.selected_day)

    @staticmethod
    def add_text_tab(notebook, title):
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        text = tk.Text(
            frame, wrap="word", padx=10, pady=10, state="disabled"
        )
        scroll = ttk.Scrollbar(
            frame, orient="vertical", command=text.yview
        )
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.configure(yscrollcommand=scroll.set)
        return text

    @staticmethod
    def set_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def render_month(self):
        for widget in self.calendar_frame.winfo_children():
            widget.destroy()

        self.month_label.configure(
            text=f"{self.display_month.year}年"
                 f"{self.display_month.month:02d}月"
        )
        for column, weekday in enumerate("月火水木金土日"):
            ttk.Label(
                self.calendar_frame, text=weekday, anchor="center"
            ).grid(row=0, column=column, sticky="ew")

        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(
            self.display_month.year, self.display_month.month
        )
        for row, week in enumerate(weeks, start=1):
            for column, day_number in enumerate(week):
                if day_number == 0:
                    continue

                day = self.display_month.replace(day=day_number)
                label = (
                    f"[{day_number}]"
                    if day == self.selected_day
                    else str(day_number)
                )
                ttk.Button(
                    self.calendar_frame,
                    text=label,
                    width=4,
                    command=lambda selected=day: self.select_day(selected),
                ).grid(row=row, column=column, padx=1, pady=2)

    def change_month(self, offset):
        month_index = (
            self.display_month.year * 12
            + self.display_month.month - 1
            + offset
        )
        year, month = divmod(month_index, 12)
        if not 1 <= year <= 9999:
            return

        self.select_day(date(year, month + 1, 1))

    def go_today(self):
        self.select_day(date.today())

    def jump_to_date(self):
        try:
            value = self.date_input.get().strip()
            day = date.fromisoformat(value)
            if value != day.isoformat():
                raise ValueError
            if day == date.max:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "日付の確認",
                "日付をYYYY-MM-DD形式で入力してください。\n"
                "9999-12-31は指定できません。",
                parent=self.root,
            )
            return

        self.select_day(day)

    def select_day(self, day):
        self.selected_day = day
        self.display_month = day.replace(day=1)
        self.render_month()
        self.date_input.delete(0, "end")
        self.date_input.insert(0, day.isoformat())

        self.event_list.delete(*self.event_list.get_children())
        self.set_text(self.detail_text, "")
        self.set_text(self.source_text, "")

        try:
            events = list_events_for_day(self.connection, day)
        except Exception as exc:
            self.day_label.configure(
                text=f"{day.year}年{day.month:02d}月{day.day:02d}日"
            )
            messagebox.showerror(
                "予定取得エラー", str(exc), parent=self.root
            )
            return

        self.day_label.configure(
            text=f"{day.year}年{day.month:02d}月{day.day:02d}日"
                 f"  ―  {len(events)}件"
        )

        for event in events:
            if event.all_day:
                time_label = "終日"
            elif event.starts_at.date() == event.ends_at.date():
                time_label = (
                    f"{event.starts_at:%H:%M}～{event.ends_at:%H:%M}"
                )
            else:
                time_label = (
                    f"{event.starts_at:%m/%d %H:%M}～"
                    f"{event.ends_at:%m/%d %H:%M}"
                )

            self.event_list.insert(
                "",
                "end",
                iid=str(event.id),
                values=(
                    time_label,
                    event.subject or "（件名なし）",
                    event.location,
                ),
            )

    def new_event(self):
        editor = EventEditor(
            self.root, self.connection, self.selected_day
        )
        self.root.wait_window(editor)
        if editor.saved:
            self.select_day(self.selected_day)

    def edit_event(self):
        selection = self.event_list.selection()
        if not selection:
            messagebox.showinfo(
                "予定の編集",
                "編集する予定を一覧から選択してください。",
                parent=self.root,
            )
            return

        try:
            detail = get_event_detail(
                self.connection, int(selection[0])
            )
        except Exception as exc:
            messagebox.showerror(
                "詳細取得エラー", str(exc), parent=self.root
            )
            return

        if detail is None:
            messagebox.showinfo(
                "予定の編集",
                "予定が見つかりません。",
                parent=self.root,
            )
            return

        editor = EventEditor(
            self.root,
            self.connection,
            self.selected_day,
            detail=detail,
        )
        self.root.wait_window(editor)
        if editor.saved:
            self.select_day(self.selected_day)

    def delete_selected_event(self):
        selection = self.event_list.selection()
        if not selection:
            messagebox.showinfo(
                "予定の削除",
                "削除する予定を一覧から選択してください。",
                parent=self.root,
            )
            return

        try:
            detail = get_event_detail(
                self.connection, int(selection[0])
            )
        except Exception as exc:
            messagebox.showerror(
                "詳細取得エラー", str(exc), parent=self.root
            )
            return

        if detail is None:
            messagebox.showinfo(
                "予定の削除",
                "予定が見つかりません。",
                parent=self.root,
            )
            return

        confirmed = messagebox.askyesno(
            "予定の削除",
            f"次の予定を削除しますか？\n\n"
            f"{detail.subject or '（件名なし）'}\n"
            f"{detail.starts_at:%Y-%m-%d %H:%M}\n\n"
            "削除すると通常の一覧・検索には表示されなくなります。",
            parent=self.root,
        )
        if not confirmed:
            return

        try:
            delete_event(self.connection, detail.id)
        except Exception as exc:
            messagebox.showerror(
                "削除できません", str(exc), parent=self.root
            )
            return

        self.select_day(self.selected_day)

    def import_csv(self):
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Outlook予定表CSVを選択",
            filetypes=[
                ("CSVファイル", "*.csv"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if not selected:
            return

        confirmed = messagebox.askyesno(
            "CSV取込",
            "選択したCSVを、現在開いているDBへ取り込みます。\n\n"
            "CSV内の予定は、重複して見えるものもすべて保存します。\n"
            "同じデータの取込済みCSVは再取り込みできません。\n\n"
            "取り込みを開始しますか？",
            parent=self.root,
        )
        if not confirmed:
            return

        self.root.configure(cursor="watch")
        self.root.update_idletasks()

        try:
            result = import_outlook_csv(self.connection, selected)
        except AlreadyImportedError as exc:
            messagebox.showinfo(
                "取込済み", str(exc), parent=self.root
            )
            return
        except Exception as exc:
            messagebox.showerror(
                "CSVを取り込めません",
                str(exc),
                parent=self.root,
            )
            return
        finally:
            self.root.configure(cursor="")

        self.select_day(self.selected_day)

        messagebox.showinfo(
            "CSV取込完了",
            f"{result.imported_count:,}件の予定を取り込みました。",
            parent=self.root,
        )


    def run_search(self):
        query = self.search_input.get().strip()
        if not query:
            messagebox.showinfo(
                "検索",
                "検索語を入力してください。",
                parent=self.root,
            )
            return

        try:
            events = search_events(self.connection, query)
        except Exception as exc:
            messagebox.showerror(
                "検索エラー", str(exc), parent=self.root
            )
            return

        self.event_list.delete(*self.event_list.get_children())
        self.set_text(self.detail_text, "")
        self.set_text(self.source_text, "")
        self.day_label.configure(
            text=f"検索結果: {query}  ―  {len(events)}件"
        )

        for event in events:
            if event.all_day:
                time_label = f"{event.starts_at:%Y-%m-%d} 終日"
            else:
                time_label = f"{event.starts_at:%Y-%m-%d %H:%M}"

            self.event_list.insert(
                "",
                "end",
                iid=str(event.id),
                values=(
                    time_label,
                    event.subject or "（件名なし）",
                    event.location,
                ),
            )


    def show_detail(self, _event=None):
        selection = self.event_list.selection()
        if not selection:
            return

        try:
            detail = get_event_detail(
                self.connection, int(selection[0])
            )
        except Exception as exc:
            messagebox.showerror(
                "詳細取得エラー", str(exc), parent=self.root
            )
            return

        if detail is None:
            self.set_text(self.detail_text, "予定が見つかりません。")
            self.set_text(self.source_text, "")
            return

        if detail.all_day:
            # 終日予定の終了は翌日0時のため、最終日として表示する。
            last_day = (
                (detail.ends_at - timedelta(days=1)).date()
                if detail.ends_at > detail.starts_at
                else detail.starts_at.date()
            )
            period = (
                f"{detail.starts_at:%Y-%m-%d} ～ "
                f"{last_day:%Y-%m-%d}（終日）"
            )
        else:
            period = (
                f"{detail.starts_at:%Y-%m-%d %H:%M} ～ "
                f"{detail.ends_at:%Y-%m-%d %H:%M}"
            )

        self.set_text(
            self.detail_text,
            f"件名: {detail.subject or '（件名なし）'}\n"
            f"日時: {period}\n"
            f"場所: {detail.location}\n"
            f"分類: {detail.categories}\n\n"
            f"内容:\n{detail.body}",
        )

        if detail.source_fields is None:
            self.set_text(
                self.source_text,
                "CalendarDockで新規登録した予定です。\n"
                "Outlook移行元情報はありません。",
            )
            return

        source = (
            f"元ファイル: {detail.source_name}\n"
            f"CSVレコード番号: {detail.source_row}\n\n"
        )
        source += "\n\n".join(
            f"{key}:\n{value}"
            for key, value in detail.source_fields.items()
        )
        self.set_text(self.source_text, source)


def main():
    root = tk.Tk()
    root.withdraw()

    icon_path = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "CalendarDock.ico"
    )
    if icon_path.is_file():
        root.iconbitmap(default=str(icon_path))

    connection = None

    try:
        startup = StartupDialog(root)
        root.wait_window(startup)

        connection = startup.connection
        if connection is None:
            return

        CalendarWindow(root, connection)
        root.title(f"CalendarDock — {startup.db_path.name}")

        remember_window(root, "main", default=(1100, 800))
        root.deiconify()
        root.mainloop()

    finally:
        if connection is not None:
            connection.close()
        try:
            root.destroy()
        except tk.TclError:
            pass
