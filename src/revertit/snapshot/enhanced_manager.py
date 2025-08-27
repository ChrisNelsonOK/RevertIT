#!/usr/bin/env python3
"""
Enhanced Snapshot Manager - Integrates Docker volumes and database backups.
"""

import json
import logging
import os
import shutil
import subprocess
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import the original SnapshotManager and Docker components
from .manager import SnapshotManager
try:
    from ..docker.manager import DockerSnapshotManager
except ImportError:
    # Fallback if Docker integration is not available
    DockerSnapshotManager = None


class EnhancedSnapshotManager(SnapshotManager):
    """Enhanced snapshot manager with Docker integration."""
    
    def __init__(self, config: Dict[str, Any], distro_info: Dict[str, str]):
        """Initialize enhanced snapshot manager."""
        # Initialize parent class
        super().__init__(config, distro_info)
        
        # Load Docker configuration
        self.docker_config = self._load_docker_config()
        self.docker_enabled = (
            DockerSnapshotManager is not None and 
            self.docker_config.get('snapshot', {}).get('enable_docker_integration', True)
        )
        
        if self.docker_enabled:
            self.docker_manager = DockerSnapshotManager(
                self.docker_config, 
                self.snapshot_location
            )
            self.logger.info("Enhanced Snapshot Manager initialized with Docker integration")
        else:
            self.docker_manager = None
            self.logger.info("Enhanced Snapshot Manager initialized without Docker integration")
    
    def _load_docker_config(self) -> Dict[str, Any]:
        """Load Docker configuration from config file."""
        docker_config_path = Path("/opt/revertit/config/docker/docker-config.yaml")
        
        if docker_config_path.exists():
            try:
                with open(docker_config_path) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                self.logger.warning(f"Failed to load Docker config: {e}")
                return {}
        else:
            self.logger.info("Docker config not found, using defaults")
            return {}
    
    def create_snapshot(self, description: Optional[str] = None) -> str:
        """Create an enhanced snapshot including Docker components."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"revertit_enhanced_{timestamp}"
        
        if description is None:
            description = f"Enhanced RevertIT snapshot created at {datetime.now().isoformat()}"
        
        self.logger.info(f"Creating enhanced snapshot: {snapshot_id}")
        
        try:
            # Create the regular system snapshot first
            system_snapshot_id = super().create_snapshot(description)
            
            # Create Docker snapshot if enabled
            if self.docker_enabled and self.docker_manager:
                docker_metadata = self.docker_manager.create_docker_snapshot(
                    system_snapshot_id, description
                )
                
                # Create combined metadata
                combined_metadata = {
                    'id': snapshot_id,
                    'system_snapshot_id': system_snapshot_id,
                    'description': description,
                    'timestamp': datetime.now().isoformat(),
                    'type': 'enhanced',
                    'docker_enabled': True,
                    'docker_components': docker_metadata.get('docker_components', {}),
                    'docker_errors': docker_metadata.get('errors', []),
                    'total_size': docker_metadata.get('backup_size', 0)
                }
            else:
                # System-only snapshot
                combined_metadata = {
                    'id': snapshot_id,
                    'system_snapshot_id': system_snapshot_id,
                    'description': description,
                    'timestamp': datetime.now().isoformat(),
                    'type': 'enhanced',
                    'docker_enabled': False,
                    'docker_components': {},
                    'docker_errors': [],
                    'total_size': 0
                }
            
            # Save enhanced metadata
            snapshot_dir = self.snapshot_location / system_snapshot_id
            enhanced_metadata_file = snapshot_dir / "enhanced_metadata.json"
            
            with open(enhanced_metadata_file, 'w') as f:
                json.dump(combined_metadata, f, indent=2)
            
            self.logger.info(f"Enhanced snapshot created successfully: {snapshot_id}")
            return snapshot_id
            
        except Exception as e:
            self.logger.error(f"Failed to create enhanced snapshot: {e}")
            raise e
    
    def list_snapshots(self) -> List[Dict[str, Any]]:
        """List all snapshots including enhanced metadata."""
        snapshots = super().list_snapshots()
        enhanced_snapshots = []
        
        for snapshot in snapshots:
            snapshot_dir = self.snapshot_location / snapshot['id']
            enhanced_metadata_file = snapshot_dir / "enhanced_metadata.json"
            
            if enhanced_metadata_file.exists():
                try:
                    with open(enhanced_metadata_file) as f:
                        enhanced_metadata = json.load(f)
                    
                    # Merge system and enhanced metadata
                    enhanced_snapshot = snapshot.copy()
                    enhanced_snapshot.update(enhanced_metadata)
                    enhanced_snapshots.append(enhanced_snapshot)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to load enhanced metadata for {snapshot['id']}: {e}")
                    enhanced_snapshots.append(snapshot)
            else:
                # Regular snapshot without Docker integration
                enhanced_snapshots.append(snapshot)
        
        return enhanced_snapshots
    
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore from an enhanced snapshot."""
        snapshots = self.list_snapshots()
        snapshot = next((s for s in snapshots if s.get('id') == snapshot_id or s.get('system_snapshot_id') == snapshot_id), None)
        
        if not snapshot:
            self.logger.error(f"Snapshot not found: {snapshot_id}")
            return False
        
        # Use the system snapshot ID for restoration
        system_snapshot_id = snapshot.get('system_snapshot_id', snapshot_id)
        
        self.logger.info(f"Restoring enhanced snapshot: {snapshot_id}")
        
        success = True
        
        try:
            # Restore Docker components first (if available)
            if (snapshot.get('docker_enabled') and 
                self.docker_enabled and 
                self.docker_manager):
                
                self.logger.info("Restoring Docker components...")
                docker_success = self.docker_manager.restore_docker_snapshot(system_snapshot_id)
                if not docker_success:
                    self.logger.error("Docker snapshot restoration failed")
                    success = False
            
            # Restore system snapshot
            self.logger.info("Restoring system snapshot...")
            system_success = super().restore_snapshot(system_snapshot_id)
            if not system_success:
                self.logger.error("System snapshot restoration failed")
                success = False
            
            if success:
                self.logger.info(f"Enhanced snapshot restoration completed: {snapshot_id}")
            else:
                self.logger.error(f"Enhanced snapshot restoration completed with errors: {snapshot_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Enhanced snapshot restoration failed: {e}")
            return False
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete an enhanced snapshot."""
        snapshots = self.list_snapshots()
        snapshot = next((s for s in snapshots if s.get('id') == snapshot_id or s.get('system_snapshot_id') == snapshot_id), None)
        
        if not snapshot:
            self.logger.error(f"Snapshot not found: {snapshot_id}")
            return False
        
        # Use the system snapshot ID for deletion
        system_snapshot_id = snapshot.get('system_snapshot_id', snapshot_id)
        
        self.logger.info(f"Deleting enhanced snapshot: {snapshot_id}")
        
        # Delete using parent class method
        return super().delete_snapshot(system_snapshot_id)
    
    def get_docker_info(self) -> Dict[str, Any]:
        """Get current Docker environment information."""
        if self.docker_enabled and self.docker_manager:
            return self.docker_manager.get_docker_info()
        else:
            return {'docker_enabled': False, 'reason': 'Docker integration not available'}
    
    def get_volume_stats(self) -> Dict[str, Any]:
        """Get Docker volume usage statistics."""
        if self.docker_enabled and self.docker_manager:
            return self.docker_manager.volume_manager.get_volume_usage_stats()
        else:
            return {}
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        if self.docker_enabled and self.docker_manager:
            return self.docker_manager.db_manager.get_database_stats()
        else:
            return {}
    
    def test_docker_integration(self) -> Dict[str, Any]:
        """Test Docker integration functionality."""
        test_results = {
            'docker_available': False,
            'docker_compose_available': False,
            'volumes_accessible': False,
            'databases_accessible': False,
            'config_valid': False,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Test Docker availability
            result = subprocess.run(['docker', '--version'], 
                                  capture_output=True, text=True, check=True)
            test_results['docker_available'] = True
            self.logger.debug(f"Docker version: {result.stdout.strip()}")
            
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            test_results['errors'].append(f"Docker not available: {e}")
        
        try:
            # Test Docker Compose availability
            result = subprocess.run(['docker', 'compose', 'version'], 
                                  capture_output=True, text=True, check=True)
            test_results['docker_compose_available'] = True
            self.logger.debug(f"Docker Compose version: {result.stdout.strip()}")
            
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            test_results['errors'].append(f"Docker Compose not available: {e}")
        
        if self.docker_enabled and self.docker_manager:
            try:
                # Test volume access
                volumes = self.docker_manager.volume_manager._get_volumes_to_backup()
                test_results['volumes_accessible'] = len(volumes) > 0
                test_results['volume_count'] = len(volumes)
                
            except Exception as e:
                test_results['errors'].append(f"Volume access failed: {e}")
            
            try:
                # Test database access
                db_stats = self.docker_manager.db_manager.get_database_stats()
                test_results['databases_accessible'] = len(db_stats) > 0
                test_results['database_count'] = len(db_stats)
                
            except Exception as e:
                test_results['errors'].append(f"Database access failed: {e}")
            
            # Test configuration validity
            if self.docker_config:
                test_results['config_valid'] = True
                test_results['config_summary'] = {
                    'backup_volumes': self.docker_config.get('docker', {}).get('backup_volumes', False),
                    'backup_databases': self.docker_config.get('docker', {}).get('backup_databases', False),
                    'backup_compose_files': self.docker_config.get('docker', {}).get('backup_compose_files', False)
                }
        else:
            test_results['warnings'].append("Docker integration not enabled or not available")
        
        return test_results
    
    def cleanup_old_snapshots(self) -> None:
        """Clean up old snapshots beyond the maximum limit."""
        # Use parent class cleanup
        super().cleanup_old_snapshots()
        
        # Additional Docker-specific cleanup if needed
        if self.docker_enabled and self.docker_config.get('snapshot', {}).get('docker_snapshot_retention'):
            docker_retention = self.docker_config['snapshot']['docker_snapshot_retention']
            snapshots = self.list_snapshots()
            
            # Filter enhanced snapshots
            enhanced_snapshots = [s for s in snapshots if s.get('type') == 'enhanced']
            
            if len(enhanced_snapshots) > docker_retention:
                snapshots_to_delete = enhanced_snapshots[docker_retention:]
                
                for snapshot in snapshots_to_delete:
                    try:
                        self.delete_snapshot(snapshot['id'])
                        self.logger.info(f"Cleaned up old enhanced snapshot: {snapshot['id']}")
                    except Exception as e:
                        self.logger.error(f"Failed to cleanup snapshot {snapshot['id']}: {e}")


# Make EnhancedSnapshotManager available as the default
SnapshotManager = EnhancedSnapshotManager
