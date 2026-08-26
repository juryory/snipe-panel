"""事件推送。

推给 n8n,由它转发到企业微信 / 飞书。为什么不直接推企微:企微的消息格式、
应用密钥、access_token 续期都是它自己的一套,写死在这里将来换飞书就得重写;
n8n 本来就是干这个的,而且他们已经在用。

推送是**尽力而为**的:失败只记日志,绝不影响借还本身。设备已经交到人手上了,
不能因为通知发不出去就把这次借出回滚掉。
"""
import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .config import settings

logger = logging.getLogger("snipe")

TIMEOUT_SECONDS = 5


def _post(url: str, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    if settings.webhook_token:
        request.add_header("Authorization", f"Bearer {settings.webhook_token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status >= 400:
                logger.warning("webhook 返回 %s:%s", response.status, payload.get("event"))
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        logger.warning("webhook 推送失败(%s):%s", payload.get("event"), exc)


def emit(event: str, data: Optional[Dict[str, Any]] = None) -> None:
    """发一条事件。没配 webhook 地址就直接跳过。

    放在后台线程里发:借还接口不该为了等一个外部 HTTP 响应而多花几百毫秒,
    更不该在对方超时时把用户卡在那里。
    """
    url = settings.webhook_url
    if not url:
        return
    payload = {"event": event, "data": data or {}}
    threading.Thread(target=_post, args=(url, payload), daemon=True).start()
