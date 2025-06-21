"""Tests for the CLI module."""

import pytest
from click.testing import CliRunner
from meshcli.cli import main


def test_main_help():
    """Test that the main command shows help."""
    runner = CliRunner()
    result = runner.invoke(main, ['--help'])
    assert result.exit_code == 0
    assert 'A CLI tool for mesh operations' in result.output


def test_hello_command():
    """Test the hello command."""
    runner = CliRunner()
    result = runner.invoke(main, ['hello'])
    assert result.exit_code == 0
    assert 'Hello World!' in result.output


def test_hello_command_with_name():
    """Test the hello command with a custom name."""
    runner = CliRunner()
    result = runner.invoke(main, ['hello', '--name', 'Alice'])
    assert result.exit_code == 0
    assert 'Hello Alice!' in result.output
