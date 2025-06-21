"""Tests for the CLI module."""

from unittest.mock import patch

from click.testing import CliRunner

from meshcli.cli import main


def test_main_help():
    """Test that the main command shows help."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "A CLI tool for mesh operations" in result.output


def test_hello_command():
    """Test the hello command."""
    runner = CliRunner()
    result = runner.invoke(main, ["hello"])
    assert result.exit_code == 0
    assert "Hello World!" in result.output


def test_hello_command_with_name():
    """Test the hello command with a custom name."""
    runner = CliRunner()
    result = runner.invoke(main, ["hello", "--name", "Alice"])
    assert result.exit_code == 0
    assert "Hello Alice!" in result.output


def test_discover_command_help():
    """Test that the discover command shows help."""
    runner = CliRunner()
    result = runner.invoke(main, ["discover", "--help"])
    assert result.exit_code == 0
    assert "Discover nearby Meshtastic nodes" in result.output


def test_list_nodes_command_help():
    """Test that the list-nodes command shows help."""
    runner = CliRunner()
    result = runner.invoke(main, ["list-nodes", "--help"])
    assert result.exit_code == 0
    assert "Show currently known nodes" in result.output


@patch("meshcli.discover.meshtastic.serial_interface.SerialInterface")
def test_discover_command_connection_failure(mock_serial):
    """Test discover command handles connection failure gracefully."""
    mock_serial.side_effect = Exception("Connection failed")

    runner = CliRunner()
    result = runner.invoke(main, ["discover", "--duration", "1"])

    assert result.exit_code == 0
    assert "Failed to connect" in result.output


@patch("meshcli.list_nodes.meshtastic.serial_interface.SerialInterface")
def test_list_nodes_command_connection_failure(mock_serial):
    """Test list-nodes command handles connection failure gracefully."""
    mock_serial.side_effect = Exception("Connection failed")

    runner = CliRunner()
    result = runner.invoke(main, ["list-nodes"])

    assert result.exit_code == 0
    assert "Failed to connect" in result.output


@patch("meshcli.discover.meshtastic.serial_interface.SerialInterface")
def test_discover_command_with_tcp_interface(mock_serial):
    """Test discover command with TCP interface option."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["discover", "--interface", "tcp", "--device", "test.local", "--duration", "1"],
    )

    # Should attempt to use TCP interface
    assert result.exit_code == 0


@patch("meshcli.list_nodes.meshtastic.serial_interface.SerialInterface")
def test_list_nodes_command_with_tcp_interface(mock_serial):
    """Test list-nodes command with TCP interface option."""
    runner = CliRunner()
    result = runner.invoke(
        main, ["list-nodes", "--interface", "tcp", "--device", "test.local"]
    )

    # Should attempt to use TCP interface
    assert result.exit_code == 0
