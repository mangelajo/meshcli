"""Tests for the list_nodes module."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from meshcli.list_nodes import NodeLister, list_nodes


class TestNodeLister:
    """Test the NodeLister class."""

    def test_init(self):
        """Test NodeLister initialization."""
        lister = NodeLister()
        assert lister.interface is None
        assert lister.interface_type == 'serial'
        assert lister.device_path is None

    def test_init_with_params(self):
        """Test NodeLister initialization with parameters."""
        lister = NodeLister(interface_type='tcp', device_path='test.local')
        assert lister.interface_type == 'tcp'
        assert lister.device_path == 'test.local'

    @patch('meshcli.list_nodes.meshtastic.serial_interface.SerialInterface')
    def test_connect_serial_success(self, mock_serial):
        """Test successful serial connection."""
        mock_interface = Mock()
        mock_serial.return_value = mock_interface
        
        lister = NodeLister()
        result = lister.connect()
        
        assert result is True
        mock_serial.assert_called_once()
        mock_interface.waitForConfig.assert_called_once()

    @patch('meshcli.list_nodes.meshtastic.serial_interface.SerialInterface')
    def test_connect_serial_failure(self, mock_serial):
        """Test failed serial connection."""
        mock_serial.side_effect = Exception("Connection failed")
        
        lister = NodeLister()
        result = lister.connect()
        
        assert result is False

    @patch('meshcli.list_nodes.meshtastic.tcp_interface.TCPInterface')
    def test_connect_tcp_success(self, mock_tcp):
        """Test successful TCP connection."""
        mock_interface = Mock()
        mock_tcp.return_value = mock_interface
        
        lister = NodeLister(interface_type='tcp', device_path='test.local')
        result = lister.connect()
        
        assert result is True
        mock_tcp.assert_called_once_with(hostname='test.local')
        mock_interface.waitForConfig.assert_called_once()

    def test_connect_invalid_interface(self):
        """Test connection with invalid interface type."""
        lister = NodeLister(interface_type='invalid')
        result = lister.connect()
        
        assert result is False

    @patch('meshcli.list_nodes.meshtastic.serial_interface.SerialInterface')
    def test_show_known_nodes_empty_database(self, mock_serial):
        """Test showing known nodes with empty database."""
        mock_interface = Mock()
        mock_interface.nodesByNum = {}
        mock_serial.return_value = mock_interface
        
        lister = NodeLister()
        
        with patch('meshcli.list_nodes.click.echo') as mock_echo:
            lister.show_known_nodes()
        
        # Should indicate empty database
        mock_echo.assert_any_call("  Node database is empty")

    @patch('meshcli.list_nodes.meshtastic.serial_interface.SerialInterface')
    def test_show_known_nodes_with_nodes(self, mock_serial):
        """Test showing known nodes with populated database."""
        mock_interface = Mock()
        mock_interface.localNode.nodeNum = 0x11111111
        mock_interface.nodesByNum = {
            0x22222222: {
                'user': {
                    'id': '!22222222',
                    'longName': 'Test Node'
                },
                'snr': 5.5,
                'lastHeard': 1640995200  # 2022-01-01 00:00:00
            }
        }
        mock_serial.return_value = mock_interface
        
        lister = NodeLister()
        
        with patch('meshcli.list_nodes.click.echo') as mock_echo:
            lister.show_known_nodes()
        
        # Should show the node information
        mock_echo.assert_any_call("  1. !22222222 (Test Node)")


def test_list_nodes_command_help():
    """Test list-nodes command help output."""
    runner = CliRunner()
    result = runner.invoke(list_nodes, ['--help'])
    
    assert result.exit_code == 0
    assert 'Show currently known nodes' in result.output
    assert '--interface' in result.output
    assert '--device' in result.output


@patch('meshcli.list_nodes.NodeLister')
def test_list_nodes_command_execution(mock_lister_class):
    """Test list-nodes command execution."""
    mock_lister = Mock()
    mock_lister_class.return_value = mock_lister
    
    runner = CliRunner()
    result = runner.invoke(list_nodes, ['--interface', 'tcp', '--device', 'test.local'])
    
    assert result.exit_code == 0
    mock_lister_class.assert_called_once_with(interface_type='tcp', device_path='test.local')
    mock_lister.show_known_nodes.assert_called_once()
