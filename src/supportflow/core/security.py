import hashlib
import secrets

import bcrypt


def generate_session_token() -> str:
    """32 字节安全随机数（256 bit），编码为可放进 Cookie 的字符串。"""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """仅用于高强度随机会话凭证；用户密码仍使用 bcrypt。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def get_password_hash(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if not 1 <= len(password_bytes) <= 72:
        raise ValueError("密码的 UTF-8 编码长度须为 1～72 字节")

    return bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(rounds=12),
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")
    if not 1 <= len(password_bytes) <= 72:
        return False

    try:
        return bcrypt.checkpw(
            password_bytes,
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        return False
