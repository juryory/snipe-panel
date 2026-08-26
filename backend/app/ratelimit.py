"""进程内滑动窗口限流。

MVP 单进程部署,内存计数即可(PRD 第 4 节:单机足够)。
若将来横向扩容,把 _WINDOWS 换成 Redis。
"""
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

_WINDOWS: Dict[str, Deque[float]] = defaultdict(deque)
_LOCK = threading.Lock()


def allow(key: str, limit: int, window_seconds: int = 60) -> bool:
    """在 window_seconds 内允许 key 至多 limit 次。超限返回 False。"""
    now = time.monotonic()
    cutoff = now - window_seconds
    with _LOCK:
        bucket = _WINDOWS[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def reset(key: str) -> None:
    with _LOCK:
        _WINDOWS.pop(key, None)
