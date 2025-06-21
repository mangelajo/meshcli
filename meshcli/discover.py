"""Discovery functionality for meshcli."""

import time

import click
import meshtastic
import meshtastic.serial_interface
import meshtastic.tcp_interface
from meshtastic import BROADCAST_ADDR
from meshtastic.protobuf import portnums_pb2, mesh_pb2
from pubsub import pub
from rich.console import Console
from rich.pretty import pprint
from rich.table import Table

from .list_nodes import NodeLister


class NearbyNodeDiscoverer:
    def __init__(self, interface_type="serial", device_path=None, debug=False):
        self.interface = None
        self.nearby_nodes = []
        self.discovery_active = False
        self.interface_type = interface_type
        self.device_path = device_path
        self.debug = debug
        self.console = Console()

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

        # Pretty print the packet details only in debug mode
        if self.debug:
            self.console.print("\n┌─ [bold blue]📦 Received packet[/bold blue] " + "─" * 50 + "┐")
            pprint(packet, console=self.console)
            self.console.print("└" + "─" * 65 + "┘")

        if packet.get("decoded", {}).get("portnum") == "TRACEROUTE_APP":
            sender_id = packet.get("fromId", f"!{packet.get('from', 0):08x}")
            snr = packet.get("rxSnr", "Unknown")
            rssi = packet.get("rxRssi", "Unknown")
            rnode = packet.get("relay_node")

            # Extract snrTowards values from traceroute data
            snr_towards = None
            traceroute = packet.get("decoded", {}).get("traceroute", {})
            if traceroute and "snrTowards" in traceroute:
                snr_towards_raw = traceroute["snrTowards"]
                if snr_towards_raw and len(snr_towards_raw) > 1:
                    # Convert raw values to dB by dividing by 4.0, skip first 0.0
                    snr_towards = snr_towards_raw[-1] / 4.0

            # Format display name with known node info
            display_name = self.format_node_display(sender_id, getattr(self, 'known_nodes', {}))
            
            click.echo(f"📡 Nearby node discovered: {display_name} {rnode}")
            if snr != "Unknown":
                if snr_towards is not None:
                    click.echo(f"   Signal: SNR={snr}dB, RSSI={rssi}dBm, SNR_towards={snr_towards}dB")
                else:
                    click.echo(f"   Signal: SNR={snr}dB, RSSI={rssi}dBm")

            self.nearby_nodes.append(
                {
                    "id": sender_id,
                    "from_num": packet.get("from"),
                    "snr": snr,
                    "rssi": rssi,
                    "snr_towards": snr_towards,
                    "timestamp": time.time(),
                    "packet": packet,
                }
            )

    def get_known_nodes(self):
        """Get known nodes from the node database"""
        known_nodes = {}
        if self.interface and self.interface.nodesByNum:
            for node_num, node in self.interface.nodesByNum.items():
                if node_num == self.interface.localNode.nodeNum:
                    continue  # Skip ourselves
                
                user = node.get("user", {})
                node_id = user.get("id", f"!{node_num:08x}")
                long_name = user.get("longName", "")
                short_name = user.get("shortName", "")
                
                known_nodes[node_id] = {
                    "long_name": long_name,
                    "short_name": short_name,
                    "node_num": node_num
                }
        return known_nodes

    def format_node_display(self, node_id, known_nodes):
        """Format node display with [Short] LongName if known, otherwise just ID"""
        if node_id in known_nodes:
            node_info = known_nodes[node_id]
            short = node_info["short_name"]
            long_name = node_info["long_name"]
            
            if short and long_name:
                return f"[{short}] {long_name}"
            elif long_name:
                return long_name
            elif short:
                return f"[{short}]"
        
        return node_id

    def discover_nearby_nodes(self, duration=60):
        """Send 0-hop traceroute and listen for responses"""
        if not self.connect():
            return []

        try:
            # Get known nodes first
            known_nodes = self.get_known_nodes()
            
            # Store known_nodes for use in on_traceroute_response
            self.known_nodes = known_nodes

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
                # Create a table for the results
                table = Table(title="Discovered Nearby Nodes")
                table.add_column("#", style="cyan", no_wrap=True)
                table.add_column("Node ID", style="magenta")
                table.add_column("Short Name", style="bright_magenta")
                table.add_column("Long Name", style="bright_cyan")
                table.add_column("SNR (dB)", style="green")
                table.add_column("RSSI (dBm)", style="yellow")
                table.add_column("SNR Towards (dB)", style="blue")

                for i, node in enumerate(self.nearby_nodes, 1):
                    node_id = node['id']
                    
                    # Get node info from known nodes
                    short_name = ""
                    long_name = ""
                    if node_id in known_nodes:
                        node_info = known_nodes[node_id]
                        short_name = node_info["short_name"]
                        long_name = node_info["long_name"]
                    
                    snr = str(node["snr"]) if node["snr"] != "Unknown" else "Unknown"
                    rssi = str(node["rssi"]) if node["rssi"] != "Unknown" else "Unknown"
                    snr_towards = str(node.get("snr_towards", "")) if node.get("snr_towards") is not None else ""
                    
                    table.add_row(
                        str(i),
                        node_id,
                        short_name,
                        long_name,
                        snr,
                        rssi,
                        snr_towards
                    )

                self.console.print(table)
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
@click.option("--debug", is_flag=True, help="Enable debug mode to show packet details")
def discover(duration, interface, device, debug):
    """Discover nearby Meshtastic nodes using 0-hop traceroute."""
    discoverer = NearbyNodeDiscoverer(interface_type=interface, device_path=device, debug=debug)

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
