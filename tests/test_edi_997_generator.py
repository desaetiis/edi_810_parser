"""
Tests for the EDI 997 Generator module.

This module contains test cases for the EDI997Generator class and its functionality.
"""

import pytest
from edi_997_generator import EDI997Generator, EDI997Config


@pytest.fixture
def default_config():
    """Fixture providing default EDI997 configuration."""
    return EDI997Config()


@pytest.fixture
def generator(default_config):
    """Fixture providing an EDI997Generator instance."""
    return EDI997Generator(default_config)


def test_generator_initialization(generator):
    """Test EDI997Generator initialization with default config."""
    assert generator is not None
    assert generator.config is not None
    assert generator.config.segment_terminator == "~"
    assert generator.config.element_separator == "*"


def test_custom_config():
    """Test EDI997Generator initialization with custom config."""
    custom_config = EDI997Config(
        segment_terminator="|",
        element_separator="^",
        sub_element_separator="&",
        line_ending="\r\n"
    )
    generator = EDI997Generator(custom_config)
    assert generator.config.segment_terminator == "|"
    assert generator.config.element_separator == "^"
    assert generator.config.sub_element_separator == "&"
    assert generator.config.line_ending == "\r\n"


def test_config_default_values():
    """Test EDI997Config default values."""
    config = EDI997Config()
    assert config.control_version_number == "00401"
    assert config.functional_id_code == "FA"
    assert config.acknowledgment_code == "A"
