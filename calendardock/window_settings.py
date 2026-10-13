"""ウィンドウの位置・サイズの保存と復元。"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
import ctypes
from ctypes import wintypes


logger = logging.getLogger(__name__)


def settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "CalendarDock" / "window_settings.json"
    return Path.home() / ".calendardock" / "window_settings.json"


def load_settings(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_window_settings(path: Path, key: str, geometry: dict) -> None:
    data = load_settings(path)
    data[key] = geometry
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix="window_settings_",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)

        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def choose_geometry(saved, screen_width, screen_height, default, center):
    """保存済み値または中央位置を、画面内に収まるよう補正する。"""
    valid = (
        isinstance(saved, dict)
        and all(
            type(saved.get(name)) is int
            for name in ("width", "height", "x", "y")
        )
        and saved["width"] > 0
        and saved["height"] > 0
    )

    if valid:
        width = saved["width"]
        height = saved["height"]
    else:
        width, height = default

    width = min(max(width, 200), screen_width)
    height = min(
        max(height, 200),
        800,
        max(200, screen_height - 80),
    )

    if valid:
        x, y = saved["x"], saved["y"]
    else:
        x = center[0] - width // 2
        y = center[1] - height // 2

    x = max(0, min(x, screen_width - width))
    y = max(0, min(y, max(0, screen_height - height - 40)))

    return {"width": width, "height": height, "x": x, "y": y}


def get_work_area(window):
    """タスクバーを除いた画面領域を取得する。"""
    if os.name == "nt":
        rect = wintypes.RECT()
        succeeded = ctypes.windll.user32.SystemParametersInfoW(
            0x0030,  # SPI_GETWORKAREA
            0,
            ctypes.byref(rect),
            0,
        )
        if succeeded:
            return rect.left, rect.top, rect.right, rect.bottom

    return (
        0,
        0,
        window.winfo_screenwidth(),
        window.winfo_screenheight() - 80,
    )


def remember_window(window, key, default, parent=None):
    """表示前に呼び出す。位置を復元し、閉じる際に保存する。"""
    path = settings_path()
    window.update_idletasks()

    left, top, right, bottom = get_work_area(window)
    work_width = right - left
    work_height = bottom - top

    if parent is not None and parent.winfo_viewable():
        center = (
            parent.winfo_rootx() + parent.winfo_width() // 2 - left,
            parent.winfo_rooty() + parent.winfo_height() // 2 - top,
        )
    else:
        center = (work_width // 2, work_height // 2)

    saved = load_settings(path).get(key)

    # 保存位置は画面座標なので、作業領域内の座標へ変換する。
    if isinstance(saved, dict):
        saved = dict(saved)
        if type(saved.get("x")) is int:
            saved["x"] -= left
        if type(saved.get("y")) is int:
            saved["y"] -= top

    geometry = choose_geometry(
        saved,
        work_width,
        work_height,
        default,
        center,
    )

    geometry["x"] += left
    geometry["y"] += top

    window.geometry(
        f'{geometry["width"]}x{geometry["height"]}'
        f'+{geometry["x"]}+{geometry["y"]}'
    )

    latest = dict(geometry)

    def on_configure(event):
        if event.widget is not window:
            return

        # 最大化・最小化時の値で、通常表示の位置を上書きしない。
        if window.state() != "normal":
            return

        latest.update(
            width=window.winfo_width(),
            height=window.winfo_height(),
            x=window.winfo_x(),
            y=window.winfo_y(),
        )

    def on_destroy(event):
        if event.widget is not window:
            return

        try:
            save_window_settings(path, key, latest)
        except OSError:
            logger.exception("ウィンドウ設定を保存できませんでした。")

    window.bind("<Configure>", on_configure, add="+")
    window.bind("<Destroy>", on_destroy, add="+")
