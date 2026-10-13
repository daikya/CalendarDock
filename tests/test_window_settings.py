from calendardock.window_settings import (
    choose_geometry,
    load_settings,
    save_window_settings,
)


def test_initial_geometry_is_centered():
    result = choose_geometry(
        None, 1920, 1080, (1100, 720), (960, 540)
    )

    assert result == {
        "width": 1100,
        "height": 720,
        "x": 410,
        "y": 180,
    }


def test_restores_saved_geometry():
    saved = {"width": 1000, "height": 650, "x": 120, "y": 90}

    assert choose_geometry(
        saved, 1920, 1080, (1100, 720), (960, 540)
    ) == saved


def test_moves_offscreen_geometry_back_inside_screen():
    result = choose_geometry(
        {"width": 1000, "height": 650, "x": 4000, "y": -500},
        1920,
        1080,
        (1100, 720),
        (960, 540),
    )

    assert result["x"] == 920
    assert result["y"] == 0


def test_invalid_saved_geometry_uses_center():
    result = choose_geometry(
        {"width": "invalid"},
        1920,
        1080,
        (1100, 720),
        (960, 540),
    )

    assert result["x"] == 410
    assert result["y"] == 180


def test_saves_main_and_editor_separately(tmp_path):
    path = tmp_path / "settings" / "window_settings.json"
    main = {"width": 1100, "height": 720, "x": 100, "y": 80}
    editor = {"width": 620, "height": 620, "x": 300, "y": 150}

    save_window_settings(path, "main", main)
    save_window_settings(path, "event_editor", editor)

    assert load_settings(path) == {
        "main": main,
        "event_editor": editor,
    }


def test_corrupt_settings_are_ignored(tmp_path):
    path = tmp_path / "window_settings.json"
    path.write_text("{broken", encoding="utf-8")

    assert load_settings(path) == {}
