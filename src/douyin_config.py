from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOUYIN_DOWNLOAD_ROOT = PROJECT_ROOT / "downloads" / "douyin"
DOUYIN_MAX_BATCH_ITEMS = 50
DOUYIN_PAGE_DELAY_MIN = 0.8
DOUYIN_PAGE_DELAY_MAX = 2.0
DOUYIN_REQUEST_TIMEOUT = 20
DOUYIN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0"
)
