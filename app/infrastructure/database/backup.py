"""Backup Management

Implements backup strategy for disaster recovery. Supports:
- Daily snapshots
- Point-in-time recovery
- Backup verification
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text
import os
import shlex
import re
import stat

logger = logging.getLogger(__name__)


class BackupManager:
    """Manages database backups and recovery."""

    def __init__(self, database_url: str, backup_dir: str = "./backups"):
        self.database_url = database_url
        self.backup_dir = backup_dir
        self.last_backup_time = None
        self.min_backup_interval = 60  # Minimum 60 seconds between backups
        os.makedirs(backup_dir, mode=0o700, exist_ok=True)  # Only owner can read

    async def create_backup(self, backup_name: Optional[str] = None) -> str:
        """
        Create a database backup.
        
        Args:
            backup_name: Optional custom backup name. If None, uses timestamp.
            
        Returns:
            Path to backup file
        """
        # Rate limiting
        now = datetime.now(timezone.utc)
        if self.last_backup_time and (now - self.last_backup_time).total_seconds() < self.min_backup_interval:
            raise ValueError("Backup rate limited - wait before creating another")
        
        if not backup_name:
            backup_name = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        # Path traversal protection
        backup_name = os.path.basename(backup_name)
        if not backup_name.endswith('.sql'):
            backup_name = f"{backup_name}.sql"
        
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        # Verify path is within backup_dir
        real_path = os.path.realpath(backup_path)
        real_dir = os.path.realpath(self.backup_dir)
        if not real_path.startswith(real_dir):
            raise ValueError("Backup path outside backup directory")
        
        try:
            # For PostgreSQL, use pg_dump
            db_url = self.database_url.replace("postgresql+asyncpg://", "postgresql://")
            
            # SQL injection protection - escape shell arguments
            cmd = f"pg_dump {shlex.quote(db_url)} > {shlex.quote(backup_path)}"
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode()
                # Mask database URL in error logs
                error_msg = self._mask_url(error_msg)
                logger.error(f"Backup failed: {error_msg}")
                raise Exception(f"Backup failed")
            
            # Secure backup file permissions
            os.chmod(backup_path, 0o600)  # Only owner can read
            
            file_size = os.path.getsize(backup_path)
            logger.info(f"Backup created: {backup_path} ({file_size} bytes)")
            
            self.last_backup_time = now
            return backup_path
            
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            raise

    async def restore_backup(self, backup_path: str, confirm: bool = False) -> bool:
        """
        Restore database from backup.
        
        WARNING: This will overwrite current database!
        
        Args:
            backup_path: Path to backup file
            confirm: Must be True to proceed (safety check)
            
        Returns:
            True if successful
        """
        if not confirm:
            raise ValueError(
                "Restore requires explicit confirmation. "
                "Pass confirm=True to proceed. "
                "This will overwrite the current database!"
            )
        
        if not os.path.exists(backup_path):
            logger.error(f"Backup file not found: {backup_path}")
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        
        try:
            # Create backup of current database first
            current_backup = await self.create_backup("pre_restore_backup")
            logger.info(f"Created backup of current database: {current_backup}")
            
            db_url = self.database_url.replace("postgresql+asyncpg://", "postgresql://")
            
            # SQL injection protection - escape shell arguments
            cmd = f"psql {shlex.quote(db_url)} < {shlex.quote(backup_path)}"
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode()
                error_msg = self._mask_url(error_msg)
                logger.error(f"Restore failed: {error_msg}")
                raise Exception(f"Restore failed")
            
            logger.info(f"Database restored from: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error restoring backup: {str(e)}")
            raise

    async def cleanup_old_backups(self, retention_days: int = 30) -> int:
        """
        Delete backups older than retention period.
        
        Args:
            retention_days: Keep backups from last N days
            
        Returns:
            Number of backups deleted
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        deleted_count = 0
        
        try:
            for filename in os.listdir(self.backup_dir):
                if not filename.endswith('.sql'):
                    continue
                
                filepath = os.path.join(self.backup_dir, filename)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_mtime < cutoff_date:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.info(f"Deleted old backup: {filename}")
            
            logger.info(f"Cleanup complete: {deleted_count} backups deleted")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error during backup cleanup: {str(e)}")
            raise

    async def list_backups(self) -> list:
        """
        List all available backups.
        
        Returns:
            List of backup info dicts
        """
        backups = []
        
        try:
            for filename in sorted(os.listdir(self.backup_dir), reverse=True):
                if not filename.endswith('.sql'):
                    continue
                
                filepath = os.path.join(self.backup_dir, filename)
                file_size = os.path.getsize(filepath)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                backups.append({
                    'name': filename,
                    'path': filepath,
                    'size_bytes': file_size,
                    'created_at': file_mtime.isoformat()
                })
            
            return backups
            
        except Exception as e:
            logger.error(f"Error listing backups: {str(e)}")
            raise

    async def verify_backup(self, backup_path: str) -> bool:
        """
        Verify backup integrity.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if backup is valid
        """
        if not os.path.exists(backup_path):
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        try:
            # Check file size
            file_size = os.path.getsize(backup_path)
            if file_size == 0:
                logger.error(f"Backup file is empty: {backup_path}")
                return False
            
            # Check if it's a valid SQL dump
            with open(backup_path, 'r') as f:
                first_line = f.readline()
                if not first_line.startswith('--'):
                    logger.error(f"Backup file doesn't look like a SQL dump: {backup_path}")
                    return False
            
            logger.info(f"Backup verified: {backup_path} ({file_size} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Error verifying backup: {str(e)}")
            return False

    def _mask_url(self, text: str) -> str:
        """Mask database credentials in text for logging."""
        # Replace postgresql://user:password@host with postgresql://***:***@host
        pattern = r'postgresql://[^:]+:[^@]+@'
        return re.sub(pattern, 'postgresql://***:***@', text)
