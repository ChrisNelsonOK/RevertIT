#!/usr/bin/env python3
"""
Database Backup Manager - Handles database backups for containerized databases.
"""

import json
import logging
import subprocess
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import tempfile


class DatabaseBackupManager:
    """Manages database backup and restoration for containerized databases."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize database backup manager."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Database configurations
        self.db_configs = config.get('database_configs', {})
        
        # Default database configurations for common observability stack databases
        self.default_configs = {
            'postgres': {
                'container_name': 'postgres',
                'type': 'postgresql',
                'port': 5432,
                'databases': ['grafana'],
                'username': 'grafana',
                'password_env': 'POSTGRES_PASSWORD',
                'password_value': '$w33t@55T3a!',
                'backup_command': 'pg_dump',
                'restore_command': 'psql'
            },
            'influxdb': {
                'container_name': 'influxdb',
                'type': 'influxdb',
                'port': 8086,
                'organization': 'rectitude',
                'bucket': 'r369',
                'token_env': 'INFLUXDB_TOKEN',
                'backup_command': 'influx backup',
                'restore_command': 'influx restore'
            },
            'minio': {
                'container_name': 'minio',
                'type': 'minio',
                'port': 9000,
                'access_key': 'admin',
                'secret_key': '$w33t@55T3a!',
                'backup_command': 'mc mirror',
                'restore_command': 'mc mirror'
            }
        }
        
        # Merge user configs with defaults
        for db_name, default_config in self.default_configs.items():
            if db_name not in self.db_configs:
                self.db_configs[db_name] = default_config
            else:
                # Update default with user overrides
                merged_config = default_config.copy()
                merged_config.update(self.db_configs[db_name])
                self.db_configs[db_name] = merged_config
        
        self.logger.info(f"Database Backup Manager initialized with {len(self.db_configs)} database configs")
    
    def backup_databases(self, snapshot_dir: Path) -> List[Dict[str, Any]]:
        """Backup all configured databases."""
        db_dir = snapshot_dir / "databases"
        db_dir.mkdir(exist_ok=True)
        
        backup_metadata = []
        
        # Check which databases are actually running
        running_containers = self._get_running_containers()
        
        for db_name, db_config in self.db_configs.items():
            container_name = db_config.get('container_name')
            
            if container_name in running_containers:
                try:
                    db_metadata = self._backup_database(db_name, db_config, db_dir)
                    backup_metadata.append(db_metadata)
                    self.logger.info(f"Backed up database: {db_name}")
                except Exception as e:
                    error_msg = f"Failed to backup database {db_name}: {e}"
                    self.logger.error(error_msg)
                    backup_metadata.append({
                        'name': db_name,
                        'container': container_name,
                        'status': 'failed',
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })
            else:
                self.logger.info(f"Database container {container_name} not running, skipping {db_name}")
        
        # Save database backup metadata
        metadata_file = db_dir / "databases_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(backup_metadata, f, indent=2)
        
        return backup_metadata
    
    def _get_running_containers(self) -> List[str]:
        """Get list of currently running container names."""
        try:
            result = subprocess.run([
                'docker', 'ps', '--format', '{{.Names}}'
            ], capture_output=True, text=True, check=True)
            
            return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to get running containers: {e}")
            return []
    
    def _backup_database(self, db_name: str, db_config: Dict[str, Any], db_dir: Path) -> Dict[str, Any]:
        """Backup a specific database."""
        db_type = db_config.get('type', 'unknown')
        container_name = db_config.get('container_name')
        
        backup_metadata = {
            'name': db_name,
            'type': db_type,
            'container': container_name,
            'timestamp': datetime.now().isoformat(),
            'status': 'success',
            'backup_files': [],
            'size_bytes': 0
        }
        
        try:
            if db_type == 'postgresql':
                backup_metadata = self._backup_postgresql(db_name, db_config, db_dir, backup_metadata)
            elif db_type == 'influxdb':
                backup_metadata = self._backup_influxdb(db_name, db_config, db_dir, backup_metadata)
            elif db_type == 'minio':
                backup_metadata = self._backup_minio(db_name, db_config, db_dir, backup_metadata)
            else:
                raise Exception(f"Unsupported database type: {db_type}")
                
        except Exception as e:
            backup_metadata['status'] = 'failed'
            backup_metadata['error'] = str(e)
            raise e
        
        return backup_metadata
    
    def _backup_postgresql(self, db_name: str, db_config: Dict[str, Any], db_dir: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Backup PostgreSQL database."""
        container_name = db_config['container_name']
        databases = db_config.get('databases', ['grafana'])
        username = db_config.get('username', 'grafana')
        
        pg_backup_dir = db_dir / f"{db_name}_postgresql"
        pg_backup_dir.mkdir(exist_ok=True)
        
        for database in databases:
            try:
                # Dump each database
                backup_file = pg_backup_dir / f"{database}.sql"
                
                dump_cmd = [
                    'docker', 'exec', container_name,
                    'pg_dump', '-U', username, '-d', database,
                    '--no-password', '--verbose'
                ]
                
                with open(backup_file, 'w') as f:
                    result = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True, check=True)
                
                # Also dump database schema separately
                schema_file = pg_backup_dir / f"{database}_schema.sql"
                schema_cmd = [
                    'docker', 'exec', container_name,
                    'pg_dump', '-U', username, '-d', database,
                    '--schema-only', '--no-password'
                ]
                
                with open(schema_file, 'w') as f:
                    subprocess.run(schema_cmd, stdout=f, stderr=subprocess.PIPE, text=True, check=True)
                
                # Export specific tables with data
                tables_of_interest = ['dashboard', 'data_source', 'user', 'org', 'preferences']
                for table in tables_of_interest:
                    try:
                        table_file = pg_backup_dir / f"{database}_{table}.sql"
                        table_cmd = [
                            'docker', 'exec', container_name,
                            'pg_dump', '-U', username, '-d', database,
                            '--table', table, '--data-only', '--column-inserts',
                            '--no-password'
                        ]
                        
                        with open(table_file, 'w') as f:
                            subprocess.run(table_cmd, stdout=f, stderr=subprocess.PIPE, text=True, check=True)
                        
                        if table_file.stat().st_size > 0:
                            metadata['backup_files'].append({
                                'file': str(table_file),
                                'type': 'table_data',
                                'table': table,
                                'database': database,
                                'size': table_file.stat().st_size
                            })
                    except subprocess.CalledProcessError:
                        # Table might not exist, continue
                        pass
                
                metadata['backup_files'].extend([
                    {
                        'file': str(backup_file),
                        'type': 'full_dump',
                        'database': database,
                        'size': backup_file.stat().st_size
                    },
                    {
                        'file': str(schema_file),
                        'type': 'schema',
                        'database': database,
                        'size': schema_file.stat().st_size
                    }
                ])
                
                self.logger.debug(f"PostgreSQL database {database} backed up")
                
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to backup PostgreSQL database {database}: {e.stderr if e.stderr else e}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        
        # Calculate total size
        metadata['size_bytes'] = sum(f['size'] for f in metadata['backup_files'])
        return metadata
    
    def _backup_influxdb(self, db_name: str, db_config: Dict[str, Any], db_dir: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Backup InfluxDB database."""
        container_name = db_config['container_name']
        organization = db_config.get('organization', 'rectitude')
        bucket = db_config.get('bucket', 'r369')
        
        influx_backup_dir = db_dir / f"{db_name}_influxdb"
        influx_backup_dir.mkdir(exist_ok=True)
        
        try:
            # Backup InfluxDB using influx CLI
            backup_cmd = [
                'docker', 'exec', container_name,
                'influx', 'backup', 
                '--org', organization,
                '--bucket', bucket,
                '/tmp/influx_backup'
            ]
            
            # First create backup inside container
            subprocess.run(backup_cmd, check=True, capture_output=True, text=True)
            
            # Copy backup from container to host
            copy_cmd = [
                'docker', 'cp', 
                f'{container_name}:/tmp/influx_backup',
                str(influx_backup_dir)
            ]
            
            subprocess.run(copy_cmd, check=True)
            
            # List backup files
            backup_files = []
            for backup_file in influx_backup_dir.rglob('*'):
                if backup_file.is_file():
                    backup_files.append({
                        'file': str(backup_file),
                        'type': 'influx_backup',
                        'size': backup_file.stat().st_size
                    })
            
            metadata['backup_files'] = backup_files
            metadata['size_bytes'] = sum(f['size'] for f in backup_files)
            
            self.logger.debug(f"InfluxDB backup completed for {organization}/{bucket}")
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to backup InfluxDB: {e.stderr if e.stderr else e}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        return metadata
    
    def _backup_minio(self, db_name: str, db_config: Dict[str, Any], db_dir: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Backup MinIO data and configuration."""
        container_name = db_config['container_name']
        
        minio_backup_dir = db_dir / f"{db_name}_minio"
        minio_backup_dir.mkdir(exist_ok=True)
        
        try:
            # Create a temporary directory in the container
            subprocess.run([
                'docker', 'exec', container_name,
                'mkdir', '-p', '/tmp/minio_backup'
            ], check=True)
            
            # Get list of buckets
            list_cmd = [
                'docker', 'exec', container_name,
                'mc', 'ls', 'local/'
            ]
            
            result = subprocess.run(list_cmd, capture_output=True, text=True, check=True)
            buckets = [line.split()[-1].rstrip('/') for line in result.stdout.strip().split('\n') if line.strip()]
            
            backup_files = []
            
            # Backup each bucket
            for bucket in buckets:
                try:
                    bucket_backup = f"/tmp/minio_backup/{bucket}"
                    
                    # Create bucket backup directory
                    subprocess.run([
                        'docker', 'exec', container_name,
                        'mkdir', '-p', bucket_backup
                    ], check=True)
                    
                    # Mirror bucket contents
                    mirror_cmd = [
                        'docker', 'exec', container_name,
                        'mc', 'mirror', f'local/{bucket}', bucket_backup
                    ]
                    
                    subprocess.run(mirror_cmd, check=True, capture_output=True)
                    
                    self.logger.debug(f"MinIO bucket {bucket} backed up")
                    
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Failed to backup MinIO bucket {bucket}: {e}")
            
            # Copy backup from container to host
            copy_cmd = [
                'docker', 'cp', 
                f'{container_name}:/tmp/minio_backup/',
                str(minio_backup_dir)
            ]
            
            subprocess.run(copy_cmd, check=True)
            
            # List backup files and calculate sizes
            for backup_file in minio_backup_dir.rglob('*'):
                if backup_file.is_file():
                    backup_files.append({
                        'file': str(backup_file),
                        'type': 'minio_object',
                        'size': backup_file.stat().st_size
                    })
            
            metadata['backup_files'] = backup_files
            metadata['size_bytes'] = sum(f['size'] for f in backup_files)
            
            self.logger.debug(f"MinIO backup completed")
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to backup MinIO: {e.stderr if e.stderr else e}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        return metadata
    
    def restore_databases(self, snapshot_dir: Path) -> bool:
        """Restore databases from backup."""
        db_dir = snapshot_dir / "databases"
        
        if not db_dir.exists():
            self.logger.warning("No database backups found to restore")
            return True
        
        # Load database metadata
        metadata_file = db_dir / "databases_metadata.json"
        if not metadata_file.exists():
            self.logger.error("Database backup metadata not found")
            return False
        
        try:
            with open(metadata_file) as f:
                db_metadata = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load database metadata: {e}")
            return False
        
        success = True
        
        for db_info in db_metadata:
            if db_info.get('status') == 'success':
                try:
                    self._restore_database(db_info, db_dir)
                    self.logger.info(f"Restored database: {db_info['name']}")
                except Exception as e:
                    self.logger.error(f"Failed to restore database {db_info['name']}: {e}")
                    success = False
        
        return success
    
    def _restore_database(self, db_info: Dict[str, Any], db_dir: Path) -> None:
        """Restore a specific database."""
        db_type = db_info.get('type')
        db_name = db_info.get('name')
        
        if db_type == 'postgresql':
            self._restore_postgresql(db_info, db_dir)
        elif db_type == 'influxdb':
            self._restore_influxdb(db_info, db_dir)
        elif db_type == 'minio':
            self._restore_minio(db_info, db_dir)
        else:
            raise Exception(f"Unsupported database type for restore: {db_type}")
    
    def _restore_postgresql(self, db_info: Dict[str, Any], db_dir: Path) -> None:
        """Restore PostgreSQL database."""
        container_name = db_info['container']
        db_name = db_info['name']
        
        pg_backup_dir = db_dir / f"{db_name}_postgresql"
        
        if not pg_backup_dir.exists():
            raise Exception(f"PostgreSQL backup directory not found: {pg_backup_dir}")
        
        # Get database config
        db_config = self.db_configs.get(db_name, {})
        username = db_config.get('username', 'grafana')
        databases = db_config.get('databases', ['grafana'])
        
        for database in databases:
            backup_file = pg_backup_dir / f"{database}.sql"
            
            if backup_file.exists():
                try:
                    # Restore database from backup
                    restore_cmd = [
                        'docker', 'exec', '-i', container_name,
                        'psql', '-U', username, '-d', database
                    ]
                    
                    with open(backup_file, 'r') as f:
                        subprocess.run(restore_cmd, stdin=f, check=True, capture_output=True, text=True)
                    
                    self.logger.debug(f"PostgreSQL database {database} restored")
                    
                except subprocess.CalledProcessError as e:
                    error_msg = f"Failed to restore PostgreSQL database {database}: {e.stderr if e.stderr else e}"
                    raise Exception(error_msg)
    
    def _restore_influxdb(self, db_info: Dict[str, Any], db_dir: Path) -> None:
        """Restore InfluxDB database."""
        # Implementation would go here - more complex due to InfluxDB 2.x restore process
        self.logger.warning("InfluxDB restore not yet implemented")
    
    def _restore_minio(self, db_info: Dict[str, Any], db_dir: Path) -> None:
        """Restore MinIO data."""
        # Implementation would go here - restore objects to buckets
        self.logger.warning("MinIO restore not yet implemented")
    
    def get_database_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all configured databases."""
        stats = {}
        running_containers = self._get_running_containers()
        
        for db_name, db_config in self.db_configs.items():
            container_name = db_config.get('container_name')
            
            if container_name in running_containers:
                try:
                    db_stats = self._get_database_stats(db_name, db_config)
                    stats[db_name] = db_stats
                except Exception as e:
                    stats[db_name] = {'error': str(e), 'status': 'failed'}
            else:
                stats[db_name] = {'status': 'not_running'}
        
        return stats
    
    def _get_database_stats(self, db_name: str, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Get statistics for a specific database."""
        db_type = db_config.get('type')
        container_name = db_config.get('container_name')
        
        if db_type == 'postgresql':
            return self._get_postgresql_stats(db_config)
        elif db_type == 'influxdb':
            return self._get_influxdb_stats(db_config)
        elif db_type == 'minio':
            return self._get_minio_stats(db_config)
        else:
            return {'error': f'Unsupported database type: {db_type}'}
    
    def _get_postgresql_stats(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Get PostgreSQL statistics."""
        container_name = db_config['container_name']
        username = db_config.get('username', 'grafana')
        databases = db_config.get('databases', ['grafana'])
        
        stats = {'type': 'postgresql', 'databases': {}}
        
        for database in databases:
            try:
                # Get database size
                size_cmd = [
                    'docker', 'exec', container_name,
                    'psql', '-U', username, '-d', database, '-t', '-c',
                    "SELECT pg_size_pretty(pg_database_size(current_database()));"
                ]
                
                result = subprocess.run(size_cmd, capture_output=True, text=True, check=True)
                db_size = result.stdout.strip()
                
                # Get table count
                table_cmd = [
                    'docker', 'exec', container_name,
                    'psql', '-U', username, '-d', database, '-t', '-c',
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
                ]
                
                result = subprocess.run(table_cmd, capture_output=True, text=True, check=True)
                table_count = int(result.stdout.strip())
                
                stats['databases'][database] = {
                    'size': db_size,
                    'table_count': table_count,
                    'status': 'accessible'
                }
                
            except Exception as e:
                stats['databases'][database] = {
                    'error': str(e),
                    'status': 'error'
                }
        
        return stats
    
    def _get_influxdb_stats(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Get InfluxDB statistics."""
        return {'type': 'influxdb', 'status': 'stats_not_implemented'}
    
    def _get_minio_stats(self, db_config: Dict[str, Any]) -> Dict[str, Any]:
        """Get MinIO statistics."""
        return {'type': 'minio', 'status': 'stats_not_implemented'}
