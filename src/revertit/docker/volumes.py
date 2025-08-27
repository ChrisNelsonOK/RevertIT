#!/usr/bin/env python3
"""
Volume Backup Manager - Handles Docker volume backup and restoration.
"""

import json
import logging
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import tarfile
import tempfile


class VolumeBackupManager:
    """Manages Docker volume backup and restoration."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize volume backup manager."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Configuration options
        self.compress_volumes = config.get('compress_volumes', True)
        self.parallel_backups = config.get('parallel_backups', False)
        self.exclude_volumes = set(config.get('exclude_volumes', []))
        self.include_only = set(config.get('include_only', []))
        
        # Critical volumes to always backup (from observability stack)
        self.critical_volumes = set(config.get('critical_volumes', [
            'grafana_data',
            'opt_grafana_data', 
            'postgres_data',
            'opt_postgres_data',
            'prometheus_data',
            'opt_prometheus_data',
            'influxdb_data',
            'opt_influxdb_data',
            'minio_data',
            'opt_minio_data',
            'portainer_data',
            'opt_portainer_data',
            'vector_data',
            'opt_vector_data'
        ]))
        
        self.logger.info("Volume Backup Manager initialized")
    
    def backup_volumes(self, snapshot_dir: Path) -> List[Dict[str, Any]]:
        """Backup Docker volumes."""
        volumes_dir = snapshot_dir / "volumes"
        volumes_dir.mkdir(exist_ok=True)
        
        # Get list of volumes to backup
        volumes_to_backup = self._get_volumes_to_backup()
        
        backup_metadata = []
        
        for volume_name in volumes_to_backup:
            try:
                volume_metadata = self._backup_single_volume(volume_name, volumes_dir)
                backup_metadata.append(volume_metadata)
                self.logger.info(f"Backed up volume: {volume_name}")
            except Exception as e:
                error_msg = f"Failed to backup volume {volume_name}: {e}"
                self.logger.error(error_msg)
                backup_metadata.append({
                    'name': volume_name,
                    'status': 'failed',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
        
        # Save volume backup metadata
        metadata_file = volumes_dir / "volumes_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(backup_metadata, f, indent=2)
        
        return backup_metadata
    
    def _get_volumes_to_backup(self) -> List[str]:
        """Get list of Docker volumes to backup."""
        try:
            # Get all volumes
            result = subprocess.run([
                'docker', 'volume', 'ls', '--format', '{{.Name}}'
            ], capture_output=True, text=True, check=True)
            
            all_volumes = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            
            # Filter volumes based on configuration
            volumes_to_backup = []
            
            for volume in all_volumes:
                # Skip if explicitly excluded
                if volume in self.exclude_volumes:
                    continue
                
                # If include_only is specified, only backup those volumes
                if self.include_only and volume not in self.include_only:
                    # Always include critical volumes
                    if volume not in self.critical_volumes:
                        continue
                
                volumes_to_backup.append(volume)
            
            # Always ensure critical volumes are included
            for critical_vol in self.critical_volumes:
                if critical_vol in all_volumes and critical_vol not in volumes_to_backup:
                    volumes_to_backup.append(critical_vol)
            
            self.logger.info(f"Found {len(volumes_to_backup)} volumes to backup: {volumes_to_backup}")
            return volumes_to_backup
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to list Docker volumes: {e}")
            return []
    
    def _backup_single_volume(self, volume_name: str, volumes_dir: Path) -> Dict[str, Any]:
        """Backup a single Docker volume."""
        volume_info = self._get_volume_info(volume_name)
        
        backup_metadata = {
            'name': volume_name,
            'timestamp': datetime.now().isoformat(),
            'mountpoint': volume_info.get('Mountpoint', 'unknown'),
            'driver': volume_info.get('Driver', 'local'),
            'status': 'success',
            'backup_file': None,
            'size_bytes': 0
        }
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Create a temporary container to access the volume
                container_name = f"revertit-backup-{volume_name}-{int(datetime.now().timestamp())}"
                
                # Run a container with the volume mounted
                subprocess.run([
                    'docker', 'run', '--rm', 
                    '-v', f'{volume_name}:/volume:ro',
                    '-v', f'{temp_path}:/backup',
                    '--name', container_name,
                    'alpine', 'tar', 'czf', f'/backup/{volume_name}.tar.gz', '-C', '/volume', '.'
                ], check=True)
                
                # Move the backup to the volumes directory
                backup_file = volumes_dir / f"{volume_name}.tar.gz"
                temp_backup = temp_path / f"{volume_name}.tar.gz"
                
                if temp_backup.exists():
                    shutil.move(temp_backup, backup_file)
                    backup_metadata['backup_file'] = str(backup_file)
                    backup_metadata['size_bytes'] = backup_file.stat().st_size
                else:
                    raise Exception("Backup file was not created")
                
                self.logger.debug(f"Volume {volume_name} backed up to {backup_file}")
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Docker command failed: {e}"
            backup_metadata['status'] = 'failed'
            backup_metadata['error'] = error_msg
            raise Exception(error_msg)
        
        return backup_metadata
    
    def _get_volume_info(self, volume_name: str) -> Dict[str, Any]:
        """Get detailed information about a Docker volume."""
        try:
            result = subprocess.run([
                'docker', 'volume', 'inspect', volume_name
            ], capture_output=True, text=True, check=True)
            
            volume_info = json.loads(result.stdout)[0]
            return volume_info
            
        except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
            return {}
    
    def restore_volumes(self, snapshot_dir: Path) -> bool:
        """Restore Docker volumes from backup."""
        volumes_dir = snapshot_dir / "volumes"
        
        if not volumes_dir.exists():
            self.logger.warning("No volume backups found to restore")
            return True
        
        # Load volume metadata
        metadata_file = volumes_dir / "volumes_metadata.json"
        if not metadata_file.exists():
            self.logger.error("Volume backup metadata not found")
            return False
        
        try:
            with open(metadata_file) as f:
                volume_metadata = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load volume metadata: {e}")
            return False
        
        success = True
        
        for volume_info in volume_metadata:
            if volume_info.get('status') == 'success' and volume_info.get('backup_file'):
                try:
                    self._restore_single_volume(volume_info, volumes_dir)
                    self.logger.info(f"Restored volume: {volume_info['name']}")
                except Exception as e:
                    self.logger.error(f"Failed to restore volume {volume_info['name']}: {e}")
                    success = False
        
        return success
    
    def _restore_single_volume(self, volume_info: Dict[str, Any], volumes_dir: Path) -> None:
        """Restore a single Docker volume."""
        volume_name = volume_info['name']
        backup_file = Path(volume_info['backup_file'])
        
        # Check if backup file exists (handle both absolute and relative paths)
        if not backup_file.is_absolute():
            backup_file = volumes_dir / backup_file.name
        
        if not backup_file.exists():
            raise Exception(f"Backup file not found: {backup_file}")
        
        try:
            # Remove existing volume if it exists
            subprocess.run([
                'docker', 'volume', 'rm', volume_name
            ], capture_output=True, text=True, check=False)  # Don't fail if volume doesn't exist
            
            # Create new volume
            subprocess.run([
                'docker', 'volume', 'create', volume_name
            ], check=True)
            
            # Restore data using a temporary container
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Copy backup to temp directory
                temp_backup = temp_path / backup_file.name
                shutil.copy2(backup_file, temp_backup)
                
                container_name = f"revertit-restore-{volume_name}-{int(datetime.now().timestamp())}"
                
                # Run container to restore the data
                subprocess.run([
                    'docker', 'run', '--rm',
                    '-v', f'{volume_name}:/volume',
                    '-v', f'{temp_path}:/backup',
                    '--name', container_name,
                    'alpine', 'sh', '-c', 
                    f'cd /volume && tar xzf /backup/{backup_file.name}'
                ], check=True)
                
                self.logger.debug(f"Volume {volume_name} restored from {backup_file}")
                
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to restore volume {volume_name}: {e}")
    
    def get_volume_usage_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get usage statistics for all volumes."""
        stats = {}
        
        try:
            result = subprocess.run([
                'docker', 'volume', 'ls', '--format', '{{.Name}}'
            ], capture_output=True, text=True, check=True)
            
            volumes = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            
            for volume in volumes:
                try:
                    # Get volume size using temporary container
                    size_result = subprocess.run([
                        'docker', 'run', '--rm',
                        '-v', f'{volume}:/volume:ro',
                        'alpine', 'du', '-sb', '/volume'
                    ], capture_output=True, text=True, check=True)
                    
                    size_bytes = int(size_result.stdout.split()[0])
                    
                    volume_info = self._get_volume_info(volume)
                    
                    stats[volume] = {
                        'size_bytes': size_bytes,
                        'size_mb': round(size_bytes / (1024 * 1024), 2),
                        'mountpoint': volume_info.get('Mountpoint', 'unknown'),
                        'driver': volume_info.get('Driver', 'local'),
                        'created': volume_info.get('CreatedAt', 'unknown')
                    }
                    
                except Exception as e:
                    stats[volume] = {
                        'error': str(e),
                        'size_bytes': 0,
                        'size_mb': 0
                    }
            
        except Exception as e:
            self.logger.error(f"Failed to get volume stats: {e}")
        
        return stats
    
    def cleanup_unused_volumes(self, dry_run: bool = True) -> List[str]:
        """Clean up unused Docker volumes."""
        try:
            if dry_run:
                result = subprocess.run([
                    'docker', 'volume', 'prune', '--dry-run', '--filter', 'label!=keep=true'
                ], capture_output=True, text=True, check=True)
                
                # Parse output to get list of volumes that would be removed
                volumes_to_remove = []
                for line in result.stdout.split('\n'):
                    if 'would remove' in line.lower():
                        # Extract volume names from output
                        pass  # This would need parsing based on Docker output format
                
                return volumes_to_remove
            else:
                result = subprocess.run([
                    'docker', 'volume', 'prune', '-f', '--filter', 'label!=keep=true'
                ], capture_output=True, text=True, check=True)
                
                self.logger.info("Cleaned up unused volumes")
                return []
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to cleanup volumes: {e}")
            return []
