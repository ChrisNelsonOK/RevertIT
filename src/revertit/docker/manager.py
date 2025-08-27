#!/usr/bin/env python3
"""
Docker Snapshot Manager - Enhanced backup support for Docker environments.
Integrates with the main RevertIT snapshot system to include:
- Docker volumes backup/restore
- Database dumps (PostgreSQL, MySQL, etc.)
- Container configurations
- Docker Compose configurations
"""

import json
import logging
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml

from .volumes import VolumeBackupManager
from .databases import DatabaseBackupManager


class DockerSnapshotManager:
    """Enhanced snapshot manager with Docker integration."""
    
    def __init__(self, config: Dict[str, Any], snapshot_location: Path):
        """Initialize Docker snapshot manager."""
        self.config = config
        self.snapshot_location = snapshot_location
        self.logger = logging.getLogger(__name__)
        
        # Initialize sub-managers
        self.volume_manager = VolumeBackupManager(config.get('volumes', {}))
        self.db_manager = DatabaseBackupManager(config.get('databases', {}))
        
        # Docker-specific settings
        self.docker_config = config.get('docker', {})
        self.backup_volumes = self.docker_config.get('backup_volumes', True)
        self.backup_databases = self.docker_config.get('backup_databases', True)
        self.backup_compose_files = self.docker_config.get('backup_compose_files', True)
        
        self.logger.info("Docker Snapshot Manager initialized")
    
    def create_docker_snapshot(self, snapshot_id: str, description: str) -> Dict[str, Any]:
        """Create comprehensive Docker environment snapshot."""
        self.logger.info(f"Creating Docker snapshot: {snapshot_id}")
        
        snapshot_dir = self.snapshot_location / snapshot_id / "docker"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        snapshot_metadata = {
            'id': snapshot_id,
            'timestamp': datetime.now().isoformat(),
            'description': description,
            'docker_components': {
                'volumes': [],
                'databases': [],
                'compose_files': [],
                'containers': []
            },
            'backup_size': 0,
            'errors': []
        }
        
        try:
            # 1. Backup Docker Compose configurations
            if self.backup_compose_files:
                self._backup_compose_files(snapshot_dir, snapshot_metadata)
            
            # 2. Backup Docker volumes
            if self.backup_volumes:
                self._backup_docker_volumes(snapshot_dir, snapshot_metadata)
            
            # 3. Backup databases
            if self.backup_databases:
                self._backup_databases(snapshot_dir, snapshot_metadata)
            
            # 4. Backup container configurations and states
            self._backup_container_info(snapshot_dir, snapshot_metadata)
            
            # 5. Calculate total backup size
            snapshot_metadata['backup_size'] = self._calculate_backup_size(snapshot_dir)
            
            # Save metadata
            metadata_file = snapshot_dir / "docker_metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(snapshot_metadata, f, indent=2)
            
            self.logger.info(f"Docker snapshot created successfully: {snapshot_id}")
            return snapshot_metadata
            
        except Exception as e:
            error_msg = f"Failed to create Docker snapshot: {e}"
            self.logger.error(error_msg)
            snapshot_metadata['errors'].append(error_msg)
            return snapshot_metadata
    
    def _backup_compose_files(self, snapshot_dir: Path, metadata: Dict[str, Any]) -> None:
        """Backup Docker Compose files and related configurations."""
        compose_dir = snapshot_dir / "compose"
        compose_dir.mkdir(exist_ok=True)
        
        compose_files = self.docker_config.get('compose_files', [
            '/opt/docker-compose.yml',
            '/opt/docker-compose.yaml',
            '/opt/compose.yml',
            '/opt/compose.yaml'
        ])
        
        # Add configuration directories
        config_dirs = self.docker_config.get('config_dirs', [
            '/opt/traefik-config',
            '/opt/grafana',
            '/opt/prometheus',
            '/opt/influxdb',
            '/opt/minio-config',
            '/opt/scripts'
        ])
        
        backed_up_files = []
        
        # Backup compose files
        for compose_file in compose_files:
            compose_path = Path(compose_file)
            if compose_path.exists():
                try:
                    dest_file = compose_dir / compose_path.name
                    shutil.copy2(compose_path, dest_file)
                    backed_up_files.append({
                        'path': str(compose_path),
                        'type': 'compose_file',
                        'size': compose_path.stat().st_size
                    })
                    self.logger.debug(f"Backed up compose file: {compose_path}")
                except Exception as e:
                    error_msg = f"Failed to backup compose file {compose_path}: {e}"
                    self.logger.warning(error_msg)
                    metadata['errors'].append(error_msg)
        
        # Backup configuration directories
        for config_dir in config_dirs:
            config_path = Path(config_dir)
            if config_path.exists() and config_path.is_dir():
                try:
                    dest_dir = compose_dir / "configs" / config_path.name
                    shutil.copytree(config_path, dest_dir, dirs_exist_ok=True)
                    backed_up_files.append({
                        'path': str(config_path),
                        'type': 'config_directory',
                        'size': sum(f.stat().st_size for f in config_path.rglob('*') if f.is_file())
                    })
                    self.logger.debug(f"Backed up config directory: {config_path}")
                except Exception as e:
                    error_msg = f"Failed to backup config directory {config_path}: {e}"
                    self.logger.warning(error_msg)
                    metadata['errors'].append(error_msg)
        
        metadata['docker_components']['compose_files'] = backed_up_files
        self.logger.info(f"Backed up {len(backed_up_files)} compose/config items")
    
    def _backup_docker_volumes(self, snapshot_dir: Path, metadata: Dict[str, Any]) -> None:
        """Backup Docker volumes."""
        try:
            volumes_metadata = self.volume_manager.backup_volumes(snapshot_dir)
            metadata['docker_components']['volumes'] = volumes_metadata
            self.logger.info(f"Backed up {len(volumes_metadata)} Docker volumes")
        except Exception as e:
            error_msg = f"Volume backup failed: {e}"
            self.logger.error(error_msg)
            metadata['errors'].append(error_msg)
    
    def _backup_databases(self, snapshot_dir: Path, metadata: Dict[str, Any]) -> None:
        """Backup databases running in containers."""
        try:
            db_metadata = self.db_manager.backup_databases(snapshot_dir)
            metadata['docker_components']['databases'] = db_metadata
            self.logger.info(f"Backed up {len(db_metadata)} databases")
        except Exception as e:
            error_msg = f"Database backup failed: {e}"
            self.logger.error(error_msg)
            metadata['errors'].append(error_msg)
    
    def _backup_container_info(self, snapshot_dir: Path, metadata: Dict[str, Any]) -> None:
        """Backup container information and states."""
        containers_dir = snapshot_dir / "containers"
        containers_dir.mkdir(exist_ok=True)
        
        try:
            # Get all running containers
            result = subprocess.run([
                'docker', 'ps', '--format', 
                '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.Mounts}}'
            ], capture_output=True, text=True, check=True)
            
            container_info = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 5:
                        container_name = parts[0]
                        
                        # Get detailed container information
                        inspect_result = subprocess.run([
                            'docker', 'inspect', container_name
                        ], capture_output=True, text=True, check=True)
                        
                        container_details = json.loads(inspect_result.stdout)[0]
                        
                        container_info.append({
                            'name': container_name,
                            'image': parts[1],
                            'status': parts[2],
                            'ports': parts[3],
                            'mounts': parts[4],
                            'config': {
                                'env': container_details['Config']['Env'],
                                'cmd': container_details['Config']['Cmd'],
                                'working_dir': container_details['Config']['WorkingDir'],
                                'user': container_details['Config']['User']
                            },
                            'mounts_detail': container_details['Mounts']
                        })
            
            # Save container information
            containers_file = containers_dir / "containers.json"
            with open(containers_file, 'w') as f:
                json.dump(container_info, f, indent=2)
            
            metadata['docker_components']['containers'] = container_info
            self.logger.info(f"Backed up information for {len(container_info)} containers")
            
        except Exception as e:
            error_msg = f"Container info backup failed: {e}"
            self.logger.error(error_msg)
            metadata['errors'].append(error_msg)
    
    def _calculate_backup_size(self, snapshot_dir: Path) -> int:
        """Calculate total size of backup."""
        total_size = 0
        try:
            for path in snapshot_dir.rglob('*'):
                if path.is_file():
                    total_size += path.stat().st_size
        except Exception as e:
            self.logger.warning(f"Failed to calculate backup size: {e}")
        return total_size
    
    def restore_docker_snapshot(self, snapshot_id: str) -> bool:
        """Restore Docker environment from snapshot."""
        snapshot_dir = self.snapshot_location / snapshot_id / "docker"
        
        if not snapshot_dir.exists():
            self.logger.error(f"Docker snapshot not found: {snapshot_dir}")
            return False
        
        # Load metadata
        metadata_file = snapshot_dir / "docker_metadata.json"
        if not metadata_file.exists():
            self.logger.error(f"Docker snapshot metadata not found: {metadata_file}")
            return False
        
        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load Docker snapshot metadata: {e}")
            return False
        
        self.logger.info(f"Restoring Docker snapshot: {snapshot_id}")
        
        success = True
        
        try:
            # 1. Stop containers (if configured to do so)
            if self.docker_config.get('stop_containers_on_restore', False):
                self._stop_containers()
            
            # 2. Restore compose files and configurations
            if not self._restore_compose_files(snapshot_dir):
                success = False
            
            # 3. Restore volumes
            if not self.volume_manager.restore_volumes(snapshot_dir):
                success = False
            
            # 4. Restore databases
            if not self.db_manager.restore_databases(snapshot_dir):
                success = False
            
            # 5. Restart containers (if they were stopped)
            if self.docker_config.get('restart_containers_after_restore', True):
                self._restart_containers()
            
            self.logger.info(f"Docker snapshot restoration completed: {snapshot_id}")
            return success
            
        except Exception as e:
            self.logger.error(f"Docker snapshot restoration failed: {e}")
            return False
    
    def _restore_compose_files(self, snapshot_dir: Path) -> bool:
        """Restore Docker Compose files and configurations."""
        compose_dir = snapshot_dir / "compose"
        if not compose_dir.exists():
            self.logger.warning("No compose files to restore")
            return True
        
        success = True
        
        try:
            # Restore compose files to /opt
            for compose_file in compose_dir.glob('*.yml'):
                dest_path = Path('/opt') / compose_file.name
                shutil.copy2(compose_file, dest_path)
                self.logger.debug(f"Restored compose file: {dest_path}")
            
            for compose_file in compose_dir.glob('*.yaml'):
                dest_path = Path('/opt') / compose_file.name
                shutil.copy2(compose_file, dest_path)
                self.logger.debug(f"Restored compose file: {dest_path}")
            
            # Restore config directories
            configs_dir = compose_dir / "configs"
            if configs_dir.exists():
                for config_dir in configs_dir.iterdir():
                    if config_dir.is_dir():
                        dest_path = Path('/opt') / config_dir.name
                        if dest_path.exists():
                            shutil.rmtree(dest_path)
                        shutil.copytree(config_dir, dest_path)
                        self.logger.debug(f"Restored config directory: {dest_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to restore compose files: {e}")
            success = False
        
        return success
    
    def _stop_containers(self) -> None:
        """Stop all running containers."""
        try:
            self.logger.info("Stopping containers for restoration...")
            subprocess.run(['docker', 'compose', '-f', '/opt/docker-compose.yml', 'down'], 
                          check=True, cwd='/opt')
        except Exception as e:
            self.logger.warning(f"Failed to stop containers: {e}")
    
    def _restart_containers(self) -> None:
        """Restart containers after restoration."""
        try:
            self.logger.info("Restarting containers after restoration...")
            subprocess.run(['docker', 'compose', '-f', '/opt/docker-compose.yml', 'up', '-d'], 
                          check=True, cwd='/opt')
        except Exception as e:
            self.logger.error(f"Failed to restart containers: {e}")
    
    def list_docker_snapshots(self) -> List[Dict[str, Any]]:
        """List all Docker snapshots with metadata."""
        snapshots = []
        
        if not self.snapshot_location.exists():
            return snapshots
        
        for snapshot_dir in self.snapshot_location.iterdir():
            docker_dir = snapshot_dir / "docker"
            if docker_dir.exists():
                metadata_file = docker_dir / "docker_metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file) as f:
                            metadata = json.load(f)
                            snapshots.append(metadata)
                    except Exception as e:
                        self.logger.warning(f"Failed to load Docker metadata for {snapshot_dir.name}: {e}")
        
        return sorted(snapshots, key=lambda x: x.get('timestamp', ''), reverse=True)
    
    def get_docker_info(self) -> Dict[str, Any]:
        """Get current Docker environment information."""
        info = {
            'containers': [],
            'volumes': [],
            'networks': [],
            'compose_files': []
        }
        
        try:
            # Get containers
            result = subprocess.run([
                'docker', 'ps', '-a', '--format', 'json'
            ], capture_output=True, text=True, check=True)
            
            for line in result.stdout.strip().split('\n'):
                if line:
                    info['containers'].append(json.loads(line))
            
            # Get volumes
            result = subprocess.run([
                'docker', 'volume', 'ls', '--format', 'json'
            ], capture_output=True, text=True, check=True)
            
            for line in result.stdout.strip().split('\n'):
                if line:
                    info['volumes'].append(json.loads(line))
            
            # Check for compose files
            for compose_file in ['/opt/docker-compose.yml', '/opt/docker-compose.yaml']:
                if Path(compose_file).exists():
                    info['compose_files'].append(compose_file)
            
        except Exception as e:
            self.logger.error(f"Failed to get Docker info: {e}")
        
        return info
