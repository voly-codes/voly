"""
Headroom Layer — управление сжатием контекста.

Сжимает контекст, результаты поиска, историю диалогов и ответы
инструментов для снижения расхода токенов на 60-95%.
"""

from codeops.headroom.proxy import HeadroomManager

__all__ = ["HeadroomManager"]
