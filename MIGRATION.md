# RevertIT Migration Guide

This document provides guidance for migrating from older versions of RevertIT to the current version, including command changes, deprecation timelines, and update procedures.

## Table of Contents

- [Version Migration Overview](#version-migration-overview)
- [Command Name Changes](#command-name-changes)
- [Deprecation Timeline](#deprecation-timeline)
- [Migration Shims](#migration-shims)
- [Updating Existing Installations](#updating-existing-installations)
- [Breaking Changes](#breaking-changes)
- [Configuration Migration](#configuration-migration)

## Version Migration Overview

RevertIT follows semantic versioning. This guide covers migrations from:
- **0.x.x** (Beta) → **1.0.0** (Stable)
- **1.0.x** → **1.1.x** (Current)

## Command Name Changes

### CLI Commands

The following command-line interface changes have been made:

| Old Command | New Command | Notes |
|-------------|-------------|-------|
| `revertit-status` | `revertit status` | Subcommand structure |
| `revertit-confirm` | `revertit confirm` | Subcommand structure |
| `revertit-snapshot` | `revertit snapshots` | Pluralized for consistency |
| `revertit-timeout` | `revertit timeouts` | Pluralized for consistency |
| `revertit-test` | `revertit test` | Subcommand structure |

### Daemon Commands

| Old Command | New Command | Notes |
|-------------|-------------|-------|
| `revertit-daemon` | `revertitd` | Shorter, follows daemon naming convention |
| `revertit-daemon start` | `systemctl start revertit` | Managed by systemd |
| `revertit-daemon stop` | `systemctl stop revertit` | Managed by systemd |

### Service Names

| Old Service | New Service | Notes |
|-------------|-------------|-------|
| `revertit-daemon.service` | `revertit.service` | Simplified service name |

## Deprecation Timeline

### Phase 1: Soft Deprecation (v1.0.0 - v1.2.0)
- **Duration**: 6 months (January 2024 - June 2024)
- Old commands continue to work with deprecation warnings
- All documentation updated to use new commands
- Migration shims installed by default

### Phase 2: Hard Deprecation (v1.3.0 - v1.4.0)
- **Duration**: 3 months (July 2024 - September 2024)
- Old commands require explicit flag `--legacy` to work
- Deprecation warnings become errors without flag
- Migration shims available but not installed by default

### Phase 3: Removal (v2.0.0+)
- **Target Date**: October 2024
- Old commands completely removed
- Migration shims no longer provided
- Clean break for major version

## Migration Shims

To ease the transition, we provide compatibility shims that map old commands to new ones.

### Installing Migration Shims

```bash
# During installation
sudo ./scripts/install.sh --with-shims

# Or manually after installation
sudo revertit migrate install-shims
```

### What Shims Do

The shims create symbolic links from old command names to a wrapper script that:
1. Shows a deprecation warning
2. Translates old command syntax to new
3. Executes the new command
4. Logs usage for migration tracking

### Shim Locations

Shims are installed in `/usr/local/bin/` with the following structure:
```
/usr/local/bin/
├── revertit-status -> /usr/lib/revertit/shims/legacy-wrapper
├── revertit-confirm -> /usr/lib/revertit/shims/legacy-wrapper
├── revertit-snapshot -> /usr/lib/revertit/shims/legacy-wrapper
├── revertit-timeout -> /usr/lib/revertit/shims/legacy-wrapper
└── revertit-daemon -> /usr/lib/revertit/shims/daemon-wrapper
```

### Removing Shims

Once you've updated all scripts and workflows:
```bash
sudo revertit migrate remove-shims
```

## Updating Existing Installations

### Step 1: Backup Current Configuration

```bash
# Backup configuration and data
sudo cp -r /etc/revertit /etc/revertit.backup
sudo cp -r /var/lib/revertit /var/lib/revertit.backup
```

### Step 2: Stop Current Service

```bash
# For old versions
sudo systemctl stop revertit-daemon
# Or
sudo revertit-daemon stop
```

### Step 3: Update Package

#### Using Package Manager (Recommended)
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install revertit

# RHEL/CentOS/Fedora
sudo yum update revertit
# or
sudo dnf update revertit
```

#### Using Git
```bash
cd /path/to/revertit
git pull origin main
sudo ./scripts/install.sh --upgrade --with-shims
```

### Step 4: Migrate Configuration

```bash
# Automatic migration
sudo revertit migrate config

# Or manual review
sudo revertit migrate check-config
```

### Step 5: Update Service Files

```bash
# Disable old service
sudo systemctl disable revertit-daemon

# Enable new service
sudo systemctl enable revertit
sudo systemctl start revertit
```

### Step 6: Update Scripts and Cron Jobs

Search for old commands in your scripts:
```bash
# Find scripts using old commands
grep -r "revertit-" /usr/local/bin/ /etc/cron* /home/*/.bashrc

# Update systemd service files
grep -r "revertit-daemon" /etc/systemd/system/
```

Example script updates:
```bash
# Old
#!/bin/bash
revertit-status
revertit-confirm $CHANGE_ID

# New
#!/bin/bash
revertit status
revertit confirm $CHANGE_ID
```

### Step 7: Verify Migration

```bash
# Check service status
sudo systemctl status revertit

# Test CLI commands
revertit status
revertit test

# Check for any remaining old commands
which revertit-status  # Should show shim location or not found
```

## Breaking Changes

### Configuration File Changes

#### Renamed Sections
- `[daemon]` → `[global]`
- `[timeouts]` → `[timeout]`
- `[monitors]` → `[monitoring]`

#### New Required Fields
```yaml
# Version 1.0.0+ requires
global:
  version: "1.0"  # Configuration version
  instance_name: "production"  # Instance identifier
```

### API Changes

If using RevertIT programmatically:

```python
# Old
from revertit import RevertITDaemon
daemon = RevertITDaemon()

# New
from revertit.daemon import Daemon
daemon = Daemon(config_path="/etc/revertit/config.yaml")
```

### File Location Changes

| Old Location | New Location |
|--------------|--------------|
| `/var/run/revertit-daemon.pid` | `/var/run/revertit.pid` |
| `/var/log/revertit-daemon.log` | `/var/log/revertit.log` |
| `/etc/revertit/daemon.conf` | `/etc/revertit/config.yaml` |

## Configuration Migration

### Automatic Migration

```bash
# Check what will be migrated
sudo revertit migrate check-config --dry-run

# Perform migration
sudo revertit migrate config
```

### Manual Migration Example

Old format (`/etc/revertit/daemon.conf`):
```ini
[daemon]
timeout = 300
log_level = INFO

[timeouts]
network = 600
ssh = 900
firewall = 300

[monitors]
watch_network = yes
watch_ssh = yes
```

New format (`/etc/revertit/config.yaml`):
```yaml
global:
  version: "1.0"
  instance_name: "production"
  default_timeout: 300
  log_level: INFO

timeout:
  network_changes: 600
  ssh_changes: 900
  firewall_changes: 300

monitoring:
  enabled_categories:
    - network
    - ssh
    - firewall
```

## Troubleshooting Migration

### Common Issues

#### 1. Service Won't Start After Update
```bash
# Check for config issues
sudo revertit test
sudo journalctl -u revertit -n 50

# Validate configuration
sudo revertit validate-config
```

#### 2. Old Commands Still Being Used
```bash
# Check if shims are installed
ls -la /usr/local/bin/revertit-*

# Install shims if missing
sudo revertit migrate install-shims
```

#### 3. Permission Errors
```bash
# Fix permissions after migration
sudo chown -R root:root /etc/revertit
sudo chmod 600 /etc/revertit/config.yaml
sudo chmod 755 /var/lib/revertit
```

### Getting Help

- **Documentation**: Check `/usr/share/doc/revertit/` for updated docs
- **Migration Logs**: Review `/var/log/revertit-migration.log`
- **Support**: File issues at https://github.com/your-org/revertit/issues

## Post-Migration Checklist

- [ ] Service running with new name
- [ ] All scripts updated to use new commands
- [ ] Configuration migrated and validated
- [ ] Cron jobs updated
- [ ] Monitoring alerts updated
- [ ] Team notified of changes
- [ ] Shims installed for transition period
- [ ] Migration documented in change log

## Future Compatibility

To ensure smooth future migrations:

1. **Use Stable APIs**: Stick to documented command-line interfaces
2. **Version Lock**: Pin specific versions in production
3. **Test Updates**: Always test in staging environment first
4. **Monitor Deprecations**: Subscribe to release notes
5. **Gradual Rollout**: Update systems in phases

---

*Last Updated: January 2024*  
*Applies to: RevertIT v1.0.0 and later*
