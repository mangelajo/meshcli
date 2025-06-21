"""List nodes functionality for meshcli."""

import datetime

import click
from .connection import address_options, connect


class NodeLister:
    def __init__(self, interface_type="serial", device_path=None):
        self.interface_type = interface_type
        self.device_path = device_path
        self.interface = None

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

                    user = node.get("user", {})
                    node_id = user.get("id", f"!{node_num:08x}")
                    long_name = user.get("longName", "Unknown")
                    snr = node.get("snr")
                    last_heard = node.get("lastHeard")

                    known_nodes.append(
                        {
                            "id": node_id,
                            "name": long_name,
                            "snr": snr,
                            "last_heard": last_heard,
                            "num": node_num,
                        }
                    )

                if known_nodes:
                    # Sort by last heard (most recent first)
                    def sort_key(x):
                        return x["last_heard"] or 0

                    known_nodes.sort(key=sort_key, reverse=True)

                    for i, node in enumerate(known_nodes, 1):
                        last_heard_str = "Unknown"
                        if node["last_heard"]:
                            dt = datetime.datetime.fromtimestamp(node["last_heard"])
                            last_heard_str = dt.strftime("%Y-%m-%d %H:%M:%S")

                        snr_str = (
                            f"SNR: {node['snr']}dB" if node["snr"] else "SNR: Unknown"
                        )
                        click.echo(f"  {i}. {node['id']} ({node['name']})")
                        click.echo(f"     {snr_str}, " f"Last heard: {last_heard_str}")
                else:
                    click.echo("  No other nodes in database")
            else:
                click.echo("  Node database is empty")

        except Exception as e:
            click.echo(f"Error showing known nodes: {e}", err=True)
        finally:
            self.interface.close()


@click.command("list-nodes")
@address_options
def list_nodes(address, interface_type):
    """Show currently known nodes from the node database."""
    lister = NodeLister(interface_type=interface_type, device_path=address)
    lister.show_known_nodes()
