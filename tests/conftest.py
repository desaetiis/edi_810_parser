"""
Shared pytest fixtures for EDI parser tests.

This module contains fixtures that can be shared across multiple test files.
"""

import pytest
import tempfile
import os
from pathlib import Path

@pytest.fixture
def sample_edi_content():
    """Fixture providing sample EDI 810 content."""
    return """ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *200505*1234*U*00401*000000001*0*P*>~
GS*IN*SENDER*RECEIVER*20200505*1234*1*X*004010~
ST*810*0001~
BIG*20200505*1234567*20200505*PO123456**~
N1*ST*CUSTOMER NAME*92*1234567890~
N3*123 MAIN ST~
N4*ANYTOWN*NY*12345~
ITD*01*3*0**30**60~
IT1*1*1*EA*100.00**UP*123456789012~
TDS*10000.00~
CAD*D*30~
CTT*1~
SE*11*0001~
GE*1*1~
IEA*1*000000001~"""

@pytest.fixture
def temp_test_dir():
    """Fixture providing a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)

@pytest.fixture
def sample_edi_file(temp_test_dir, sample_edi_content):
    """Fixture providing a sample EDI file."""
    file_path = temp_test_dir / "test.edi"
    with open(file_path, "w") as f:
        f.write(sample_edi_content)
    return file_path

@pytest.fixture
def env_setup():
    """Fixture for setting up test environment variables."""
    original_env = dict(os.environ)
    
    # Set test environment variables
    os.environ.update({
        'SFTP_TEST_HOST': 'test.host',
        'SFTP_TEST_USER': 'test_user',
        'SFTP_TEST_PASS': 'test_pass'
    })
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
