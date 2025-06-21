"""Discovery functionality for meshcli."""

import time

import click
import meshtastic
import meshtastic.serial_interface
import meshtastic.tcp_interface
from meshtastic import BROADCAST_ADDR
from meshtastic.protobuf import portnums_pb2, mesh_pb2
from pubsub import pub


class NearbyNodeDiscoverer:
    def __init__(self, interface_type="serial", device_path=None):
        self.interface = None
        self.nearby_nodes = []
        self.discovery_active = False
        self.interface_type = interface_type
        self.device_path = device_path

    def connect(self):
        """Connect to the Meshtastic device"""
        try:
            if self.interface_type == "serial":
                if self.device_path:
                    self.interface = meshtastic.serial_interface.SerialInterface(
                        devPath=self.device_path
                    )
                else:
                    self.interface = meshtastic.serial_interface.SerialInterface()
            elif self.interface_type == "tcp":
                hostname = self.device_path or "meshtastic.local"
                self.interface = meshtastic.tcp_interface.TCPInterface(
                    hostname=hostname
                )
            else:
                raise ValueError(f"Unsupported interface type: {self.interface_type}")

            self.interface.waitForConfig()
            click.echo("Connected to Meshtastic device")
            return True

        except Exception as e:
            click.echo(f"Failed to connect: {e}", err=True)
            return False

    def on_traceroute_response(self, packet, interface):
        """Handle traceroute responses during discovery"""
        if not self.discovery_active:
            return

        click.echo(packet)

        if packet.get("decoded", {}).get("portnum") == "TRACEROUTE_APP":
            sender_id = packet.get("fromId", f"!{packet.get('from', 0):08x}")
            snr = packet.get("rxSnr", "Unknown")
            rssi = packet.get("rxRssi", "Unknown")
            rnode = packet.get("relay_node")

            click.echo(f"📡 Nearby node discovered: {sender_id} {rnode}")
            if snr != "Unknown":
                click.echo(f"   Signal: SNR={snr}dB, RSSI={rssi}dBm")

            self.nearby_nodes.append(
                {
                    "id": sender_id,
                    "from_num": packet.get("from"),
                    "snr": snr,
                    "rssi": rssi,
                    "timestamp": time.time(),
                    "packet": packet,
                }
            )

    def discover_nearby_nodes(self, duration=60):
        """Send 0-hop traceroute and listen for responses"""
        if not self.connect():
            return []

        try:
            # Subscribe to traceroute responses
            pub.subscribe(self.on_traceroute_response, "meshtastic.receive.traceroute")

            self.discovery_active = True
            self.nearby_nodes = []

            click.echo("🔍 Starting interactive nearby node discovery...")
            click.echo(f"   Listening for responses for {duration} seconds...")
            click.echo("   Using 0-hop traceroute to broadcast address")

            # Create and send RouteDiscovery message
            route_discovery = mesh_pb2.RouteDiscovery()
            packet = self.interface.sendData(
                data=route_discovery,
                destinationId=BROADCAST_ADDR,
                portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                wantResponse=True,
                hopLimit=0,
            )

            click.echo(f"   Packet ID: {packet.id}")
            click.echo("\n📻 Listening for nearby node responses...")

            # Listen for responses
            start_time = time.time()
            while time.time() - start_time < duration:
                time.sleep(0.5)

            self.discovery_active = False

            # Report results
            nearby_count = len(self.nearby_nodes)
            click.echo(
                f"\n📊 Discovery complete! Found {nearby_count} " "nearby nodes:"
            )
            if self.nearby_nodes:
                for i, node in enumerate(self.nearby_nodes, 1):
                    click.echo(f"  {i}. {node['id']}")
                    if node["snr"] != "Unknown":
                        snr = node["snr"]
                        rssi = node["rssi"]
                        click.echo(f"     Signal: SNR={snr}dB, " f"RSSI={rssi}dBm")
            else:
                click.echo("  No nearby nodes detected or they didn't " "respond.")

            return self.nearby_nodes

        except KeyboardInterrupt:
            click.echo("\n⏹️  Discovery interrupted by user")
            return self.nearby_nodes
        except Exception as e:
            click.echo(f"Error during interactive discovery: {e}", err=True)
            return []
        finally:
            self.discovery_active = False
            pub.unsubscribe(
                self.on_traceroute_response, "meshtastic.receive.traceroute"
            )
            if self.interface:
                self.interface.close()


@click.command()
@click.option(
    "--duration",
    type=int,
    default=15,
    help="How long to listen for responses (seconds)",
)
@click.option(
    "--interface",
    type=click.Choice(["serial", "tcp"]),
    default="serial",
    help="Interface type to use",
)
@click.option("--device", type=str, help="Device path for serial or hostname for TCP")
def discover(duration, interface, device):
    """Discover nearby Meshtastic nodes using 0-hop traceroute."""
    discoverer = NearbyNodeDiscoverer(interface_type=interface, device_path=device)

    click.echo("🌐 Meshtastic Nearby Node Discoverer")
    click.echo("=" * 40)
    click.echo("Using 0-hop traceroute to broadcast address")
    click.echo()

    click.echo(f"Listening for responses for {duration} seconds...")
    nearby_nodes = discoverer.discover_nearby_nodes(duration=duration)
    if nearby_nodes:
        click.echo("✅ Discovery completed successfully")
    else:
        click.echo("ℹ️  No nearby nodes found")
