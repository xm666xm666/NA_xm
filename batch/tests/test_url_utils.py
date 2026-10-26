import sys
from pathlib import Path

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.url_utils import normalize_na_base_url  # noqa: E402


def test_normalize_removes_trailing_and_invisible_spaces():
    assert normalize_na_base_url(" https://na-test.example.com\u00a0") == "https://na-test.example.com"
    assert normalize_na_base_url("https://na-test.example.com\u200b") == "https://na-test.example.com"
    assert normalize_na_base_url("https://na-test.example.com\u3000") == "https://na-test.example.com"


if __name__ == "__main__":
    test_normalize_removes_trailing_and_invisible_spaces()
    print("ok")

