"""Main CLI module for meshcli."""

import click
import meshtastic
import meshtastic.serial_interface
import meshtastic.tcp_interface
from meshtastic import BROADCAST_ADDR
from meshtastic.protobuf import portnums_pb2, mesh_pb2
from pubsub import pub
import time
import sys
import datetime


class NearbyNodeDiscoverer:
    def __init__(self, interface_type='serial', device_path=None):
        self.interface = None
        self.nearby_nodes = []
        self.discovery_active = False
        self.interface_type = interface_type
        self.device_path = device_path
        
    def connect(self):
        """Connect to the Meshtastic device"""
        try:
            if self.interface_type == 'serial':
                if self.device_path:
                    self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.device_path)
                else:
                    self.interface = meshtastic.serial_interface.SerialInterface()
            elif self.interface_type == 'tcp':
                self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.device_path or 'meshtastic.local')
            else:
                raise ValueError(f"Unsupported interface type: {self.interface_type}")
                
            self.interface.waitForConfig()
            click.echo(f"Connected to Meshtastic device")
            return True
            
        except Exception as e:
            click.echo(f"Failed to connect: {e}", err=True)
            return False
    
    def on_traceroute_response(self, packet, interface):
        """Handle traceroute responses during discovery"""
        if not self.discovery_active:
            return
        
        click.echo(packet)
            
        if packet.get('decoded', {}).get('portnum') == 'TRACEROUTE_APP':
            sender_id = packet.get('fromId', f"!{packet.get('from', 0):08x}")
            snr = packet.get('rxSnr', 'Unknown')
            rssi = packet.get('rxRssi', 'Unknown')
            rnode = packet.get('relay_node')
            
            click.echo(f"📡 Nearby node discovered: {sender_id} {rnode}")
            if snr != 'Unknown':
                click.echo(f"   Signal: SNR={snr}dB, RSSI={rssi}dBm")
            
            self.nearby_nodes.append({
                'id': sender_id,
                'from_num': packet.get('from'),
                'snr': snr,
                'rssi': rssi,
                'timestamp': time.time(),
                'packet': packet
            })
    
    def simple_discovery(self):
        """Send a simple 0-hop traceroute to discover nearby nodes"""
        if not self.connect():
            return False
            
        try:
            click.echo("🔍 Sending 0-hop traceroute to broadcast address...")
            click.echo("   Using TRACEROUTE_APP protocol")
            
            # Create RouteDiscovery message
            route_discovery = mesh_pb2.RouteDiscovery()
            
            packet = self.interface.sendData(
                data=route_discovery,
                destinationId=BROADCAST_ADDR,
                portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                wantResponse=True,
                hopLimit=0  # Only nearby nodes
            )
            
            click.echo(f"   Packet ID: {packet.id}")
            click.echo("   Nearby nodes should respond automatically")
            return True
            
        except Exception as e:
            click.echo(f"Failed to send discovery: {e}", err=True)
            return False
        finally:
            self.interface.close()
    
    def builtin_discovery(self, timeout=10):
        """Use the built-in pingNearbyNodes method"""
        if not self.connect():
            return []
            
        try:
            click.echo(f"🔍 Using built-in nearby node discovery...")
            click.echo(f"   Timeout: {timeout} seconds")
            
            # Use the new built-in method
            nearby_nodes = self.interface.pingNearbyNodes(timeout=timeout)
            
            return nearby_nodes
            
        except Exception as e:
            click.echo(f"Error during built-in discovery: {e}", err=True)
            return []
        finally:
            self.interface.close()
    
    def interactive_discovery(self, duration=60):
        """Send 0-hop traceroute and listen for responses"""
        if not self.connect():
            return []
            
        try:
            # Subscribe to traceroute responses
            pub.subscribe(self.on_traceroute_response, "meshtastic.receive.traceroute")
            
            self.discovery_active = True
            self.nearby_nodes = []
            
            click.echo(f"🔍 Starting interactive nearby node discovery...")
            click.echo(f"   Listening for responses for {duration} seconds...")
            click.echo("   Using 0-hop traceroute to broadcast address")
            
            # Create and send RouteDiscovery message
            route_discovery = mesh_pb2.RouteDiscovery()
            packet = self.interface.sendData(
                data=route_discovery,
                destinationId=BROADCAST_ADDR,
                portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                wantResponse=True,
                hopLimit=0
            )
            
            click.echo(f"   Packet ID: {packet.id}")
            click.echo("\n📻 Listening for nearby node responses...")
            
            # Listen for responses
            start_time = time.time()
            while time.time() - start_time < duration:
                time.sleep(0.5)
                
            self.discovery_active = False
            
            # Report results
            click.echo(f"\n📊 Discovery complete! Found {len(self.nearby_nodes)} nearby nodes:")
            if self.nearby_nodes:
                for i, node in enumerate(self.nearby_nodes, 1):
                    click.echo(f"  {i}. {node['id']}")
                    if node['snr'] != 'Unknown':
                        click.echo(f"     Signal: SNR={node['snr']}dB, RSSI={node['rssi']}dBm")
            else:
                click.echo("  No nearby nodes detected or they didn't respond.")
                
            return self.nearby_nodes
                
        except KeyboardInterrupt:
            click.echo("\n⏹️  Discovery interrupted by user")
            return self.nearby_nodes
        except Exception as e:
            click.echo(f"Error during interactive discovery: {e}", err=True)
            return []
        finally:
            self.discovery_active = False
            pub.unsubscribe(self.on_traceroute_response, "meshtastic.receive.traceroute")
            if self.interface:
                self.interface.close()
    
    def show_known_nodes(self):
        """Show currently known nodes from the node database"""
        if not self.connect():
            return
            
        try:
            click.echo("📋 Currently known nodes in database:")
            
            if self.interface.nodesByNum:
                known_nodes = []
                for node_num, node in self.interface.nodesByNum.items():
                    if node_num == self.interface.localNode.nodeNum:
                        continue  # Skip ourselves
                        
                    user = node.get('user', {})
                    node_id = user.get('id', f"!{node_num:08x}")
                    long_name = user.get('longName', 'Unknown')
                    snr = node.get('snr')
                    last_heard = node.get('lastHeard')
                    
                    known_nodes.append({
                        'id': node_id,
                        'name': long_name,
                        'snr': snr,
                        'last_heard': last_heard,
                        'num': node_num
                    })
                
                if known_nodes:
                    # Sort by last heard (most recent first)
                    known_nodes.sort(key=lambda x: x['last_heard'] or 0, reverse=True)
                    
                    for i, node in enumerate(known_nodes, 1):
                        last_heard_str = "Unknown"
                        if node['last_heard']:
                            dt = datetime.datetime.fromtimestamp(node['last_heard'])
                            last_heard_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        
                        snr_str = f"SNR: {node['snr']}dB" if node['snr'] else "SNR: Unknown"
                        click.echo(f"  {i}. {node['id']} ({node['name']})")
                        click.echo(f"     {snr_str}, Last heard: {last_heard_str}")
                else:
                    click.echo("  No other nodes in database")
            else:
                click.echo("  Node database is empty")
                
        except Exception as e:
            click.echo(f"Error showing known nodes: {e}", err=True)
        finally:
            self.interface.close()


