"""Tests for the CLI module."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from meshctl.cli import main


def test_main_help():
    """Test that the main command shows help."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "A CLI tool for mesh operations" in result.output


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


@patch("meshctl.discover.NearbyNodeDiscoverer")
def test_discover_command_connection_failure(mock_discoverer_class):
    """Test discover command handles connection failure gracefully."""
    mock_discoverer = Mock()
    mock_discoverer.connect.return_value = False
    mock_discoverer.discover_nearby_nodes.return_value = []
    mock_discoverer_class.return_value = mock_discoverer

    runner = CliRunner()
    result = runner.invoke(main, ["discover", "--duration", "1"])

    assert result.exit_code == 0
    # Verify the discoverer was created and discovery method was called
    mock_discoverer_class.assert_called_once()
    mock_discoverer.discover_nearby_nodes.assert_called_once()
    assert "No nearby nodes found" in result.output


@patch("meshctl.list_nodes.connect")
def test_list_nodes_command_connection_failure(mock_connect):
    """Test list-nodes command handles connection failure gracefully."""
    mock_connect.return_value = None

    runner = CliRunner()
    result = runner.invoke(main, ["list-nodes"])

    assert result.exit_code == 0
    assert "Failed to connect" in result.output


@patch("meshctl.discover.NearbyNodeDiscoverer")
def test_discover_command_with_tcp_interface(mock_discoverer_class):
    """Test discover command with TCP interface option."""
    mock_discoverer = Mock()
    mock_discoverer.connect.return_value = False
    mock_discoverer.discover_nearby_nodes.return_value = []
    mock_discoverer_class.return_value = mock_discoverer

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "discover",
            "--interface-type",
            "tcp",
            "--address",
            "test.local",
            "--duration",
            "1",
        ],
    )

    # Should attempt to use TCP interface
    assert result.exit_code == 0
    # Check that the correct parameters were passed
    mock_discoverer_class.assert_called_once_with(
        interface_type="tcp",
        device_path="test.local",
        debug=False,
        test_run_id=None,
        csv_file=None,
    )
    mock_discoverer.discover_nearby_nodes.assert_called_once()
    assert "No nearby nodes found" in result.output


@patch("meshctl.list_nodes.connect")
def test_list_nodes_command_with_tcp_interface(mock_connect):
    """Test list-nodes command with TCP interface option."""
    mock_connect.return_value = None

    runner = CliRunner()
    result = runner.invoke(
        main, ["list-nodes", "--interface-type", "tcp", "--address", "test.local"]
    )

    # Should attempt to use TCP interface
    assert result.exit_code == 0
    assert "Failed to connect" in result.output


def test_scan_ble_command_help():
    """Test that the scan-ble command shows help."""
    runner = CliRunner()
    result = runner.invoke(main, ["scan-ble", "--help"])
    assert result.exit_code == 0
    assert "Scan for Meshtastic BLE devices" in result.output


@patch("meshctl.scan_ble.meshtastic.ble_interface.BLEInterface.scan")
def test_scan_ble_command_success(mock_scan):
    """Test scan-ble command with successful scan."""
    mock_device = Mock()
    mock_device.name = "Test Device"
    mock_device.address = "AA:BB:CC:DD:EE:FF"
    mock_scan.return_value = [mock_device]

    runner = CliRunner()
    result = runner.invoke(main, ["scan-ble"])

    assert result.exit_code == 0
    assert "Scanning for BLE devices" in result.output
    assert "Test Device" in result.output
    assert "AA:BB:CC:DD:EE:FF" in result.output


@patch("meshctl.scan_ble.meshtastic.ble_interface.BLEInterface.scan")
def test_scan_ble_command_no_devices(mock_scan):
    """Test scan-ble command with no devices found."""
    mock_scan.return_value = []

    runner = CliRunner()
    result = runner.invoke(main, ["scan-ble"])

    assert result.exit_code == 0
    assert "No BLE devices found" in result.output


@patch("meshctl.scan_ble.meshtastic.ble_interface.BLEInterface.scan")
def test_scan_ble_command_error(mock_scan):
    """Test scan-ble command with scan error."""
    mock_scan.side_effect = Exception("Scan failed")

    runner = CliRunner()
    result = runner.invoke(main, ["scan-ble"])

    assert result.exit_code == 0
    assert "Error during BLE scan" in result.output
