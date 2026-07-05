"""
RTK Layer — управление Rust Token Killer для фильтрации вывода команд.

Сокращает шум терминала, git diff, логи, тесты и результаты команд
на 60-90% перед передачей в модель.
"""

from voly.rtk.installer import RTKManager

__all__ = ["RTKManager"]
