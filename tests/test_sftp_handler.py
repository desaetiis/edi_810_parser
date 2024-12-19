"""
Test module for SFTPHandler class.
"""

import os
import pytest
import paramiko
from unittest.mock import Mock, patch
from datetime import datetime
import stat

from sftp_handler import SFTPHandler

@pytest.fixture
def mock_sftp():
    """Create a mock SFTP client."""
    mock = Mock()
    mock.listdir_attr.return_value = [
        Mock(
            filename='test_file.txt',
            st_mode=stat.S_IFREG,  # Regular file
            st_size=1024,
            st_mtime=datetime.now().timestamp()
        ),
        Mock(
            filename='test_dir',
            st_mode=stat.S_IFDIR,  # Directory
            st_size=0,
            st_mtime=datetime.now().timestamp()
        )
    ]
    return mock

@pytest.fixture
def mock_ssh():
    """Create a mock SSH client."""
    mock = Mock()
    return mock

@pytest.fixture
def sftp_handler(mock_sftp, mock_ssh):
    """Create an SFTPHandler instance with mocked SFTP and SSH clients."""
    handler = SFTPHandler('test.host', 'user', 'pass', '/home/test')
    handler.sftp = mock_sftp
    handler.ssh = mock_ssh
    return handler

def test_init():
    """Test SFTPHandler initialization."""
    handler = SFTPHandler('test.host', 'user', 'pass', '/home/test')
    assert handler.hostname == 'test.host'
    assert handler.username == 'user'
    assert handler.password == 'pass'
    assert handler.home_dir == '/home/test'
    assert handler.port == 22

def test_validate_path_inside_home(sftp_handler):
    """Test path validation for paths inside home directory."""
    test_path = "test.txt"
    result = sftp_handler._validate_path(test_path)
    assert result == '/home/test/test.txt'

def test_validate_path_outside_home(sftp_handler):
    """Test path validation for paths outside home directory."""
    test_path = "../outside/test.txt"
    with pytest.raises(ValueError):
        sftp_handler._validate_path(test_path)

def test_list_directory(sftp_handler, mock_sftp):
    """Test directory listing functionality."""
    current_time = datetime.now()
    mock_attrs = [
        Mock(
            filename='test_file.txt',
            st_mode=stat.S_IFREG,
            st_size=1024,
            st_mtime=current_time.timestamp()
        )
    ]
    mock_sftp.listdir_attr.return_value = mock_attrs
    result = sftp_handler.list_directory("/test")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]['name'] == 'test_file.txt'
    assert result[0]['type'] == 'file'
    assert result[0]['size'] == 1024
    assert isinstance(result[0]['modified'], str)

def test_connect_disconnect(sftp_handler, mock_ssh):
    """Test connection and disconnection."""
    # Test connect
    with patch('paramiko.SSHClient', return_value=mock_ssh):
        sftp_handler.connect()
        mock_ssh.connect.assert_called_once_with(
            hostname='test.host',
            username='user',
            password='pass',
            port=22
        )
    
    # Test disconnect
    sftp_handler.disconnect()
    mock_ssh.close.assert_called_once()
    assert sftp_handler.ssh is None
    assert sftp_handler.sftp is None

def test_upload_file(sftp_handler, mock_sftp):
    """Test file upload functionality."""
    local_path = 'local_test.txt'
    remote_path = 'remote_test.txt'
    
    sftp_handler.upload_file(local_path, remote_path)
    mock_sftp.put.assert_called_once_with(local_path, '/home/test/remote_test.txt')

def test_download_file(sftp_handler, mock_sftp):
    """Test file download functionality."""
    local_path = 'local_test.txt'
    remote_path = 'remote_test.txt'
    
    sftp_handler.download_file(remote_path, local_path)
    mock_sftp.get.assert_called_once_with('/home/test/remote_test.txt', local_path)

def test_error_handling(sftp_handler, mock_sftp):
    """Test error handling in SFTP operations."""
    mock_sftp.listdir_attr.side_effect = paramiko.SFTPError("Test error")
    
    with pytest.raises(Exception):
        sftp_handler.list_directory('.')
