"""
SuperGuard Core - Main Package

Cross-platform Security Platform Core API with plugin architecture.
"""

from superguard_core.main import app, create_app

__version__ = "2.0.0-dev"
__author__ = "SuperGuard Team"

__all__ = [
    "app",
    "create_app",
]