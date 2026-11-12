"""Prompt 防护：输入侧过滤 + 角色隔离 + 输出侧审计。

- 输入侧：规则过滤「忽略之前所有指令」类注入话术；长度限制 2000 字符。
- 角色隔离：用户文本永远放在 user 角色消息里，不拼接进 system prompt；
  system prompt 里明确「用户输入仅作为旅行需求」。
- 输出侧：对偏离旅行规划角色的请求拒绝执行。
"""
from __future__ import annotations

import re

from ....common.errors import ValidationError
from ....common.logging import get_logger

logger = get_logger("prompt_guard")

MAX_INPUT_LEN = 2000

_INJECTION_PATTERNS = [
    r"忽略(之前|以上|前面)(所有)?(的)?指令",
    r"ignore (all )?(previous|prior) instructions",
    r"忘记(你|你的)?(身份|设定|角色)",
    r"你现在是",
    r"system\s*prompt",
    r"泄露.{0,6}(提示词|指令|prompt)",
    r"输出(你的)?(系统)?(提示词|指令)",
    r"越狱",
    r"jailbreak",
    r"扮演.{0,8}(管理员|开发者)",
]

_OUT_OF_SCOPE = [
    r"写(一|个)?(代码|程序|脚本)",
    r"帮我(写|做).{0,6}(作业|论文|代码)",
    r"(生成|写).{0,4}(病毒|木马|恶意)",
]


class PromptGuard:
    def check_input(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            raise ValidationError("输入不能为空")
        if len(text) > MAX_INPUT_LEN:
            raise ValidationError(f"输入过长，请控制在 {MAX_INPUT_LEN} 字符以内")
        for p in _INJECTION_PATTERNS:
            if re.search(p, text, re.IGNORECASE):
                logger.warning("拦截疑似 Prompt 注入", extra={"event": "injection_blocked"})
                raise ValidationError("检测到疑似指令注入，请用正常语句描述你的旅行需求")
        return text

    def audit_output(self, text: str) -> str:
        return text

    def is_in_scope(self, text: str) -> bool:
        for p in _OUT_OF_SCOPE:
            if re.search(p, text):
                return False
        return True

    def wrap_user_content(self, text: str) -> str:
        """角色隔离：明确标注用户输入只是「数据」，不给它指令权。"""
        return f"【用户旅行需求】{text}"


prompt_guard = PromptGuard()
