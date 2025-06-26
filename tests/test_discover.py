"""Tests for the discover module."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from meshctl.discover import NearbyNodeDiscoverer, discover


class TestNearbyNodeDiscoverer:
    """Test the NearbyNodeDiscoverer class."""

    def test_init(self):
        """Test NearbyNodeDiscoverer initialization."""
        discoverer = NearbyNodeDiscoverer()
        assert discoverer.interface is None
        assert discoverer.interface_type == "auto"
        assert discoverer.device_path is None
        assert discoverer.debug is False

    def test_init_with_params(self):
        """Test NearbyNodeDiscoverer initialization with parameters."""
        discoverer = NearbyNodeDiscoverer(
            interface_type="tcp", device_path="test.local", debug=True
        )
        assert discoverer.interface_type == "tcp"
        assert discoverer.device_path == "test.local"
        assert discoverer.debug is True

    @patch("meshctl.traceroute.TracerouteBase.connect")
    def test_connect_success(self, mock_connect):
        """Test successful connection."""
        mock_connect.return_value = True

        discoverer = NearbyNodeDiscoverer()
        result = discoverer.connect()

        assert result is True
        mock_connect.assert_called_once()

    @patch("meshctl.connection.connect")
    def test_connect_failure(self, mock_connect):
        """Test failed connection."""
        mock_connect.return_value = None

        discoverer = NearbyNodeDiscoverer()
        result = discoverer.connect()

        assert result is False
        assert discoverer.interface is None

    @patch("meshctl.traceroute.TracerouteBase.connect")
    def test_connect_with_params(self, mock_connect):
        """Test connection with specific parameters."""
        mock_connect.return_value = True

        discoverer = NearbyNodeDiscoverer(
            interface_type="tcp", device_path="test.local"
        )
        result = discoverer.connect()

        assert result is True
        mock_connect.assert_called_once()

    def test_on_traceroute_response(self):
        """Test traceroute response handler."""
        discoverer = NearbyNodeDiscoverer()

        packet = {
            "decoded": {"portnum": "TRACEROUTE_APP"},
            "fromId": "!12345678",
            "from": 0x12345678,
            "rxSnr": 10.5,
            "rxRssi": -50,
        }

        with patch("meshctl.discover.click.echo"):
            discoverer.on_traceroute_response(packet, None)


def test_discover_command_help():
    """Test discover command help output."""
    runner = CliRunner()
    result = runner.invoke(discover, ["--help"])

    assert result.exit_code == 0
    assert "Discover nearby Meshtastic nodes" in result.output
    assert "--duration" in result.output
    assert "--interface-type" in result.output
    assert "--address" in result.output


@patch("meshctl.discover.NearbyNodeDiscoverer")
def test_discover_command_execution(mock_discoverer_class):
    """Test discover command execution."""
    mock_discoverer = Mock()
    mock_discoverer.discover_nearby_nodes.return_value = []
    mock_discoverer_class.return_value = mock_discoverer

    runner = CliRunner()
    result = runner.invoke(discover, ["--duration", "1"])

    assert result.exit_code == 0
    mock_discoverer_class.assert_called_once_with(
        interface_type="auto",
        device_path=None,
        debug=False,
        test_run_id=None,
        csv_file=None,
    )
    mock_discoverer.discover_nearby_nodes.assert_called_once_with(
        duration=1, current_run=1, total_runs=1
    )
