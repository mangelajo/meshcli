"""Discovery functionality for meshcli."""

import csv
import os
import time

import click
from meshtastic import BROADCAST_ADDR
from meshtastic.protobuf import portnums_pb2, mesh_pb2
from pubsub import pub
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from .connection import address_options, connect


class NearbyNodeDiscoverer:
    def __init__(
        self,
        interface_type="auto",
        device_path=None,
        debug=False,
        test_run_id=None,
        csv_file=None,
    ):
        self.interface_type = interface_type
        self.device_path = device_path
        self.interface = None
        self.debug = debug
        self.nearby_nodes = []
        self.discovery_active = False
        self.console = Console()
        self.test_run_id = test_run_id
        self.csv_file = csv_file

    def connect(self):
        """Connect to the Meshtastic device using the unified connect function."""
        self.interface = connect(
            address=self.device_path, interface_type=self.interface_type
        )
        if self.interface is None:
            click.echo("Failed to connect", err=True)
            return False
        try:
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
            packet_details = self.format_packet_details(packet)
            content = "\n".join(packet_details)

            panel = Panel(
                content,
                title="[bold blue]📦 Received Traceroute Packet[/bold blue]",
                border_style="blue",
                padding=(0, 1),
            )
            self.console.print(panel)

        if packet.get("decoded", {}).get("portnum") == "TRACEROUTE_APP":
            sender_id = packet.get("fromId", f"!{packet.get('from', 0):08x}")
            snr = packet.get("rxSnr", "Unknown")
            rssi = packet.get("rxRssi", "Unknown")
            rnode = packet.get("relay_node")

            # Check if this is a forwarded packet (SNR back entries > 1)
            traceroute = packet.get("decoded", {}).get("traceroute", {})
            snr_back = traceroute.get("snrBack", []) if traceroute else []
            is_forwarded_packet = len(snr_back) > 1

            # Extract snrTowards values from traceroute data
            snr_towards = None
            if traceroute and "snrTowards" in traceroute:
                snr_towards_raw = traceroute["snrTowards"]
                if snr_towards_raw and len(snr_towards_raw) > 1:
                    # Convert raw values to dB by dividing by 4.0, skip first 0.0
                    snr_towards = snr_towards_raw[-1] / 4.0

            # Skip SNR consideration if this is a forwarded packet
            if is_forwarded_packet:
                snr = "Forwarded"
                rssi = "Forwarded"

            # Format display name with known node info
            display_name = self.format_node_display(
                sender_id, getattr(self, "known_nodes", {})
            )

            # Format relay node display
            relay_display = ""
            if rnode is not None:
                relay_hex = f"______{rnode:02x}"
                relay_display = f" via relay 0x{relay_hex}"

                # Find candidate nodes
                candidates = self.find_relay_candidates(rnode)
                if candidates:
                    candidate_names = [cand["name"] for cand in candidates]
                    relay_display += f" (candidates: {', '.join(candidate_names)})"

            # Create content for the panel
            content = f"[bold cyan]Node:[/bold cyan] {display_name}{relay_display}\n"

            if snr != "Unknown":
                if snr_towards is not None:
                    content += f"[bold green]Signal:[/bold green] SNR={snr}dB, RSSI={rssi}dBm, SNR_towards={snr_towards}dB"
                else:
                    content += (
                        f"[bold green]Signal:[/bold green] SNR={snr}dB, RSSI={rssi}dBm"
                    )

            # Create a beautiful panel for the discovery output
            panel = Panel(
                content,
                title="[bold green]📡 Nearby Node Discovered[/bold green]",
                border_style="green",
                padding=(0, 1),
            )
            self.console.print(panel)

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
                    "node_num": node_num,
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

    def format_packet_details(self, packet):
        """Format packet details in a nice, readable way"""
        details = []

        # Get known nodes for name lookup
        known_nodes = getattr(self, "known_nodes", {})

        # Basic packet info
        details.append(
            f"[bold cyan]Packet ID:[/bold cyan] {packet.get('id', 'Unknown')}"
        )

        # Format From field with name if known
        from_id = packet.get("fromId", "Unknown")
        from_num = packet.get("from", "Unknown")
        from_display = f"{from_id}"
        if from_id != "Unknown" and from_id in known_nodes:
            from_name = self.format_node_display(from_id, known_nodes)
            from_display = f"{from_id} ({from_name})"
        elif from_num != "Unknown":
            from_display = f"{from_id} (num: {from_num})"
        details.append(f"[bold cyan]From:[/bold cyan] {from_display}")

        # Format To field with name if known
        to_id = packet.get("toId", "Unknown")
        to_num = packet.get("to", "Unknown")
        to_display = f"{to_id}"
        if to_id != "Unknown" and to_id in known_nodes:
            to_name = self.format_node_display(to_id, known_nodes)
            to_display = f"{to_id} ({to_name})"
        elif to_num != "Unknown":
            to_display = f"{to_id} (num: {to_num})"
        details.append(f"[bold cyan]To:[/bold cyan] {to_display}")

        # Signal info
        rx_snr = packet.get("rxSnr", "Unknown")
        rx_rssi = packet.get("rxRssi", "Unknown")
        details.append(
            f"[bold green]Signal:[/bold green] SNR={rx_snr}dB, RSSI={rx_rssi}dBm"
        )

        # Hop info with enhanced relay node display
        hop_limit = packet.get("hopLimit", "Unknown")
        hop_start = packet.get("hopStart", "Unknown")
        relay_node = packet.get("relayNode", "Unknown")

        relay_display = relay_node
        if relay_node != "Unknown" and isinstance(relay_node, int):
            relay_hex = f"______{relay_node:02x}"
            relay_display = f"0x{relay_hex}"

            # Find candidate nodes based on last hex digits
            candidates = self.find_relay_candidates(relay_node)
            if candidates:
                candidate_names = [
                    self.format_node_display(
                        cand["id"], getattr(self, "known_nodes", {})
                    )
                    for cand in candidates
                ]
                relay_display += f" - Candidates: {', '.join(candidate_names)}"

        details.append(
            f"[bold yellow]Hops:[/bold yellow] Limit={hop_limit}, Start={hop_start}, Relay={relay_display}"
        )

        # Decoded info
        decoded = packet.get("decoded", {})
        if decoded:
            portnum = decoded.get("portnum", "Unknown")
            request_id = decoded.get("requestId", "Unknown")
            bitfield = decoded.get("bitfield", "Unknown")
            details.append(
                f"[bold magenta]Decoded:[/bold magenta] Port={portnum}, RequestID={request_id}, Bitfield={bitfield}"
            )

            # Traceroute specific info
            traceroute = decoded.get("traceroute", {})
            if traceroute:
                details.append("[bold blue]Traceroute Data:[/bold blue]")

                # Route information
                route = traceroute.get("route", [])
                if route:
                    route_parts = []
                    for node in route:
                        node_id = f"!{node:08x}"
                        if node_id in known_nodes:
                            node_name = self.format_node_display(node_id, known_nodes)
                            route_parts.append(f"{node_id} ({node_name})")
                        else:
                            route_parts.append(node_id)
                    route_str = " → ".join(route_parts)
                    details.append(f"  [blue]Route:[/blue] {route_str}")

                # SNR towards information
                snr_towards = traceroute.get("snrTowards", [])
                route = traceroute.get("route", [])
                if snr_towards:
                    snr_towards_parts = []
                    for i, snr in enumerate(snr_towards):
                        snr_db = f"{snr/4.0:.1f}dB"
                        # Try to match with route nodes if available
                        if i < len(route):
                            node_id = f"!{route[i]:08x}"
                            if node_id in known_nodes:
                                node_name = self.format_node_display(
                                    node_id, known_nodes
                                )
                                snr_towards_parts.append(f"{snr_db} ({node_name})")
                            else:
                                snr_towards_parts.append(f"{snr_db} ({node_id})")
                        else:
                            snr_towards_parts.append(snr_db)
                    details.append(
                        f"  [blue]SNR Towards:[/blue] {' → '.join(snr_towards_parts)}"
                    )

                # SNR back information
                snr_back = traceroute.get("snrBack", [])
                if snr_back:
                    snr_back_parts = []
                    for i, snr in enumerate(snr_back):
                        snr_db = f"{snr/4.0:.1f}dB"
                        # Try to match with route nodes if available (reverse order for back)
                        if i < len(route):
                            route_idx = len(route) - 1 - i
                            if route_idx >= 0:
                                node_id = f"!{route[route_idx]:08x}"
                                if node_id in known_nodes:
                                    node_name = self.format_node_display(
                                        node_id, known_nodes
                                    )
                                    snr_back_parts.append(f"{snr_db} ({node_name})")
                                else:
                                    snr_back_parts.append(f"{snr_db} ({node_id})")
                            else:
                                snr_back_parts.append(snr_db)
                        else:
                            snr_back_parts.append(snr_db)
                    details.append(
                        f"  [blue]SNR Back:[/blue] {' → '.join(snr_back_parts)}"
                    )

        # Timing info
        rx_time = packet.get("rxTime", "Unknown")
        if rx_time != "Unknown":
            import datetime

            try:
                dt = datetime.datetime.fromtimestamp(rx_time)
                details.append(
                    f"[bold white]Received:[/bold white] {dt.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except (ValueError, OSError, OverflowError):
                details.append(f"[bold white]RX Time:[/bold white] {rx_time}")

        return details

    def find_relay_candidates(self, relay_node_last_byte):
        """Find known nodes at 0 hops that could match the relay node based on last hex digits"""
        candidates = []
        known_nodes = getattr(self, "known_nodes", {})

        # Only consider nodes that are at 0 hops (directly reachable)
        if self.interface and self.interface.nodesByNum:
            for node_num, node in self.interface.nodesByNum.items():
                # Skip ourselves
                if node_num == self.interface.localNode.nodeNum:
                    continue

                # Only consider nodes at 0 hops
                if node.get("hopsAway", float("inf")) == 0:
                    # Check if the last byte matches
                    if (node_num & 0xFF) == relay_node_last_byte:
                        user = node.get("user", {})
                        node_id = user.get("id", f"!{node_num:08x}")

                        candidates.append(
                            {
                                "id": node_id,
                                "node_num": node_num,
                                "name": self.format_node_display(node_id, known_nodes),
                            }
                        )

        return candidates

    def append_to_csv(self, nodes, known_nodes):
        """Append discovery results to CSV file"""
        import datetime

        # Check if file exists to determine if we need headers
        file_exists = os.path.exists(self.csv_file)

        try:
            with open(self.csv_file, "a", newline="", encoding="utf-8") as csvfile:
                # Define fieldnames based on whether test_run_id is used
                if self.test_run_id:
                    fieldnames = [
                        "Timestamp",
                        "Test Run ID",
                        "Node ID",
                        "Short Name",
                        "Long Name",
                        "SNR (dB)",
                        "RSSI (dBm)",
                        "SNR Towards (dB)",
                    ]
                else:
                    fieldnames = [
                        "Timestamp",
                        "Node ID",
                        "Short Name",
                        "Long Name",
                        "SNR (dB)",
                        "RSSI (dBm)",
                        "SNR Towards (dB)",
                    ]

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                # Write header if file is new
                if not file_exists:
                    writer.writeheader()

                # Write data rows
                for i, node in enumerate(nodes, 1):
                    node_id = node["id"]

                    # Get node info from known nodes
                    short_name = ""
                    long_name = ""
                    if node_id in known_nodes:
                        node_info = known_nodes[node_id]
                        short_name = node_info["short_name"]
                        long_name = node_info["long_name"]

                    snr = str(node["snr"]) if node["snr"] != "Unknown" else "Unknown"
                    rssi = str(node["rssi"]) if node["rssi"] != "Unknown" else "Unknown"
                    snr_towards = (
                        str(node.get("snr_towards", ""))
                        if node.get("snr_towards") is not None
                        else ""
                    )

                    # Format timestamp
                    timestamp = datetime.datetime.fromtimestamp(
                        node["timestamp"]
                    ).strftime("%Y-%m-%d %H:%M:%S")

                    # Create row data
                    if self.test_run_id:
                        row = {
                            "Timestamp": timestamp,
                            "Test Run ID": self.test_run_id,
                            "Node ID": node_id,
                            "Short Name": short_name,
                            "Long Name": long_name,
                            "SNR (dB)": snr,
                            "RSSI (dBm)": rssi,
                            "SNR Towards (dB)": snr_towards,
                        }
                    else:
                        row = {
                            "Timestamp": timestamp,
                            "Node ID": node_id,
                            "Short Name": short_name,
                            "Long Name": long_name,
                            "SNR (dB)": snr,
                            "RSSI (dBm)": rssi,
                            "SNR Towards (dB)": snr_towards,
                        }

                    writer.writerow(row)

            click.echo(f"📄 Results appended to {self.csv_file}")

        except Exception as e:
            click.echo(f"❌ Error writing to CSV file: {e}", err=True)

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

            # Listen for responses with progress bar
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=self.console,
                transient=True,
            ) as progress:
                task = progress.add_task("Discovering nodes...", total=duration)

                start_time = time.time()
                while time.time() - start_time < duration:
                    elapsed = time.time() - start_time
                    progress.update(task, completed=elapsed)
                    time.sleep(0.1)  # More frequent updates for smoother progress bar

            self.discovery_active = False

            # Report results
            nearby_count = len(self.nearby_nodes)
            if self.nearby_nodes:
                # Create a table for the results
                table = Table(
                    title=f"\n📊 Discovery complete! Found {nearby_count} "
                    "nearby nodes:"
                )
                table.add_column("Timestamp", style="white", no_wrap=True)
                if self.test_run_id:
                    table.add_column("Test Run ID", style="dim", no_wrap=True)
                table.add_column("Node ID", style="magenta")
                table.add_column("Short Name", style="bright_magenta")
                table.add_column("Long Name", style="bright_cyan")
                table.add_column("SNR (dB)", style="green")
                table.add_column("RSSI (dBm)", style="yellow")
                table.add_column("SNR Towards (dB)", style="bright_blue")

                for i, node in enumerate(self.nearby_nodes, 1):
                    node_id = node["id"]

                    # Get node info from known nodes
                    short_name = ""
                    long_name = ""
                    if node_id in known_nodes:
                        node_info = known_nodes[node_id]
                        short_name = node_info["short_name"]
                        long_name = node_info["long_name"]

                    snr = str(node["snr"]) if node["snr"] != "Unknown" else "Unknown"
                    rssi = str(node["rssi"]) if node["rssi"] != "Unknown" else "Unknown"
                    snr_towards = (
                        str(node.get("snr_towards", ""))
                        if node.get("snr_towards") is not None
                        else ""
                    )

                    # Format timestamp
                    import datetime

                    timestamp = datetime.datetime.fromtimestamp(
                        node["timestamp"]
                    ).strftime("%H:%M:%S")

                    if self.test_run_id:
                        table.add_row(
                            timestamp,
                            self.test_run_id,
                            node_id,
                            short_name,
                            long_name,
                            snr,
                            rssi,
                            snr_towards,
                        )
                    else:
                        table.add_row(
                            timestamp,
                            node_id,
                            short_name,
                            long_name,
                            snr,
                            rssi,
                            snr_towards,
                        )

                self.console.print(table)

                # Append to CSV if requested
                if self.csv_file:
                    self.append_to_csv(self.nearby_nodes, known_nodes)
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
@address_options
@click.option(
    "--duration",
    type=int,
    default=45,
    help="How long to listen for responses (seconds)",
)
@click.option("--debug", is_flag=True, help="Enable debug mode to show packet details")
@click.option("--id", help="Test run ID to include in results table")
@click.option(
    "--append-to-csv",
    help="Append results to CSV file (creates file with headers if it doesn't exist)",
)
@click.option(
    "--repeat", type=int, default=1, help="Number of times to repeat the discovery"
)
@click.option(
    "--repeat-time",
    type=int,
    default=300,
    help="Time interval between repeats in seconds (includes test runtime)",
)
def discover(
    address, interface_type, duration, debug, id, append_to_csv, repeat, repeat_time
):
    """Discover nearby Meshtastic nodes using 0-hop traceroute."""

    click.echo("🌐 Meshtastic Nearby Node Discoverer")
    click.echo("=" * 40)
    click.echo("Using 0-hop traceroute to broadcast address")
    if repeat > 1:
        click.echo(f"Repeating {repeat} times with {repeat_time} second intervals")
    click.echo()

    all_nodes = []

    for run_number in range(1, repeat + 1):
        if repeat > 1:
            click.echo(f"\n🔄 Run {run_number} of {repeat}")
            click.echo("-" * 30)

        # Create a new discoverer instance for each run to ensure clean state
        discoverer = NearbyNodeDiscoverer(
            interface_type=interface_type,
            device_path=address,
            debug=debug,
            test_run_id=id,
            csv_file=append_to_csv,
        )

        click.echo(f"Listening for responses for {duration} seconds...")
        run_start_time = time.time()
        nearby_nodes = discoverer.discover_nearby_nodes(duration=duration)
        run_duration = time.time() - run_start_time

        all_nodes.extend(nearby_nodes)

        if nearby_nodes:
            click.echo("✅ Discovery run completed successfully")
        else:
            click.echo("ℹ️  No nearby nodes found in this run")

        # Wait for the remaining time if there are more runs
        if run_number < repeat:
            remaining_wait = repeat_time - run_duration
            if remaining_wait > 0:
                click.echo(f"⏳ Waiting {remaining_wait:.1f} seconds until next run...")
                time.sleep(remaining_wait)
            else:
                click.echo(
                    "⚠️  Run took longer than repeat interval, starting next run immediately"
                )

    # Final summary
    if repeat > 1:
        click.echo(
            f"\n📊 Final Summary: {len(all_nodes)} total nodes discovered across {repeat} runs"
        )
