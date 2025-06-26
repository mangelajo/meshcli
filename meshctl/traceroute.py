"""Shared traceroute functionality for meshctl."""

import csv
import os
import datetime

import click
from meshtastic.protobuf import portnums_pb2, mesh_pb2
from rich.console import Console
from rich.table import Table
from .connection import connect


class TracerouteBase:
    """Base class for traceroute-based functionality."""

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
        self.responses = []
        self.active = False
        self.console = Console()
        self.test_run_id = test_run_id
        self.csv_file = csv_file
        self.known_nodes = {}

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

    def find_relay_candidates(self, relay_node_last_byte):
        """Find known nodes at 0 hops that could match the relay node based on last hex digits"""
        candidates = []

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
                                "name": self.format_node_display(
                                    node_id, self.known_nodes
                                ),
                            }
                        )

        return candidates

    def format_packet_details(self, packet):
        """Format packet details in a nice, readable way"""
        details = []

        # Basic packet info
        details.append(
            f"[bold cyan]Packet ID:[/bold cyan] {packet.get('id', 'Unknown')}"
        )

        # Format From field with name if known
        from_id = packet.get("fromId", "Unknown")
        from_num = packet.get("from", "Unknown")
        from_display = f"{from_id}"
        if from_id != "Unknown" and from_id in self.known_nodes:
            from_name = self.format_node_display(from_id, self.known_nodes)
            from_display = f"{from_id} ({from_name})"
        elif from_num != "Unknown":
            from_display = f"{from_id} (num: {from_num})"
        details.append(f"[bold cyan]From:[/bold cyan] {from_display}")

        # Format To field with name if known
        to_id = packet.get("toId", "Unknown")
        to_num = packet.get("to", "Unknown")
        to_display = f"{to_id}"
        if to_id != "Unknown" and to_id in self.known_nodes:
            to_name = self.format_node_display(to_id, self.known_nodes)
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
                    self.format_node_display(cand["id"], self.known_nodes)
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
                        if node_id in self.known_nodes:
                            node_name = self.format_node_display(
                                node_id, self.known_nodes
                            )
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
                            if node_id in self.known_nodes:
                                node_name = self.format_node_display(
                                    node_id, self.known_nodes
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
                                if node_id in self.known_nodes:
                                    node_name = self.format_node_display(
                                        node_id, self.known_nodes
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
            try:
                dt = datetime.datetime.fromtimestamp(rx_time)
                details.append(
                    f"[bold white]Received:[/bold white] {dt.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except (ValueError, OSError, OverflowError):
                details.append(f"[bold white]RX Time:[/bold white] {rx_time}")

        return details

    def append_to_csv(self, nodes, known_nodes):
        """Append results to CSV file"""
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

    def send_traceroute(self, destination_id, hop_limit=0):
        """Send a traceroute packet to the specified destination."""
        route_discovery = mesh_pb2.RouteDiscovery()
        packet = self.interface.sendData(
            data=route_discovery,
            destinationId=destination_id,
            portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
            wantResponse=True,
            hopLimit=hop_limit,
        )
        return packet

    def create_results_table(self, nodes, known_nodes, title):
        """Create a Rich table with the results."""
        table = Table(title=title)
        table.add_column("Timestamp", style="white", no_wrap=True)
        if self.test_run_id:
            table.add_column("Test Run ID", style="dim", no_wrap=True)
        table.add_column("Node ID", style="magenta")
        table.add_column("Short Name", style="bright_magenta")
        table.add_column("Long Name", style="bright_cyan")
        table.add_column("SNR (dB)", style="green")
        table.add_column("RSSI (dBm)", style="yellow")
        table.add_column("SNR Towards (dB)", style="bright_blue")

        for node in nodes:
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
            timestamp = datetime.datetime.fromtimestamp(node["timestamp"]).strftime(
                "%H:%M:%S"
            )

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

        return table
