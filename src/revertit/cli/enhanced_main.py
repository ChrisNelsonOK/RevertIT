#!/usr/bin/env python3
"""
Enhanced RevertIT CLI - Command-line interface with Docker integration.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ..daemon.main import RevertITDaemon
from ..distro.detector import DistroDetector
from ..snapshot.enhanced_manager import SnapshotManager


class EnhancedRevertITCLI:
    """Enhanced command-line interface for RevertIT with Docker integration."""

    def __init__(self):
        """Initialize CLI."""
        self.config_path = "/opt/revertit/config/revertit.yaml"
        self.logger = None

    def setup_logging(self, verbose: bool = False) -> None:
        """Setup logging for CLI operations."""
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=level, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration file."""
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
                return config if config else {}
        except FileNotFoundError:
            print(f"Configuration file not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            print(f"Error parsing configuration: {e}")
            return {}

    def cmd_status(self, args) -> int:
        """Show daemon and system status."""
        config = self.load_config()

        print("RevertIT Enhanced Status")
        print("=" * 40)

        # Check daemon status
        pid_file = config.get("global", {}).get("pid_file", "/var/run/revertit.pid")
        if Path(pid_file).exists():
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())

                # Check if process is running
                try:
                    import os
                    os.kill(pid, 0)
                    print(f"✓ Daemon running (PID: {pid})")
                except OSError:
                    print("✗ Daemon not running (stale PID file)")
            except Exception as e:
                print(f"✗ Error reading PID file: {e}")
        else:
            print("✗ Daemon not running")

        # Distribution info
        try:
            distro_detector = DistroDetector(config.get("distro", {}))
            distro_info = distro_detector.detect()
            print(f"✓ Distribution: {distro_info['name']} {distro_info['version']}")
            print(f"  Family: {distro_info['family']}")
            print(f"  Package Manager: {distro_info['package_manager']}")
            print(f"  Init System: {distro_info['init_system']}")
        except Exception as e:
            print(f"✗ Error detecting distribution: {e}")

        # Configuration file
        if Path(self.config_path).exists():
            print(f"✓ Configuration: {self.config_path}")
        else:
            print(f"✗ Configuration file missing: {self.config_path}")

        # Docker integration status
        try:
            distro_detector = DistroDetector(config.get("distro", {}))
            distro_info = distro_detector.detect()
            snapshot_manager = SnapshotManager(
                config=config.get("snapshot", {}), distro_info=distro_info
            )
            
            docker_info = snapshot_manager.get_docker_info()
            if docker_info.get('docker_enabled', False):
                print("✓ Docker integration enabled")
                containers = docker_info.get('containers', [])
                volumes = docker_info.get('volumes', [])
                print(f"  Containers: {len(containers)}")
                print(f"  Volumes: {len(volumes)}")
            else:
                print("✗ Docker integration disabled")
                print(f"  Reason: {docker_info.get('reason', 'Unknown')}")
        except Exception as e:
            print(f"✗ Error checking Docker integration: {e}")

        # Log file
        log_file = config.get("global", {}).get("log_file", "/var/log/revertit.log")
        if Path(log_file).exists():
            print(f"✓ Log file: {log_file}")
        else:
            print(f"✗ Log file not found: {log_file}")

        return 0

    def cmd_start(self, args) -> int:
        """Start the daemon."""
        if args.config:
            self.config_path = args.config

        try:
            daemon = RevertITDaemon(config_path=self.config_path)
            print("Starting RevertIT daemon...")
            daemon.start()
            return 0
        except Exception as e:
            print(f"Failed to start daemon: {e}")
            return 1

    def cmd_stop(self, args) -> int:
        """Stop the daemon."""
        config = self.load_config()
        pid_file = config.get("global", {}).get("pid_file", "/var/run/revertit.pid")

        if not Path(pid_file).exists():
            print("Daemon is not running")
            return 0

        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())

            import os
            import signal

            os.kill(pid, signal.SIGTERM)
            print(f"Sent stop signal to daemon (PID: {pid})")
            return 0

        except Exception as e:
            print(f"Failed to stop daemon: {e}")
            return 1

    def cmd_restart(self, args) -> int:
        """Restart the daemon."""
        print("Stopping daemon...")
        self.cmd_stop(args)

        import time
        time.sleep(2)

        print("Starting daemon...")
        return self.cmd_start(args)

    def cmd_snapshots(self, args) -> int:
        """Manage snapshots."""
        config = self.load_config()

        try:
            # Initialize components needed for snapshot management
            distro_detector = DistroDetector(config.get("distro", {}))
            distro_info = distro_detector.detect()

            snapshot_manager = SnapshotManager(
                config=config.get("snapshot", {}), distro_info=distro_info
            )

            if args.snapshot_action == "list":
                return self._list_snapshots(snapshot_manager)
            elif args.snapshot_action == "create":
                return self._create_snapshot(snapshot_manager, args.description)
            elif args.snapshot_action == "delete":
                return self._delete_snapshot(snapshot_manager, args.snapshot_id)
            elif args.snapshot_action == "restore":
                return self._restore_snapshot(snapshot_manager, args.snapshot_id)
            else:
                print(f"Unknown snapshot action: {args.snapshot_action}")
                return 1

        except Exception as e:
            print(f"Snapshot operation failed: {e}")
            return 1

    def _list_snapshots(self, snapshot_manager: SnapshotManager) -> int:
        """List all snapshots."""
        snapshots = snapshot_manager.list_snapshots()

        if not snapshots:
            print("No snapshots found")
            return 0

        print("Available Snapshots:")
        print("-" * 100)
        print(f"{'ID':<30} {'Type':<12} {'Timestamp':<20} {'Docker':<8} {'Size':<10} {'Description'}")
        print("-" * 100)

        for snapshot in snapshots:
            snapshot_type = snapshot.get('type', 'manual')
            docker_enabled = "Yes" if snapshot.get('docker_enabled', False) else "No"
            size_mb = snapshot.get('total_size', 0) / (1024 * 1024)
            size_str = f"{size_mb:.1f}MB" if size_mb > 0 else "Unknown"
            
            print(
                f"{snapshot['id']:<30} {snapshot_type:<12} "
                f"{snapshot.get('timestamp', 'unknown'):<20} {docker_enabled:<8} "
                f"{size_str:<10} {snapshot.get('description', 'No description')}"
            )

        return 0

    def _create_snapshot(
        self, snapshot_manager: SnapshotManager, description: Optional[str] = None
    ) -> int:
        """Create a new snapshot."""
        try:
            if not description:
                description = "Enhanced snapshot created via CLI"

            snapshot_id = snapshot_manager.create_snapshot(description)
            print(f"Created enhanced snapshot: {snapshot_id}")
            return 0
        except Exception as e:
            print(f"Failed to create snapshot: {e}")
            return 1

    def _delete_snapshot(
        self, snapshot_manager: SnapshotManager, snapshot_id: str
    ) -> int:
        """Delete a snapshot."""
        if not snapshot_id:
            print("Snapshot ID is required for deletion")
            return 1

        try:
            success = snapshot_manager.delete_snapshot(snapshot_id)
            if success:
                print(f"Deleted snapshot: {snapshot_id}")
                return 0
            else:
                print(f"Failed to delete snapshot: {snapshot_id}")
                return 1
        except Exception as e:
            print(f"Error deleting snapshot: {e}")
            return 1

    def _restore_snapshot(
        self, snapshot_manager: SnapshotManager, snapshot_id: str
    ) -> int:
        """Restore from a snapshot."""
        if not snapshot_id:
            print("Snapshot ID is required for restoration")
            return 1

        print(
            f"WARNING: This will restore system configuration from snapshot: {snapshot_id}"
        )
        response = input("Are you sure you want to continue? (yes/no): ")

        if response.lower() not in ["yes", "y"]:
            print("Restoration cancelled")
            return 0

        try:
            success = snapshot_manager.restore_snapshot(snapshot_id)
            if success:
                print(f"Successfully restored from snapshot: {snapshot_id}")
                print("You may need to restart affected services manually")
                return 0
            else:
                print(f"Failed to restore from snapshot: {snapshot_id}")
                return 1
        except Exception as e:
            print(f"Error restoring snapshot: {e}")
            return 1

    def cmd_docker(self, args) -> int:
        """Docker integration commands."""
        config = self.load_config()
        
        try:
            # Initialize components needed for Docker management
            distro_detector = DistroDetector(config.get("distro", {}))
            distro_info = distro_detector.detect()
            
            snapshot_manager = SnapshotManager(
                config=config.get("snapshot", {}), distro_info=distro_info
            )
            
            if args.docker_action == "info":
                return self._docker_info(snapshot_manager)
            elif args.docker_action == "volumes":
                return self._docker_volumes(snapshot_manager)
            elif args.docker_action == "databases":
                return self._docker_databases(snapshot_manager)
            elif args.docker_action == "test":
                return self._docker_test(snapshot_manager)
            else:
                print(f"Unknown docker action: {args.docker_action}")
                return 1
                
        except Exception as e:
            print(f"Docker operation failed: {e}")
            return 1
    
    def _docker_info(self, snapshot_manager) -> int:
        """Show Docker environment information."""
        try:
            docker_info = snapshot_manager.get_docker_info()
            
            print("Docker Environment Information")
            print("=" * 50)
            
            if not docker_info.get('docker_enabled', True):
                print("❌ Docker integration not available")
                print(f"   Reason: {docker_info.get('reason', 'Unknown')}")
                return 0
            
            # Show containers
            containers = docker_info.get('containers', [])
            print(f"📦 Containers: {len(containers)}")
            for container in containers[:5]:  # Show first 5
                print(f"   • {container.get('Names', 'Unknown')} ({container.get('State', 'Unknown')})")
            if len(containers) > 5:
                print(f"   ... and {len(containers) - 5} more")
            
            # Show volumes  
            volumes = docker_info.get('volumes', [])
            print(f"💾 Volumes: {len(volumes)}")
            for volume in volumes[:5]:  # Show first 5
                print(f"   • {volume.get('Name', 'Unknown')}")
            if len(volumes) > 5:
                print(f"   ... and {len(volumes) - 5} more")
            
            # Show compose files
            compose_files = docker_info.get('compose_files', [])
            print(f"🐳 Compose Files: {len(compose_files)}")
            for compose_file in compose_files:
                print(f"   • {compose_file}")
            
            return 0
            
        except Exception as e:
            print(f"Failed to get Docker info: {e}")
            return 1
    
    def _docker_volumes(self, snapshot_manager) -> int:
        """Show Docker volume statistics."""
        try:
            volume_stats = snapshot_manager.get_volume_stats()
            
            print("Docker Volume Statistics")
            print("=" * 50)
            
            if not volume_stats:
                print("No volume statistics available")
                return 0
            
            total_size_bytes = 0
            
            print(f"{'Volume Name':<30} {'Size (MB)':<15} {'Driver':<10} {'Status'}")
            print("-" * 70)
            
            for volume_name, stats in volume_stats.items():
                size_mb = stats.get('size_mb', 0)
                driver = stats.get('driver', 'unknown')
                status = 'error' if 'error' in stats else 'ok'
                
                total_size_bytes += stats.get('size_bytes', 0)
                
                print(f"{volume_name:<30} {size_mb:<15.2f} {driver:<10} {status}")
            
            total_size_gb = total_size_bytes / (1024 * 1024 * 1024)
            print(f"\nTotal Volume Size: {total_size_gb:.2f} GB")
            
            return 0
            
        except Exception as e:
            print(f"Failed to get volume stats: {e}")
            return 1
    
    def _docker_databases(self, snapshot_manager) -> int:
        """Show database statistics."""
        try:
            db_stats = snapshot_manager.get_database_stats()
            
            print("Database Statistics")
            print("=" * 50)
            
            if not db_stats:
                print("No database statistics available")
                return 0
            
            for db_name, stats in db_stats.items():
                print(f"\n📊 Database: {db_name}")
                print(f"   Type: {stats.get('type', 'unknown')}")
                print(f"   Status: {stats.get('status', 'unknown')}")
                
                if 'error' in stats:
                    print(f"   ❌ Error: {stats['error']}")
                elif 'databases' in stats:
                    for db, db_info in stats['databases'].items():
                        size = db_info.get('size', 'unknown')
                        table_count = db_info.get('table_count', 'unknown')
                        print(f"   • {db}: {size} ({table_count} tables)")
            
            return 0
            
        except Exception as e:
            print(f"Failed to get database stats: {e}")
            return 1
    
    def _docker_test(self, snapshot_manager) -> int:
        """Test Docker integration functionality."""
        try:
            test_results = snapshot_manager.test_docker_integration()
            
            print("Docker Integration Test")
            print("=" * 50)
            
            # Show test results
            if test_results['docker_available']:
                print("✅ Docker is available")
            else:
                print("❌ Docker is not available")
            
            if test_results['docker_compose_available']:
                print("✅ Docker Compose is available")
            else:
                print("❌ Docker Compose is not available")
            
            if test_results['volumes_accessible']:
                volume_count = test_results.get('volume_count', 0)
                print(f"✅ Volumes are accessible ({volume_count} found)")
            else:
                print("❌ Volumes are not accessible")
            
            if test_results['databases_accessible']:
                db_count = test_results.get('database_count', 0)
                print(f"✅ Databases are accessible ({db_count} found)")
            else:
                print("❌ Databases are not accessible")
            
            if test_results['config_valid']:
                print("✅ Configuration is valid")
                config_summary = test_results.get('config_summary', {})
                print(f"   • Backup volumes: {config_summary.get('backup_volumes', False)}")
                print(f"   • Backup databases: {config_summary.get('backup_databases', False)}")
                print(f"   • Backup compose files: {config_summary.get('backup_compose_files', False)}")
            else:
                print("❌ Configuration is not valid")
            
            # Show errors
            errors = test_results.get('errors', [])
            if errors:
                print(f"\n❌ Errors ({len(errors)}):")
                for error in errors:
                    print(f"   • {error}")
            
            # Show warnings
            warnings = test_results.get('warnings', [])
            if warnings:
                print(f"\n⚠️  Warnings ({len(warnings)}):")
                for warning in warnings:
                    print(f"   • {warning}")
            
            if not errors:
                print("\n🎉 All tests passed!")
                return 0
            else:
                print(f"\n💥 {len(errors)} test(s) failed")
                return 1
                
        except Exception as e:
            print(f"Docker integration test failed: {e}")
            return 1

    def cmd_timeouts(self, args) -> int:
        """Manage active timeouts."""
        self.load_config()

        try:
            # This is a simplified version - in real usage, we'd connect to the daemon
            print("Active Timeouts:")
            print("(This would connect to the running daemon to show active timeouts)")
            print("Feature requires daemon integration for full functionality")
            return 0
        except Exception as e:
            print(f"Failed to list timeouts: {e}")
            return 1

    def cmd_confirm(self, args) -> int:
        """Confirm a configuration change."""
        if not args.change_id:
            print("Change ID is required")
            return 1

        try:
            # This would connect to the daemon to confirm the change
            print(f"Confirming change: {args.change_id}")
            print("(This feature requires daemon integration)")
            return 0
        except Exception as e:
            print(f"Failed to confirm change: {e}")
            return 1

    def cmd_test(self, args) -> int:
        """Test system compatibility and configuration."""
        config = self.load_config()

        print("RevertIT Enhanced System Test")
        print("=" * 40)

        # Test distribution detection
        try:
            distro_detector = DistroDetector(config.get("distro", {}))
            distro_info = distro_detector.detect()
            compatibility = distro_detector.get_compatibility_info()

            print(f"✓ Distribution detected: {distro_info['name']}")
            print(f"  Supported: {'Yes' if distro_detector.is_supported() else 'No'}")
            print(
                f"  TimeShift compatible: {'Yes' if compatibility['timeshift_available'] else 'No'}"
            )
        except Exception as e:
            print(f"✗ Distribution detection failed: {e}")

        # Test snapshot capability
        try:
            snapshot_manager = SnapshotManager(
                config=config.get("snapshot", {}), distro_info=distro_info
            )

            # Try to create and delete a test snapshot
            test_snapshot = snapshot_manager.create_snapshot(
                "Test snapshot - will be deleted"
            )
            print("✓ Snapshot creation works")

            snapshot_manager.delete_snapshot(test_snapshot)
            print("✓ Snapshot deletion works")

        except Exception as e:
            print(f"✗ Snapshot functionality failed: {e}")

        # Test Docker integration
        try:
            distro_detector = DistroDetector(config.get("distro", {}))
            distro_info = distro_detector.detect()
            snapshot_manager = SnapshotManager(
                config=config.get("snapshot", {}), distro_info=distro_info
            )
            
            test_results = snapshot_manager.test_docker_integration()
            
            if test_results['docker_available']:
                print("✓ Docker integration available")
                if test_results['volumes_accessible']:
                    print(f"✓ Can access {test_results.get('volume_count', 0)} volumes")
                if test_results['databases_accessible']:
                    print(f"✓ Can access {test_results.get('database_count', 0)} databases")
            else:
                print("⚠ Docker integration not available")
                
        except Exception as e:
            print(f"✗ Docker integration test failed: {e}")

        # Test configuration file monitoring paths
        monitor_config = config.get("monitoring", {})
        all_paths = []
        all_paths.extend(monitor_config.get("network_configs", []))
        all_paths.extend(monitor_config.get("ssh_configs", []))
        all_paths.extend(monitor_config.get("firewall_configs", []))
        all_paths.extend(monitor_config.get("service_configs", []))

        existing_paths = []
        for path in all_paths:
            if "*" not in path and Path(path).exists():
                existing_paths.append(path)

        print(f"✓ Found {len(existing_paths)} existing configuration files to monitor")

        # Test permissions
        try:
            import os

            if os.geteuid() != 0:
                print("⚠ Warning: Not running as root - some features may not work")
            else:
                print("✓ Running with root privileges")
        except Exception:
            print("? Could not determine privilege level")

        return 0


