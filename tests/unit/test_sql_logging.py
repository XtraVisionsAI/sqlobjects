from sqlobjects.sql_logging import get_caller_frame


def test_get_caller_frame_returns_string():
    """get_caller_frame 默认返回一个字符串"""
    result = get_caller_frame()
    assert isinstance(result, str)


def test_get_caller_frame_contains_this_file():
    """默认 max_frames=1 时，返回的帧应指向调用者（本测试文件）"""
    result = get_caller_frame()
    assert "test_sql_logging" in result


def test_get_caller_frame_max_frames_list():
    """max_frames > 1 时返回列表"""
    result = get_caller_frame(max_frames=3)
    assert isinstance(result, list)
    assert len(result) >= 1


def test_get_caller_frame_skips_site_packages():
    """不应返回 site-packages 中的帧"""
    result = get_caller_frame(max_frames=5)
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        assert "site-packages" not in frame


def test_get_caller_frame_skips_sqlobjects_frames():
    """不应返回 sqlobjects 内部帧（editable install 兼容）"""
    result = get_caller_frame(max_frames=5)
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        assert not ("sqlobjects" in frame and "test" not in frame)


def test_get_caller_frame_extra_skip_packages():
    """extra_skip_packages 可以跳过指定模块名前缀的帧"""
    result = get_caller_frame(
        max_frames=3,
        extra_skip_packages=["tests.unit.test_sql_logging"],
    )
    frames = result if isinstance(result, list) else [result]
    for frame in frames:
        assert "test_sql_logging" not in frame
