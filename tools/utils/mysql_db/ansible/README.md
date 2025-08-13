# MySQL Stack (Docker + Backups) — Ansible Role

This role deploys MySQL (in Docker) plus a backup service with cron.
Data and configuration are stored in bind mounts (default `/srv/mysql`), making it easy to move to another disk.

## Requirements
- Ansible 2.15+
- Collection: `community.docker`
  ```bash
  ansible-galaxy collection install community.docker
  ```
- Docker/Compose on the target host (the role can install it automatically via `mysql_install_docker`).

## Repository layout
```text
repo/
├─ inventories/
│  └─ prod/
│     ├─ hosts.ini
│     └─ group_vars/
│        ├─ db.yml
│        └─ vault.yml < Edit to change default passwords
├─ playbooks/
│  └─ site.yml
└─ roles/
   └─ mysql_stack/
      ├─ defaults/
      ├─ handlers/
      ├─ tasks/
      └─ templates/
```

## Basic deployment
```bash
ansible-playbook -i inventories/prod/hosts.ini playbooks/site.yml -e mysql_root_password='StrongRoot!' -e mysql_app_password='StrongApp!'
```
Or by vault.yaml
```bash
ansible-playbook -i inventories/prod/hosts.ini playbooks/site.yml --extra-vars "@inventories/prod/group_vars/vault.yml"
```
> Prefer Ansible Vault for secrets (see below).

## Manual backup (run now)
```bash
ansible-playbook -i inventories/prod/hosts.ini playbooks/site.yml --tags backup_now
```

## Restore from dump
Put the dump file on the remote host first, then:
```bash
ansible-playbook -i inventories/prod/hosts.ini playbooks/site.yml --tags restore -e mysql_restore_src="/srv/mysql/backups/app_YYYYmmdd_HHMMSS.sql.gz" -e mysql_restore_drop_db=true
```

## Storage auto-mount & migration
To format a new disk, migrate existing data, and mount it at `mysql_stack_root` in one go:
```bash
ansible-playbook -i inventories/prod/hosts.ini playbooks/site.yml \
  -e mysql_manage_storage=true \
  -e mysql_mount_device=/dev/sdb \
  -e mysql_device_mountpoint=/mnt/storage \
  -e mysql_subdir_name=mysql \
  -e mysql_mount_fstype=ext4 \
  -e mysql_mount_create_fs=true \
  -e mysql_migrate_existing=true
```
The role will:
1) Mounts the entire device at mysql_device_mountpoint (e.g., /mnt/storage). 
2) Creates the subdirectory mysql_data_dir = /mnt/storage/mysql. 
3) Copies the current data into it (if mysql_migrate_existing is enabled). 
4) Bind-mounts mysql_data_dir → /srv/mysql (so the role/Compose don’t need to change anything). 
5) Brings the stack back up.

**Use with care**: make sure `/dev/sdb` is the correct device.

## Using Ansible Vault for passwords
Create an encrypted vars file:
```bash
ansible-vault create inventories/prod/group_vars/vault.yml
```
Put variables inside:
```yaml
mysql_root_password: "StrongRoot!"
mysql_app_password:  "StrongApp!"
```
Then run the playbook with:
```bash
ansible-playbook -i inventories/prod/hosts.ini playbooks/site.yml --extra-vars "@inventories/prod/group_vars/vault.yml"
```
Alternatively, pass secrets via `-e` or your CI secret manager.
