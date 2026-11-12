"""密钥加密存储（Fernet / AES-128-CBC + HMAC）。

设计目标：用户级 API Key 与管理员配置的密钥**不以明文落库**。
- 密文带 `enc:` 前缀，可识别；读取时解密。
- 兼容历史明文（无前缀）→ 原样返回，并在下次写入时自动升级为密文。
- 加密密钥来源：`SECRET_ENCRYPTION_KEY` 环境变量；未设置时由
  `JWT_SECRET` 经 SHA-256 派生（避免新增必填配置，但生产应显式设置）。
"""
from __future__ import annotations

import base64
import hashlib
import os

from .config import settings

_PREFIX = "enc:"
_cipher = None


def _load_cipher():
    global _cipher
    if _cipher is not None:
        return _cipher
    raw = os.environ.get("SECRET_ENCRYPTION_KEY") or settings.secret_encryption_key
    if raw:
        key_bytes = hashlib.sha256(raw.encode("utf-8")).digest()
    else:
        # 未显式配置时由 JWT_SECRET 派生（同一份配置即同一把钥匙）
        key_bytes = hashlib.sha256(
            ("ta-enc::" + settings.jwt_secret).encode("utf-8")).digest()
    from cryptography.fernet import Fernet
    _cipher = Fernet(base64.urlsafe_b64encode(key_bytes))
    return _cipher


def encrypt_secret(plaintext: str | None) -> str:
    """加密密钥；空串原样返回（表示「未配置」）。"""
    if not plaintext:
        return ""
    if plaintext.startswith(_PREFIX):        # 已是密文，幂等
        return plaintext
    token = _load_cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_secret(stored: str | None) -> str:
    """解密密钥；历史明文（无前缀）原样返回，保证向后兼容。"""
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        return stored                        # 兼容历史明文
    try:
        return _load_cipher().decrypt(stored[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        return ""                            # 密钥轮换后旧密文无法解密 → 视为未配置


def is_encrypted(stored: str | None) -> bool:
    return bool(stored) and stored.startswith(_PREFIX)
