"""
RevertIT - Timed confirmation system for Linux configuration changes.

This module provides automatic reversion of system configuration changes
if not confirmed within a specified timeout period. Designed for remote
system administrators to prevent loss of access due to configuration errors.
"""

__package__ = "revertit"
__version__ = "1.0.0"
__author__ = "MeshAdmin"
__email__ = "admin@meshadmin.com"

from .daemon.main import RevertITDaemon
from .cli.main import RevertITCLI
from .snapshot.manager import SnapshotManager
from .monitor.watcher import ConfigurationMonitor
from .timeout.manager import TimeoutManager
from .revert.engine import RevertEngine

# Backward compatibility aliases (deprecated, will be removed in v1.1)
MeshAdminDaemon = RevertITDaemon  # deprecated
MeshAdminCLI = RevertITCLI  # deprecated

__all__ = [
    "RevertITDaemon",
    "RevertITCLI",
    "SnapshotManager", 
    "ConfigurationMonitor",
    "TimeoutManager",
    "RevertEngine",
    # Deprecated aliases for backward compatibility
    "MeshAdminDaemon",
    "MeshAdminCLI"
]
