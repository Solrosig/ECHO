"""The Space mounts Gradio so that its config and its queued results both link to /api/tts."""

import ast
from pathlib import Path

APP = (
    Path(__file__).resolve().parents[1]
    / "standalone"
    / "deployment"
    / "huggingface"
    / "app.py"
)


def mount_keywords():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "mount_gradio_app"
    ]
    assert len(calls) == 1
    return {keyword.arg: keyword.value for keyword in calls[0].keywords}


def test_gradio_is_mounted_at_api_tts_with_the_same_relative_root_path():
    keywords = mount_keywords()
    assert ast.literal_eval(keywords["path"]) == "/api/tts"
    # Queued results build their file links from root_path alone; a full URL there broke Gradio's routing.
    assert ast.literal_eval(keywords["root_path"]) == "/api/tts"