def main():
    """Main entry point for enhanced CLI."""
    parser = argparse.ArgumentParser(
        description="RevertIT Enhanced - Timed confirmation system with Docker integration"
    )

    parser.add_argument(
        "--config", default="/opt/revertit/config/revertit.yaml", help="Configuration file path"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Status command
    subparsers.add_parser("status", help="Show system status")

    # Daemon management commands
    start_parser = subparsers.add_parser("start", help="Start daemon")
    start_parser.add_argument(
        "--foreground", action="store_true", help="Run in foreground"
    )

    subparsers.add_parser("stop", help="Stop daemon")
    subparsers.add_parser("restart", help="Restart daemon")

    # Snapshot management commands
    snapshot_parser = subparsers.add_parser("snapshots", help="Manage snapshots")
    snapshot_parser.add_argument(
        "snapshot_action",
        choices=["list", "create", "delete", "restore"],
        help="Snapshot action to perform",
    )
    snapshot_parser.add_argument(
        "--snapshot-id", help="Snapshot ID for delete/restore operations"
    )
    snapshot_parser.add_argument("--description", help="Description for new snapshot")

    # Docker management commands
    docker_parser = subparsers.add_parser("docker", help="Docker integration commands")
    docker_parser.add_argument(
        "docker_action",
        choices=["info", "volumes", "databases", "test"],
        help="Docker action to perform"
    )

    # Timeout management commands
    subparsers.add_parser("timeouts", help="List active timeouts")

    confirm_parser = subparsers.add_parser(
        "confirm", help="Confirm a configuration change"
    )
    confirm_parser.add_argument("change_id", help="Change ID to confirm")

    # Test command
    subparsers.add_parser("test", help="Test system compatibility")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cli = EnhancedRevertITCLI()
    cli.config_path = args.config
    cli.setup_logging(args.verbose)

    # Route to appropriate command handler
    command_handlers = {
        "status": cli.cmd_status,
        "start": cli.cmd_start,
        "stop": cli.cmd_stop,
        "restart": cli.cmd_restart,
        "snapshots": cli.cmd_snapshots,
        "docker": cli.cmd_docker,
        "timeouts": cli.cmd_timeouts,
        "confirm": cli.cmd_confirm,
        "test": cli.cmd_test,
    }

    handler = command_handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