@click.group()
@click.version_option()
def main():
    """A CLI tool for mesh operations."""
    pass


@main.command()
@click.option("--name", default="World", help="Name to greet.")
def hello(name):
    """Simple program that greets NAME."""
    click.echo(f"Hello {name}!")


@main.command()
@click.option("--mode", type=click.Choice(['simple', 'builtin', 'interactive']), 
              default='builtin', help='Discovery mode')
@click.option("--duration", type=int, default=15, 
              help='How long to listen for responses in interactive mode (seconds)')
@click.option("--timeout", type=int, default=10,
              help='Timeout for built-in discovery method (seconds)')
@click.option("--interface", type=click.Choice(['serial', 'tcp']), default='serial',
              help='Interface type to use')
@click.option("--device", type=str, help='Device path for serial or hostname for TCP')
def discover(mode, duration, timeout, interface, device):
    """Discover nearby Meshtastic nodes using 0-hop traceroute."""
    discoverer = NearbyNodeDiscoverer(interface_type=interface, device_path=device)
    
    click.echo("🌐 Meshtastic Nearby Node Discoverer")
    click.echo("=" * 40)
    click.echo("Using 0-hop traceroute to broadcast address")
    click.echo()
    
    if mode == 'simple':
        click.echo("Mode: Simple discovery (send only)")
        success = discoverer.simple_discovery()
        if success:
            click.echo("✅ Discovery packet sent successfully")
        else:
            click.echo("❌ Failed to send discovery packet")
            sys.exit(1)
            
    elif mode == 'builtin':
        click.echo(f"Mode: Built-in discovery (timeout: {timeout}s)")
        nearby_nodes = discoverer.builtin_discovery(timeout=timeout)
        if nearby_nodes:
            click.echo("✅ Discovery completed successfully")
        else:
            click.echo("ℹ️  No nearby nodes found")
            
    elif mode == 'interactive':
        click.echo(f"Mode: Interactive discovery (listen for {duration}s)")
        nearby_nodes = discoverer.interactive_discovery(duration=duration)
        if nearby_nodes:
            click.echo("✅ Discovery completed successfully")
        else:
            click.echo("ℹ️  No nearby nodes found")


@main.command("list-nodes")
@click.option("--interface", type=click.Choice(['serial', 'tcp']), default='serial',
              help='Interface type to use')
@click.option("--device", type=str, help='Device path for serial or hostname for TCP')
def list_nodes(interface, device):
    """Show currently known nodes from the node database."""
    discoverer = NearbyNodeDiscoverer(interface_type=interface, device_path=device)
    discoverer.show_known_nodes()


if __name__ == "__main__":
    main()
