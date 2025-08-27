# RevertIT Docker Integration

## Overview

The enhanced RevertIT system now includes comprehensive Docker integration, extending its snapshot capabilities to include:

- **Docker volumes backup and restoration**
- **Database dumps (PostgreSQL, InfluxDB, MinIO)**  
- **Docker Compose configurations backup**
- **Container state preservation**
- **Observability stack-specific optimizations**

## Architecture

The Docker integration consists of several key components:

### Core Components

1. **EnhancedSnapshotManager** (`src/revertit/snapshot/enhanced_manager.py`)
   - Extends the original SnapshotManager
   - Orchestrates system + Docker snapshots
   - Provides unified CLI interface

2. **DockerSnapshotManager** (`src/revertit/docker/manager.py`)
   - Handles Docker-specific backup operations
   - Coordinates volume and database backups
   - Manages container configurations

3. **VolumeBackupManager** (`src/revertit/docker/volumes.py`)
   - Backs up Docker volumes using tar archives
   - Supports critical volume identification
   - Handles volume restoration

4. **DatabaseBackupManager** (`src/revertit/docker/databases.py`)
   - PostgreSQL database dumps
   - InfluxDB backup support
   - MinIO object storage backup

### Configuration

The Docker integration is configured via `/opt/revertit/config/docker/docker-config.yaml`:

```yaml
docker:
  backup_volumes: true
  backup_databases: true  
  backup_compose_files: true

volumes:
  critical_volumes:
    - grafana_data
    - postgres_data
    - prometheus_data
    - influxdb_data
    - minio_data
    - portainer_data

databases:
  database_configs:
    postgres:
      container_name: postgres
      type: postgresql
      databases: [grafana]
      username: grafana
```

## Usage

### Enhanced CLI

The enhanced RevertIT CLI is available at `/opt/revertit/revertit-enhanced`:

```bash
# Show enhanced status with Docker information
./revertit-enhanced status

# Create enhanced snapshot (includes Docker components)
./revertit-enhanced snapshots create --description "Pre-maintenance snapshot"

# List snapshots with Docker metadata
./revertit-enhanced snapshots list

# Restore enhanced snapshot
./revertit-enhanced snapshots restore --snapshot-id <snapshot_id>

# Docker-specific commands
./revertit-enhanced docker info        # Show Docker environment
./revertit-enhanced docker volumes     # Show volume statistics  
./revertit-enhanced docker databases   # Show database statistics
./revertit-enhanced docker test        # Test Docker integration
```

### Snapshot Structure

Enhanced snapshots include:

```
/var/lib/revertit/snapshots/<snapshot_id>/
├── docker/
│   ├── volumes/
│   │   ├── grafana_data.tar.gz
│   │   ├── postgres_data.tar.gz
│   │   └── volumes_metadata.json
│   ├── databases/
│   │   ├── postgres_postgresql/
│   │   │   ├── grafana.sql
│   │   │   ├── grafana_schema.sql
│   │   │   └── grafana_dashboard.sql
│   │   └── databases_metadata.json
│   ├── compose/
│   │   ├── docker-compose.yml
│   │   └── configs/
│   │       ├── traefik-config/
│   │       ├── grafana/
│   │       └── scripts/
│   ├── containers/
│   │   └── containers.json
│   └── docker_metadata.json
├── enhanced_metadata.json
└── ... (system files)
```

## Features

### Volume Backup

- **Automatic discovery** of Docker volumes
- **Critical volume protection** - ensures observability stack volumes are always backed up
- **Compressed backups** using tar.gz
- **Incremental exclusions** - skip temporary/cache volumes
- **Parallel processing** support (configurable)

### Database Backup

- **PostgreSQL**: Full dumps + schema + individual table exports
- **InfluxDB**: Bucket-specific backups using native tools  
- **MinIO**: Object storage mirroring
- **Custom database support** via configuration

### Configuration Preservation

- **Docker Compose files** backup
- **Configuration directories** (/opt/traefik-config, /opt/grafana, etc.)
- **Container metadata** and runtime configuration
- **Network definitions** and volume mappings

### Observability Stack Integration

Optimized for common observability components:

- **Grafana**: Dashboard, datasource, user, and plugin preservation
- **Prometheus**: Configuration and rule backup  
- **InfluxDB**: Bucket-specific data and configuration
- **MinIO**: Object storage with selective bucket backup
- **Traefik**: Configuration and SSL certificate preservation
- **Vector, Blackbox, Node Exporter**: Configuration backup

## Security Considerations

- **Credential protection**: Database passwords stored securely in environment variables
- **File permissions**: Backups maintain original ownership and permissions
- **Network isolation**: Operations use existing Docker networks
- **Temporary containers**: Backup processes use ephemeral containers

## Performance

- **Parallel operations**: Volume backups can run concurrently
- **Compression**: All backups use gzip compression
- **Incremental sizing**: Metadata tracks backup sizes
- **Cleanup automation**: Old snapshots automatically pruned

## Integration with Existing RevertIT

The Docker integration seamlessly extends existing RevertIT functionality:

- **Backward compatibility**: Existing snapshots continue to work
- **Unified interface**: Single CLI for all operations  
- **Configuration inheritance**: Uses existing RevertIT configuration structure
- **Logging integration**: Docker operations logged via RevertIT logging system
- **Timeout handling**: Docker operations respect RevertIT timeout settings

## Troubleshooting

### Common Issues

1. **Docker not available**
   ```bash
   ./revertit-enhanced docker test
   # Check Docker installation and permissions
   ```

2. **Volume backup failures**  
   ```bash
   ./revertit-enhanced docker volumes
   # Check volume accessibility and disk space
   ```

3. **Database connection issues**
   ```bash
   ./revertit-enhanced docker databases  
   # Verify container names and credentials
   ```

### Log Analysis

Enhanced RevertIT logs Docker operations:

```bash
tail -f /var/log/revertit.log | grep -i docker
```

### Manual Recovery

If automated restoration fails:

```bash
# List backup contents
tar -tzf /var/lib/revertit/snapshots/<id>/docker/volumes/grafana_data.tar.gz

# Manual volume restoration
docker volume create grafana_data
docker run --rm -v grafana_data:/volume -v /backup:/backup alpine \
    sh -c "cd /volume && tar xzf /backup/grafana_data.tar.gz"
```

## Best Practices

1. **Regular testing**: Run `docker test` periodically
2. **Snapshot before changes**: Create snapshots before major configuration changes  
3. **Monitor storage**: Docker backups can be large - monitor available space
4. **Verify restorations**: Test restore procedures in non-production environments
5. **Update configurations**: Keep database credentials and paths current in config files

## Configuration Examples

### Custom Volume Selection

```yaml
volumes:
  include_only:
    - critical_app_data
    - user_uploads
  exclude_volumes:
    - temp_cache
    - log_files
```

### Additional Database Types

```yaml
databases:
  database_configs:
    redis:
      container_name: redis  
      type: redis
      backup_command: redis-cli BGSAVE
```

### Advanced Docker Settings

```yaml
advanced:
  docker_timeout: 600
  max_parallel_backups: 5
  stop_containers_on_restore: true
```

## Monitoring and Alerts

The enhanced system provides metrics and alerting capabilities:

- Backup success/failure rates
- Backup size trends  
- Database connectivity monitoring
- Volume usage statistics
- Container health status

These can be integrated with your existing observability stack for comprehensive monitoring.
