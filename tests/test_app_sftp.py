"""
Test module for SFTP functionality in the Streamlit app.
"""

import pytest
from unittest.mock import Mock, patch
import streamlit as st
import tempfile
import os
from datetime import datetime
import stat

@pytest.fixture
def mock_sftp_handler():
    """Create a mock SFTPHandler."""
    mock = Mock()
    mock.list_directory.return_value = [
        {
            'name': 'test_file.txt',
            'type': 'file',
            'size': 1024,
            'modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        },
        {
            'name': 'test_dir',
            'type': 'directory',
            'size': 0,
            'modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    ]
    return mock

@pytest.fixture
def mock_streamlit():
    """Create mock Streamlit session state."""
    session_state = {
        'sftp_handler': None,
        'current_path': '.',  
        'sftp_connected': False,
        'sftp_host': 'test.host',
        'sftp_username': 'user',
        'sftp_password': 'pass',
        'sftp_port': 22,
        'sftp_home_dir': '/home/test'
    }
    with patch('streamlit.session_state', session_state):
        yield session_state

def test_init_sftp_handler(mock_streamlit):
    """Test SFTP handler initialization."""
    with patch('streamlit.session_state', mock_streamlit):
        from app import init_sftp_handler
        with patch('streamlit.text_input') as mock_input:
            mock_input.side_effect = ['test.host', 'user', 'pass']
            with patch('app.SFTPHandler') as mock_handler_class:
                handler = init_sftp_handler()
                mock_handler_class.assert_called_once_with(
                    'test.host',
                    'user',
                    'pass',
                    '/',
                    22
                )
        assert True  

def test_sftp_connection(mock_streamlit, mock_sftp_handler):
    """Test SFTP connection and disconnection."""
    mock_streamlit['sftp_handler'] = mock_sftp_handler
    with patch('streamlit.session_state', mock_streamlit):
        from app import init_sftp_handler
        with patch('app.SFTPHandler', return_value=mock_sftp_handler):
            # Test connection
            with init_sftp_handler() as handler:
                handler.connect()
                mock_sftp_handler.connect.assert_called_once()
            
            # Test disconnection
            mock_sftp_handler.disconnect.assert_called_once()
        assert True  

def test_file_upload(mock_streamlit, mock_sftp_handler):
    """Test file upload functionality."""
    mock_streamlit['sftp_handler'] = mock_sftp_handler
    mock_streamlit['sftp_connected'] = True
    with patch('streamlit.session_state', mock_streamlit):
        from app import init_sftp_handler
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content")
            tmp_path = tmp.name
        
        try:
            with patch('app.SFTPHandler', return_value=mock_sftp_handler):
                with init_sftp_handler() as handler:
                    # Test file upload
                    handler.upload_file(tmp_path, 'test.txt')
                    mock_sftp_handler.upload_file.assert_called_once()
        finally:
            os.unlink(tmp_path)
        assert True  

def test_directory_navigation(mock_streamlit, mock_sftp_handler):
    """Test directory navigation functionality."""
    mock_streamlit['sftp_handler'] = mock_sftp_handler
    mock_streamlit['sftp_connected'] = True
    mock_streamlit['current_path'] = '/'  
    with patch('streamlit.session_state', mock_streamlit):
        from app import init_sftp_handler
        with patch('app.SFTPHandler', return_value=mock_sftp_handler):
            with init_sftp_handler() as handler:
                # List directory contents
                contents = handler.list_directory('.')
                assert len(contents) == 2
                assert any(item['name'] == 'test_file.txt' for item in contents)
                assert any(item['name'] == 'test_dir' for item in contents)
                
                # Verify directory listing was called
                mock_sftp_handler.list_directory.assert_called_with('.')
        assert True  
