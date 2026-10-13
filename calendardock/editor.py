"""予定の新規登録・編集で共用する入力画面。"""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, time, timedelta
from tkinter import messagebox, ttk

from calendardock.service import EventDraft, create_event, update_event
from calendardock.window_settings import remember_window


class EventEditor(tk.Toplevel):
    def __init__(
        self, parent, connection, selected_day, detail=None
    ):
        super().__init__(parent)
        self.withdraw()
        self.connection = connection
        self.detail = detail
        self.saved = False

        self.title("予定の編集" if detail else "予定の新規登録")
        self.geometry("620x620")
        self.minsize(540, 560)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(7, weight=1)

        self.subject = tk.StringVar(
            value=detail.subject if detail else ""
        )
        self.all_day = tk.BooleanVar(
            value=detail.all_day if detail else False
        )
        self.location = tk.StringVar(
            value=detail.location if detail else ""
        )
        self.categories = tk.StringVar(
            value=detail.categories if detail else ""
        )

        if detail:
            start = detail.starts_at
            end = detail.ends_at
            if detail.all_day and end > start:
                end -= timedelta(days=1)
        else:
            start = datetime.combine(selected_day, time(9))
            end = datetime.combine(selected_day, time(10))

        self.start_date = tk.StringVar(value=start.date().isoformat())
        self.end_date = tk.StringVar(value=end.date().isoformat())
        self.start_time = tk.StringVar(value=start.strftime("%H:%M:%S"))
        self.end_time = tk.StringVar(value=end.strftime("%H:%M:%S"))

        ttk.Label(frame, text="件名").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=6
        )
        subject_entry = ttk.Entry(frame, textvariable=self.subject)
        subject_entry.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(
            frame,
            text="終日予定",
            variable=self.all_day,
            command=self.toggle_times,
        ).grid(row=1, column=1, sticky="w", pady=6)

        self.start_time_entry = self.add_datetime_row(
            frame, 2, "開始", self.start_date, self.start_time
        )
        self.end_time_entry = self.add_datetime_row(
            frame, 3, "終了", self.end_date, self.end_time
        )

        ttk.Label(
            frame,
            text="日付: YYYY-MM-DD　時刻: HH:MM または HH:MM:SS\n"
                 "終日予定の終了日は、予定の最終日を入力します。",
        ).grid(row=4, column=1, sticky="w", pady=6)

        for row, label, variable in (
            (5, "場所", self.location),
            (6, "分類", self.categories),
        ):
            ttk.Label(frame, text=label).grid(
                row=row, column=0, sticky="w", pady=6
            )
            ttk.Entry(frame, textvariable=variable).grid(
                row=row, column=1, sticky="ew", pady=6
            )

        ttk.Label(frame, text="内容").grid(
            row=7, column=0, sticky="nw", pady=6
        )
        body_frame = ttk.Frame(frame)
        body_frame.grid(row=7, column=1, sticky="nsew", pady=6)

        self.body = tk.Text(body_frame, wrap="word", height=10)
        scroll = ttk.Scrollbar(
            body_frame, orient="vertical", command=self.body.yview
        )
        scroll.pack(side="right", fill="y")
        self.body.pack(fill="both", expand=True)
        self.body.configure(yscrollcommand=scroll.set)
        if detail:
            self.body.insert("1.0", detail.body)

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=1, sticky="e", pady=(12, 0))
        ttk.Button(
            buttons, text="キャンセル", command=self.destroy
        ).pack(side="left", padx=6)
        ttk.Button(
            buttons, text="保存", command=self.save
        ).pack(side="left")

        self.toggle_times()
        self.bind("<Escape>", lambda event: self.destroy())
        remember_window(
            self,
            "event_editor",
            default=(620, 620),
            parent=parent,
        )
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        subject_entry.focus_set()

    @staticmethod
    def add_datetime_row(frame, row, label, date_var, time_var):
        ttk.Label(frame, text=label).grid(
            row=row, column=0, sticky="w", pady=6
        )
        fields = ttk.Frame(frame)
        fields.grid(row=row, column=1, sticky="w", pady=6)

        ttk.Entry(
            fields, textvariable=date_var, width=14
        ).pack(side="left")

        time_entry = ttk.Entry(
            fields, textvariable=time_var, width=12
        )
        time_entry.pack(side="left", padx=(10, 0))
        return time_entry

    def toggle_times(self):
        state = "disabled" if self.all_day.get() else "normal"
        self.start_time_entry.configure(state=state)
        self.end_time_entry.configure(state=state)

    @staticmethod
    def parse_date(value):
        value = value.strip()
        result = date.fromisoformat(value)
        if value != result.isoformat():
            raise ValueError
        return result

    @staticmethod
    def parse_time(value):
        value = value.strip()
        for format_string in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, format_string).time()
            except ValueError:
                pass
        raise ValueError

    def save(self):
        try:
            start_date = self.parse_date(self.start_date.get())
            end_date = self.parse_date(self.end_date.get())

            # 日別一覧の計算で翌日が必要になるため、この日は除外する。
            if start_date == date.max or end_date == date.max:
                raise ValueError

            if self.all_day.get():
                starts_at = datetime.combine(start_date, time.min)
                ends_at = datetime.combine(
                    end_date + timedelta(days=1), time.min
                )
                if end_date < start_date:
                    raise ValueError
            else:
                starts_at = datetime.combine(
                    start_date, self.parse_time(self.start_time.get())
                )
                ends_at = datetime.combine(
                    end_date, self.parse_time(self.end_time.get())
                )
        except (ValueError, OverflowError):
            messagebox.showerror(
                "日時の確認",
                "開始・終了の日付と時刻を確認してください。\n"
                "日付はYYYY-MM-DD、時刻はHH:MMまたはHH:MM:SSです。\n"
                "終日予定の終了日は開始日以降を指定してください。\n"
                "9999-12-31は指定できません。",
                parent=self,
            )
            return

        draft = EventDraft(
            subject=self.subject.get(),
            starts_at=starts_at,
            ends_at=ends_at,
            all_day=self.all_day.get(),
            location=self.location.get(),
            body=self.body.get("1.0", "end-1c"),
            categories=self.categories.get(),
        )

        try:
            if self.detail is None:
                create_event(self.connection, draft)
            else:
                update_event(self.connection, self.detail.id, draft)
        except Exception as exc:
            messagebox.showerror(
                "保存できません", str(exc), parent=self
            )
            return

        self.saved = True
        self.destroy()
