"""
Антиспам: rate limiting по user_id + action.
"""
import time
from config import SPAM_COOLDOWN

# {(user_id, action): last_timestamp}
_last_action: dict[tuple, float] = {}


def check_spam(user_id: int, action: str) -> bool:
    """
    Возвращает True если действие разрешено (не спам).
    Возвращает False если пользователь слишком часто жмёт.
    """
    key = (user_id, action)
    now = time.monotonic()
    last = _last_action.get(key, 0)
    if now - last < SPAM_COOLDOWN:
        return False
    _last_action[key] = now
    return True


def reset_spam(user_id: int, action: str) -> None:
    """Сбрасывает кулдаун для конкретного действия (после успешного выполнения)."""
    _last_action.pop((user_id, action), None)
