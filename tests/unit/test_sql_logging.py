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
