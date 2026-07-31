"""
Memory Layer — долгосрочная память агента.

Предоставляет:
    - Хранение решений и архитектурных документов
    - Кодовые соглашения и паттерны
    - Историю проекта и сессий
    - Семантический поиск по памяти
"""

from voly.memory.store import MemoryStore
from voly.memory.strategic import SessionHandoff, StrategicMemoryStore

__all__ = ["MemoryStore", "SessionHandoff", "StrategicMemoryStore"]
