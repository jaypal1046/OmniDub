import pytest
from core.comic_animator import _build_filter_complex

def test_subtitle_drawtext_escaping_apostrophe_and_colons():
    # Test case matching user screenshot: "unwell, noting that stress from new surroundings isn't..."
    raw = "unwell, noting that stress from new surroundings isn't: 100% strange!"
    fc = _build_filter_complex(
        image_path="dummy.png",
        audio_path="dummy.mp3",
        subtitle_text=raw,
        preset="zoom_in",
        framing_mode="contain",
        width=1280,
        height=720,
        duration=3.0
    )
    # Check that raw single quote is replaced by typographic apostrophe to prevent FFmpeg filter breaking
    assert "isn't" not in fc
    assert "isn’t" in fc
    # Check that colon is escaped
    assert r"\:" in fc
    # Check that % is escaped
    assert r"\%" in fc
    # Check boxcolor is light black (0.45)
    assert "boxcolor=black@0.45" in fc
