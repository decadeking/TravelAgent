"""MCP 服务：智能体工具以「MCP 子进程」形式统一提供。

- server.py：基于 MCP 协议（stdio）暴露旅行工具，可被任意 MCP 客户端复用；
- manager.py：进程内 MCP 客户端，拉起子进程、维持长连接并做健康检查；
- desktop.py：desktop-notification 在 Windows 上的原生气泡提醒（尽力而为）。
"""
