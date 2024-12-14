"""
SFTP Handler module for managing EDI file transfers.

This module provides functionality to interact with SFTP servers,
including downloading 810 files and uploading 997 acknowledgments.
"""

import os
import paramiko
from pathlib import Path
from typing import List, Optional, Dict
import logging
import posixpath
import stat
from datetime import datetime

class SFTPHandler:
    """
    Handles SFTP operations for EDI file transfers.
    
    Attributes:
        hostname (str): SFTP server hostname
        username (str): SFTP username
        password (str): SFTP password
        port (int): SFTP port number
        home_dir (str): Base directory for SFTP operations
    """
    
    def __init__(self, hostname: str, username: str, password: str, home_dir: str = "/", port: int = 22):
        """
        Initialize SFTP handler with connection details.
        
        Args:
            hostname: SFTP server hostname
            username: SFTP username
            password: SFTP password
            home_dir: Base directory for SFTP operations (default: "/")
            port: SFTP port number (default: 22)
        """
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.home_dir = home_dir.rstrip("/")
        self.ssh = None
        self.sftp = None
        self.logger = logging.getLogger(__name__)

    def _validate_path(self, path: str) -> str:
        """
        Validate and normalize a path to ensure it doesn't escape the home directory.
        
        Args:
            path: Path to validate
            
        Returns:
            str: Normalized path relative to home directory
            
        Raises:
            ValueError: If path attempts to escape home directory
        """
        # If path is absolute, make it relative to home_dir
        if path.startswith('/'):
            # Remove leading slash for joining
            rel_path = path.lstrip('/')
        else:
            rel_path = path

        # Join with home directory and normalize
        full_path = posixpath.join(self.home_dir, rel_path)
        normalized = posixpath.normpath(full_path)
        
        # Ensure the normalized path starts with home_dir
        if not normalized.startswith(self.home_dir):
            raise ValueError(f"Access denied: Path {path} attempts to escape home directory {self.home_dir}")
            
        return normalized

    def connect(self) -> None:
        """
        Establish SFTP connection.
        
        Raises:
            paramiko.SSHException: If connection or authentication fails
            Exception: For other connection-related errors
        """
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password
            )
            self.sftp = self.ssh.open_sftp()
            self.logger.info("Successfully connected to SFTP server")
        except Exception as e:
            self.logger.error(f"Failed to connect to SFTP server: {str(e)}")
            raise

    def disconnect(self) -> None:
        """
        Safely disconnect from the SFTP server.
        Ensures both SFTP and SSH connections are properly closed.
        """
        try:
            if self.sftp:
                self.sftp.close()
                self.sftp = None
            if self.ssh:
                self.ssh.close()
                self.ssh = None
            self.logger.info("Successfully disconnected from SFTP server")
        except Exception as e:
            self.logger.error(f"Error during SFTP disconnect: {str(e)}")
            raise

    def list_directory(self, remote_path: str = ".") -> List[Dict]:
        """
        List contents of a directory with file/folder information.
        
        Args:
            remote_path: Remote directory path to list (default: current directory)
            
        Returns:
            List of dictionaries containing file information:
            {
                'name': str,  # File/directory name
                'type': str,  # 'file' or 'directory'
                'size': int,  # File size in bytes (0 for directories)
                'modified': str  # Last modified timestamp
            }
        """
        try:
            validated_path = self._validate_path(remote_path)
            files = []
            for entry in self.sftp.listdir_attr(validated_path):
                # Format the timestamp consistently
                modified_time = datetime.fromtimestamp(entry.st_mtime)
                formatted_time = modified_time.strftime("%Y-%m-%d %H:%M:%S")
                
                file_info = {
                    'name': entry.filename,
                    'type': 'directory' if stat.S_ISDIR(entry.st_mode) else 'file',
                    'size': entry.st_size,
                    'modified': formatted_time
                }
                files.append(file_info)
            return sorted(files, key=lambda x: x['modified'], reverse=True)
        except Exception as e:
            self.logger.error(f"Failed to list directory {remote_path}: {str(e)}")
            raise

    def list_files(self, directory: str) -> List[Dict]:
        """
        List files in the specified directory.
        
        Args:
            directory: Directory path relative to home directory
            
        Returns:
            List of dictionaries containing file information
        """
        try:
            path = self._validate_path(directory)
            files = []
            for entry in self.sftp.listdir_attr(path):
                if stat.S_ISREG(entry.st_mode):  # If it's a regular file
                    files.append({
                        'name': entry.filename,
                        'size': entry.st_size,
                        'mtime': datetime.fromtimestamp(entry.st_mtime)
                    })
            return files
        except Exception as e:
            self.logger.error(f"Error listing files in {directory}: {str(e)}")
            raise

    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        Download file from SFTP server.
        
        Args:
            remote_path: Path to remote file
            local_path: Path to save file locally
            
        Raises:
            paramiko.SFTPError: If file download fails
            ValueError: If remote path is outside home directory
        """
        try:
            validated_path = self._validate_path(remote_path)
            self.sftp.get(validated_path, local_path)
        except paramiko.SFTPError as e:
            self.logger.error(f"Failed to download file {remote_path}: {str(e)}")
            raise
        except ValueError as e:
            self.logger.error(str(e))
            raise

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """
        Upload a file to SFTP server.
        
        Args:
            local_path: Path to local file
            remote_path: Remote path relative to home directory
        """
        try:
            remote_path = self._validate_path(remote_path)
            
            # Ensure remote directory exists
            remote_dir = os.path.dirname(remote_path)
            try:
                self.sftp.stat(remote_dir)
            except FileNotFoundError:
                self.sftp.mkdir(remote_dir)
            
            # Upload file
            self.sftp.put(local_path, remote_path)
            self.logger.info(f"Successfully uploaded file to {remote_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to upload file to {remote_path}: {str(e)}")
            raise

    def move_remote_file(self, source_path: str, dest_path: str) -> None:
        """
        Move file on remote SFTP server.
        
        Args:
            source_path: Current path of remote file
            dest_path: New path for remote file
            
        Raises:
            paramiko.SFTPError: If file move fails
            ValueError: If either path is outside home directory
        """
        try:
            validated_source = self._validate_path(source_path)
            validated_dest = self._validate_path(dest_path)
            
            # Ensure destination directory exists
            dest_dir = '/'.join(validated_dest.split('/')[:-1])
            self.ensure_remote_directory_exists(dest_dir)
            
            try:
                # Try POSIX rename first
                self.sftp.posix_rename(validated_source, validated_dest)
            except (IOError, OSError):
                # If POSIX rename fails, fallback to copy and delete
                self.logger.info(f"POSIX rename not supported, falling back to copy and delete for {source_path}")
                
                # Copy the file
                file_data = self.sftp.open(validated_source, 'rb').read()
                with self.sftp.open(validated_dest, 'wb') as dest:
                    dest.write(file_data)
                
                # Delete the source file
                self.sftp.remove(validated_source)
                
        except Exception as e:
            self.logger.error(f"Failed to move file from {source_path} to {dest_path}: {str(e)}")
            raise

    def move_file(self, source_path: str, destination_path: str) -> None:
        """
        Move a file from source path to destination path on the SFTP server.
        
        Args:
            source_path: Source file path relative to home directory
            destination_path: Destination file path relative to home directory
        """
        try:
            src = self._validate_path(source_path)
            dst = self._validate_path(destination_path)
            
            # Ensure destination directory exists
            dst_dir = os.path.dirname(dst)
            try:
                self.sftp.stat(dst_dir)
            except FileNotFoundError:
                self.sftp.mkdir(dst_dir)
            
            # Move the file
            self.sftp.rename(src, dst)
            self.logger.info(f"Successfully moved file from {source_path} to {destination_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to move file from {source_path} to {destination_path}: {str(e)}")
            raise

    def ensure_remote_directory_exists(self, remote_path: str) -> None:
        """
        Ensure remote directory exists, create if it doesn't.
        
        Args:
            remote_path: Remote directory path
            
        Raises:
            paramiko.SFTPError: If directory creation fails
            ValueError: If path is outside home directory
        """
        try:
            validated_path = self._validate_path(remote_path)
            try:
                self.sftp.stat(validated_path)
            except FileNotFoundError:
                self.sftp.mkdir(validated_path)
        except paramiko.SFTPError as e:
            self.logger.error(f"Failed to create directory {remote_path}: {str(e)}")
            raise
        except ValueError as e:
            self.logger.error(str(e))
            raise

    def get_current_directory(self) -> str:
        """Get the current working directory on the SFTP server"""
        try:
            return self.sftp.getcwd() or '.'
        except Exception as e:
            self.logger.error(f"Error getting current directory: {str(e)}")
            return '.'

    def change_to_parent_directory(self):
        """Change to parent directory"""
        try:
            current = self.get_current_directory()
            if current != '.':
                parent = posixpath.dirname(current)
                self.sftp.chdir(parent if parent else '.')
        except Exception as e:
            self.logger.error(f"Error changing to parent directory: {str(e)}")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
