"""Tests for the scan_ble module."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from meshctl.scan_ble import scan_ble


def test_scan_ble_command_help():
    """Test scan-ble command help output."""
    runner = CliRunner()
    result = runner.invoke(scan_ble, ["--help"])

    assert result.exit_code == 0
    assert "Scan for Meshtastic BLE devices" in result.output


@patch("meshctl.scan_ble.meshtastic.ble_interface.BLEInterface.scan")
def test_scan_ble_success(mock_scan):
    """Test successful BLE scan."""
    mock_device1 = Mock()
    mock_device1.name = "Meshtastic Device 1"
    mock_device1.address = "AA:BB:CC:DD:EE:FF"

    mock_device2 = Mock()
    mock_device2.name = "Meshtastic Device 2"
    mock_device2.address = "11:22:33:44:55:66"

    mock_scan.return_value = [mock_device1, mock_device2]

    runner = CliRunner()
    result = runner.invoke(scan_ble)

    assert result.exit_code == 0
    assert "Scanning for BLE devices" in result.output
    assert "Meshtastic Device 1" in result.output
    assert "AA:BB:CC:DD:EE:FF" in result.output
    assert "Meshtastic Device 2" in result.output
    assert "11:22:33:44:55:66" in result.output


@patch("meshctl.scan_ble.meshtastic.ble_interface.BLEInterface.scan")
def test_scan_ble_no_devices(mock_scan):
    """Test BLE scan with no devices found."""
    mock_scan.return_value = []

    runner = CliRunner()
    result = runner.invoke(scan_ble)

    assert result.exit_code == 0
    assert "Scanning for BLE devices" in result.output
    assert "No BLE devices found" in result.output


@patch("meshctl.scan_ble.meshtastic.ble_interface.BLEInterface.scan")
def test_scan_ble_error(mock_scan):
    """Test BLE scan with error."""
    mock_scan.side_effect = Exception("Bluetooth not available")

    runner = CliRunner()
    result = runner.invoke(scan_ble)

    assert result.exit_code == 0
    assert "Error during BLE scan" in result.output
    assert "Bluetooth not available" in result.output
