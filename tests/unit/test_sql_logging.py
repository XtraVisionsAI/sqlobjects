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
    """_find_user_frame skips all frames matching extra_skip_packages prefix."""
    from sqlobjects.sql_logging import _find_user_frame

    result = _find_user_frame(extra_skip_packages=["tests.unit.test_sql_logging"])
    # The test module frames are skipped; result is None or an outer runner frame
    if result is not None:
        module = result.frame.f_globals.get("__name__", "")
        assert not module.startswith("tests.unit.test_sql_logging"), (
            f"Expected non-test-module frame, got module={module!r}"
        )


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
    assert result is None


def test_should_skip_frame_skips_site_packages():
    """_should_skip_frame returns True for site-packages paths."""
    from sqlobjects.sql_logging import _should_skip_frame

    assert (
        _should_skip_frame(
            filepath="/usr/lib/python3.12/site-packages/sqlalchemy/orm.py",
            module="sqlalchemy.orm",
            extra_skip_prefixes=(),
        )
        is True
    )


def test_should_skip_frame_skips_internal_modules():
    """_should_skip_frame returns True for sqlobjects/sqlalchemy/logging module names."""
    from sqlobjects.sql_logging import _should_skip_frame

    assert _should_skip_frame("/app/sqlobjects/queries/executor.py", "sqlobjects.queries.executor", ()) is True
    assert _should_skip_frame("/app/sqlobjects/__init__.py", "sqlobjects", ()) is True
    assert _should_skip_frame("/app/sqlalchemy/engine.py", "sqlalchemy", ()) is True
    assert _should_skip_frame("/usr/lib/python3.12/logging/__init__.py", "logging", ()) is True


def test_should_skip_frame_skips_extra_prefixes():
    """_should_skip_frame returns True for caller-supplied extra prefixes."""
    from sqlobjects.sql_logging import _should_skip_frame

    assert _should_skip_frame("/app/myapp/middleware.py", "myapp.middleware", ("myapp.middleware",)) is True
    assert _should_skip_frame("/app/myapp/views.py", "myapp.views", ("myapp.middleware",)) is False


def test_should_skip_frame_passes_user_code():
    """_should_skip_frame returns False for ordinary user-code frames."""
    from sqlobjects.sql_logging import _should_skip_frame

    assert _should_skip_frame("/app/myapp/services/user_service.py", "myapp.services.user_service", ()) is False


def test_object_logger_makerecord_overwrites_caller_fields():
    """ObjectLogger.makeRecord() sets filename/funcName/lineno to user-code location."""
    from sqlobjects.sql_logging import ObjectLogger

    logger = ObjectLogger("test.object_logger")
    record = logger.makeRecord(
        name="test.object_logger",
        level=logging.DEBUG,
        fn="executor.py",  # should be overwritten
        lno=99,  # should be overwritten
        msg="test",
        args=(),
        exc_info=None,
    )
    assert "executor" not in record.filename
    assert "test_sql_logging" in record.filename
    assert record.lineno != 99


def test_object_logger_makerecord_no_crash_when_no_user_frame():
    """ObjectLogger.makeRecord() falls back gracefully when no user frame found."""
    from sqlobjects.sql_logging import ObjectLogger

    logger = ObjectLogger("test.object_logger_fallback")
    logger.extra_skip_packages = ["tests", "_pytest", "pluggy"]
    record = logger.makeRecord(
        name="test.object_logger_fallback",
        level=logging.DEBUG,
        fn="original.py",
        lno=42,
        msg="test",
        args=(),
        exc_info=None,
    )
    # When no frame found, original values are preserved
    assert isinstance(record.filename, str)
    assert isinstance(record.lineno, int)


def test_object_logger_extra_skip_packages_is_threaded_through():
    """ObjectLogger respects extra_skip_packages set at construction."""
    from sqlobjects.sql_logging import ObjectLogger

    logger = ObjectLogger(
        "test.object_logger_skip",
        extra_skip_packages=["tests.unit.test_sql_logging"],
    )
    record = logger.makeRecord(
        name="test.object_logger_skip",
        level=logging.DEBUG,
        fn="executor.py",
        lno=99,
        msg="test",
        args=(),
        exc_info=None,
    )
    # test_sql_logging frames skipped; caller should be some outer frame
    assert "test_sql_logging" not in record.filename


def test_install_object_logger_returns_object_logger_instance():
    """_install_object_logger returns an ObjectLogger registered in loggerDict."""
    import logging as stdlib_logging

    from sqlobjects.sql_logging import ObjectLogger, _install_object_logger

    name = "test.install_object_logger_unique_xyz"
    result = _install_object_logger(name)

    assert isinstance(result, ObjectLogger)
    assert stdlib_logging.root.manager.loggerDict.get(name) is result

    # Cleanup
    del stdlib_logging.root.manager.loggerDict[name]


def test_install_object_logger_migrates_existing_handlers():
    """_install_object_logger migrates handlers from a pre-existing Logger."""
    import logging as stdlib_logging

    from sqlobjects.sql_logging import _install_object_logger

    name = "test.install_migrate_handlers_xyz"
    existing = stdlib_logging.getLogger(name)
    handler = stdlib_logging.StreamHandler()
    existing.addHandler(handler)

    result = _install_object_logger(name)

    assert handler in result.handlers

    # Cleanup
    del stdlib_logging.root.manager.loggerDict[name]


def test_object_logger_debug_call_rewrites_caller():
    """ObjectLogger rewrites caller fields when called via .debug(), not just makeRecord."""
    import logging as stdlib_logging

    from sqlobjects.sql_logging import ObjectLogger

    logger = ObjectLogger("test.via_debug")
    logger.setLevel(stdlib_logging.DEBUG)
    records = []

    class Capture(stdlib_logging.Handler):
        def emit(self, record):
            records.append(record)

    logger.addHandler(Capture())
    logger.debug("test message")  # full call path: debug → _log → makeRecord

    assert len(records) == 1
    r = records[0]
    assert "test_sql_logging" in r.filename
    assert r.funcName == "test_object_logger_debug_call_rewrites_caller"
