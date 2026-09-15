import bcrypt

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
