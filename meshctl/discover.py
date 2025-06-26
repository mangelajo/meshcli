"""Discovery functionality for meshcli."""

import time

import click
from meshtastic import BROADCAST_ADDR
from pubsub import pub
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)

from .connection import address_options
from .traceroute import TracerouteBase


class NearbyNodeDiscoverer(TracerouteBase):
    def __init__(
        self,
        interface_type="auto",
        device_path=None,
        debug=False,
        test_run_id=None,
        csv_file=None,
    ):
        super().__init__(interface_type, device_path, debug, test_run_id, csv_file)
        self.nearby_nodes = []
        self.discovery_active = False

    def on_traceroute_response(self, packet, interface):
        """Handle traceroute responses during discovery"""
        if not self.active:
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
            display_name = self.format_node_display(sender_id, self.known_nodes)

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

    def discover_nearby_nodes(self, duration=60, current_run=None, total_runs=None):
        """Send 0-hop traceroute and listen for responses"""
        if not self.connect():
            return []

        try:
            # Get known nodes first
            self.known_nodes = self.get_known_nodes()

            # Subscribe to traceroute responses
            pub.subscribe(self.on_traceroute_response, "meshtastic.receive.traceroute")

            self.active = True
            self.nearby_nodes = []

            click.echo("🔍 Starting interactive nearby node discovery...")
            click.echo(f"   Listening for responses for {duration} seconds...")
            click.echo("   Using 0-hop traceroute to broadcast address")

            # Send traceroute packet
            packet = self.send_traceroute(BROADCAST_ADDR, hop_limit=0)

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
                # Create progress description with run info if provided
                description = "Discovering nodes..."
                if current_run is not None and total_runs is not None:
                    description = (
                        f"Discovering nodes... (Run {current_run}/{total_runs})"
                    )

                task = progress.add_task(description, total=duration)

                start_time = time.time()
                while time.time() - start_time < duration:
                    elapsed = time.time() - start_time
                    progress.update(task, completed=elapsed)
                    time.sleep(0.1)  # More frequent updates for smoother progress bar

            self.active = False

            # Report results
            nearby_count = len(self.nearby_nodes)
            if self.nearby_nodes:
                # Create a table for the results
                table = self.create_results_table(
                    self.nearby_nodes,
                    self.known_nodes,
                    f"\n📊 Discovery complete! Found {nearby_count} nearby nodes:",
                )
                self.console.print(table)

                # Append to CSV if requested
                if self.csv_file:
                    self.append_to_csv(self.nearby_nodes, self.known_nodes)
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
            self.active = False
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
        nearby_nodes = discoverer.discover_nearby_nodes(
            duration=duration, current_run=run_number, total_runs=repeat
        )
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
