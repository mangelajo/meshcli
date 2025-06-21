"""Tests for the discover module."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from meshcli.discover import NearbyNodeDiscoverer, discover


class TestNearbyNodeDiscoverer:
    """Test the NearbyNodeDiscoverer class."""

    def test_init(self):
        """Test NearbyNodeDiscoverer initialization."""
        discoverer = NearbyNodeDiscoverer()
        assert discoverer.interface is None
        assert discoverer.nearby_nodes == []
        assert discoverer.discovery_active is False
        assert discoverer.interface_type == 'serial'
        assert discoverer.device_path is None

    def test_init_with_params(self):
        """Test NearbyNodeDiscoverer initialization with parameters."""
        discoverer = NearbyNodeDiscoverer(
            interface_type='tcp',
            device_path='test.local'
        )
        assert discoverer.interface_type == 'tcp'
        assert discoverer.device_path == 'test.local'

    @patch('meshcli.discover.meshtastic.serial_interface.SerialInterface')
    def test_connect_serial_success(self, mock_serial):
        """Test successful serial connection."""
        mock_interface = Mock()
        mock_serial.return_value = mock_interface

        discoverer = NearbyNodeDiscoverer()
        result = discoverer.connect()

        assert result is True
        mock_serial.assert_called_once()
        mock_interface.waitForConfig.assert_called_once()

    @patch('meshcli.discover.meshtastic.serial_interface.SerialInterface')
    def test_connect_serial_failure(self, mock_serial):
        """Test failed serial connection."""
        mock_serial.side_effect = Exception("Connection failed")

        discoverer = NearbyNodeDiscoverer()
        result = discoverer.connect()

        assert result is False

    @patch('meshcli.discover.meshtastic.tcp_interface.TCPInterface')
    def test_connect_tcp_success(self, mock_tcp):
        """Test successful TCP connection."""
        mock_interface = Mock()
        mock_tcp.return_value = mock_interface

        discoverer = NearbyNodeDiscoverer(
            interface_type='tcp',
            device_path='test.local'
        )
        result = discoverer.connect()

        assert result is True
        mock_tcp.assert_called_once_with(hostname='test.local')
        mock_interface.waitForConfig.assert_called_once()

    def test_connect_invalid_interface(self):
        """Test connection with invalid interface type."""
        discoverer = NearbyNodeDiscoverer(interface_type='invalid')
        result = discoverer.connect()

        assert result is False

    def test_on_traceroute_response_inactive(self):
        """Test traceroute response handler when discovery is inactive."""
        discoverer = NearbyNodeDiscoverer()
        discoverer.discovery_active = False

        packet = {'decoded': {'portnum': 'TRACEROUTE_APP'}}
        discoverer.on_traceroute_response(packet, None)

        assert len(discoverer.nearby_nodes) == 0

    def test_on_traceroute_response_active(self):
        """Test traceroute response handler when discovery is active."""
        discoverer = NearbyNodeDiscoverer()
        discoverer.discovery_active = True

        packet = {
            'decoded': {'portnum': 'TRACEROUTE_APP'},
            'fromId': '!12345678',
            'from': 0x12345678,
            'rxSnr': 10.5,
            'rxRssi': -50,
            'relay_node': None
        }

        with patch('meshcli.discover.click.echo'):
            discoverer.on_traceroute_response(packet, None)

        assert len(discoverer.nearby_nodes) == 1
        assert discoverer.nearby_nodes[0]['id'] == '!12345678'
        assert discoverer.nearby_nodes[0]['snr'] == 10.5


def test_discover_command_help():
    """Test discover command help output."""
    runner = CliRunner()
    result = runner.invoke(discover, ['--help'])
    
    assert result.exit_code == 0
    assert 'Discover nearby Meshtastic nodes' in result.output
    assert '--duration' in result.output
    assert '--interface' in result.output
    assert '--device' in result.output


@patch('meshcli.discover.NearbyNodeDiscoverer')
def test_discover_command_execution(mock_discoverer_class):
    """Test discover command execution."""
    mock_discoverer = Mock()
    mock_discoverer.discover_nearby_nodes.return_value = []
    mock_discoverer_class.return_value = mock_discoverer

    runner = CliRunner()
    result = runner.invoke(discover, ['--duration', '5'])

    assert result.exit_code == 0
    mock_discoverer_class.assert_called_once_with(
        interface_type='serial',
        device_path=None
    )
    mock_discoverer.discover_nearby_nodes.assert_called_once_with(duration=5)
