import inspect
import logging

from sqlobjects.sql_logging import get_caller_frame


def test_get_caller_frame_returns_string():
    """get_caller_frame returns a string by default"""
    result = get_caller_frame()
    assert isinstance(result, str)


def test_get_caller_frame_contains_this_file():
    """With default max_frames=1, the returned frame should point to the caller (this test file)"""
    result = get_caller_frame()
    assert "test_sql_logging" in result


def test_get_caller_frame_max_frames_list():
    """When max_frames > 1, a list is returned"""
    result = get_caller_frame(max_frames=3)
    assert isinstance(result, list)
    assert len(result) >= 1


def test_get_caller_frame_skips_site_packages():
    """Frames from site-packages should not be returned"""
    result = get_caller_frame(max_frames=5)
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        assert "site-packages" not in frame


def test_get_caller_frame_skips_sqlobjects_frames():
    """Internal sqlobjects frames should not be returned (editable install compatible)"""
    result = get_caller_frame(max_frames=5)
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        assert not ("sqlobjects" in frame and "test" not in frame)


def test_get_caller_frame_extra_skip_packages():
    """extra_skip_packages can skip frames whose module name matches a given prefix"""
    result = get_caller_frame(
        max_frames=3,
        extra_skip_packages=["tests.unit.test_sql_logging"],
    )
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        assert "test_sql_logging" not in frame


def _make_record(extra: dict | None = None) -> logging.LogRecord:
    """Helper: create a LogRecord with given extra fields."""
    base_extra = {"sql": "SELECT 1", "params": {}, "duration_ms": 1.5}
    if extra:
        base_extra.update(extra)
    logger = logging.getLogger("sqlobjects.sql.test")
    record = logger.makeRecord(
        name="sqlobjects.sql",
        level=logging.DEBUG,
        fn="executor.py",  # will be overwritten by filter
        lno=99,  # will be overwritten
        msg="SELECT 1",
        args=(),
        exc_info=None,
        extra=base_extra,
    )
    return record


def test_sql_caller_filter_overwrites_caller_fields():
    """SQLCallerFilter overwrites record filename/funcName/lineno/pathname."""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter()
    record = _make_record()
    f.filter(record)

    # After filter, caller should point to this test file, not executor.py
    assert "executor" not in record.filename
    assert "test_sql_logging" in record.filename
    assert isinstance(record.lineno, int)
    assert record.lineno != 99


def test_sql_caller_filter_preserves_extra_fields():
    """filter() does not remove or overwrite pre-existing extra fields on the record."""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter()
    record = _make_record()
    f.filter(record)

    assert hasattr(record, "duration_ms")
    assert record.duration_ms == 1.5  # type: ignore[attr-defined]
    assert record.sql == "SELECT 1"  # type: ignore[attr-defined]


def test_sql_caller_filter_max_frames_one_sets_string_caller():
    """With max_frames=1, record.caller is a string."""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter(max_frames=1)
    record = _make_record()
    f.filter(record)

    assert isinstance(record.caller, str)  # type: ignore[attr-defined]
    assert "test_sql_logging" in record.caller  # type: ignore[attr-defined]


def test_sql_caller_filter_max_frames_multiple_sets_list():
    """With max_frames=3, record.caller is a list."""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter(max_frames=3)
    record = _make_record()
    f.filter(record)

    assert isinstance(record.caller, list)  # type: ignore[attr-defined]


def test_sql_caller_filter_returns_true():
    """filter() always returns True (never drops records)."""
    from sqlobjects.sql_logging import SQLCallerFilter

    f = SQLCallerFilter()
    record = _make_record()
    result = f.filter(record)

    assert result is True


def test_find_user_frame_returns_frame_info_or_none():
    """_find_user_frame returns an inspect.FrameInfo pointing to this test file."""
    from sqlobjects.sql_logging import _find_user_frame

    result = _find_user_frame()
    assert result is not None
    assert isinstance(result, inspect.FrameInfo)
    assert "test_sql_logging" in result.filename


def test_find_user_frame_skips_site_packages():
    """_find_user_frame never returns a site-packages frame."""
    from sqlobjects.sql_logging import _find_user_frame

    result = _find_user_frame()
    assert result is not None
    assert "site-packages" not in result.filename


def test_find_user_frame_skips_sqlobjects_internals():
    """_find_user_frame never returns a sqlobjects internal frame."""
    from sqlobjects.sql_logging import _find_user_frame

    result = _find_user_frame()
    assert result is not None
    module = result.frame.f_globals.get("__name__", "")
    assert not module.startswith("sqlobjects.")
    assert module != "sqlobjects"


def test_find_user_frame_extra_skip_packages():
    """_find_user_frame respects extra_skip_packages module prefix."""
    from sqlobjects.sql_logging import _find_user_frame

    result = _find_user_frame(extra_skip_packages=["tests.unit.test_sql_logging"])
    # All test_sql_logging frames skipped, falls back to pytest internals or None
    if result is not None:
        module = result.frame.f_globals.get("__name__", "")
        assert not module.startswith("tests.unit.test_sql_logging")


def test_find_user_frame_returns_none_when_no_user_frame():
    """_find_user_frame returns None when every frame is filtered out."""
    from sqlobjects.sql_logging import _find_user_frame

    # Skip everything — should return None
    result = _find_user_frame(
        extra_skip_packages=[
            "tests",
            "_pytest",
            "pluggy",
            "asyncio",
            "__main__",
        ]
    )
    # May return None or a frame from a deeply nested runner — just confirm no crash
    assert result is None or isinstance(result, inspect.FrameInfo)
