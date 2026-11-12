"""desktop-notification：把提醒推到「用户桌面」。

MCP 的 desktop-notification 工具负责让用户真正「被提醒到」：
- 无条件写入一条站内通知（保证 Web 端右上角红点可见）；
- 在 Windows 上再尽力弹一个托盘气泡（.NET NotifyIcon，无需第三方库），
  失败只记日志、不影响主流程——服务器可能运行在无桌面会话的环境。

实现要点：气泡进程需要存活数秒才会显示，所以用 Popen 起独立进程、
不阻塞事件循环；命令用单引号包裹参数，避免用户文本里的引号注入。
"""
from __future__ import annotations

import subprocess
import sys

from ...common.logging import get_logger

logger = get_logger("mcp.desktop")

# PowerShell 脚本：用 .NET 托盘气泡弹一条通知，9 秒后自动清理
_PS_TEMPLATE = (
    "Add-Type -AssemblyName System.Windows.Forms;"
    "Add-Type -AssemblyName System.Drawing;"
    "$n=New-Object System.Windows.Forms.NotifyIcon;"
    "$n.Icon=[System.Drawing.SystemIcons]::Information;"
    "$n.Visible=$true;"
    "$n.ShowBalloonTip(8000,{title},{content},"
    "[System.Windows.Forms.ToolTipIcon]::Info);"
    "Start-Sleep -Seconds 9;"
    "$n.Dispose()"
)


def _ps_quote(text: str) -> str:
    """转义为 PowerShell 单引号字符串字面量（单引号翻倍）。"""
    return "'" + (text or "").replace("'", "''") + "'"


def show_toast(title: str, content: str = "") -> bool:
    """弹一条 Windows 托盘气泡通知；非 Windows 或失败返回 False。"""
    if not sys.platform.startswith("win"):
        return False
    script = _PS_TEMPLATE.format(title=_ps_quote(title[:64]),
                                 content=_ps_quote(content[:200]))
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-Command", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception as exc:      # 无桌面会话 / 无 PowerShell 时静默降级
        logger.warning("桌面通知发送失败（已降级为仅站内通知）: %s", exc)
        return False
