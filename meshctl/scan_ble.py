"""BLE scan functionality for meshcli."""

import click
import meshtastic.ble_interface


@click.command("scan-ble")
def scan_ble():
    """Scan for Meshtastic BLE devices."""
    click.echo("🔍 Scanning for BLE devices...")
    try:
        devices = meshtastic.ble_interface.BLEInterface.scan()
        if not devices:
            click.echo("No BLE devices found.")
            return
        for i, dev in enumerate(devices, 1):
            click.echo(f"{i}. Name: '{dev.name}'  Address: '{dev.address}'")
    except Exception as e:
        click.echo(f"Error during BLE scan: {e}", err=True)
