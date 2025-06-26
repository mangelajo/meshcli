"""Main CLI module for meshcli."""

import click
from .discover import discover
from .list_nodes import list_nodes
from .ping import ping
from .scan_ble import scan_ble
from .connection import connect


@click.group()
@click.version_option()
def main():
    """A CLI tool for mesh operations."""
    pass


@click.command()
@click.option("--address", help="Device address (serial port, IP, or BLE MAC/name)")
@click.option(
    "--interface-type", default="auto", help="Interface type: serial, tcp, ble, or auto"
)
def some_command(address, interface_type):
    """Example command using the new connection logic."""
    connect(address=address, interface_type=interface_type)
    # ... use iface as needed ...


# Add the commands to the main group
main.add_command(discover)
main.add_command(list_nodes)
main.add_command(ping)
main.add_command(scan_ble)


if __name__ == "__main__":
    main()
