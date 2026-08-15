"""
SuperGuard Core - Хранилище Plugins Package
"""

from superguard_core.plugins.storage.sqlite import SqliteStoragePlugin

# Реестр плагинов
STORAGE_PLUGINS = {
    "sqlite": SqliteStoragePlugin,
}

__all__ = [
    "SqliteStoragePlugin",
    "STORAGE_PLUGINS",
]