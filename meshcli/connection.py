"""Connection utilities for meshcli."""

import re
import click
import meshtastic.serial_interface
import meshtastic.tcp_interface
import meshtastic.ble_interface

def detect_interface_type(address: str) -> str:
    """Auto-detect interface type based on address format."""
    if address.startswith("/dev/"):
        return "serial"
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", address) or ":" in address:
        return "tcp"
    # Match BLE MAC address (e.g., 01:23:45:67:89:AB)
    if re.match(r"^[a-zA-Z0-9\-\.]+$", address):
        return "tcp"
    return "ble" # node names, uuids, or other formats default to BLE

def connect(address: str = None, interface_type: str = "auto", **kwargs):
    """Create and return the appropriate interface based on type or auto-detect."""
    if interface_type == "auto":
        interface_type = detect_interface_type(address)
    try:
        if interface_type == "serial":
            if address:
                return meshtastic.serial_interface.SerialInterface(devPath=address, **kwargs)
            else:
                return meshtastic.serial_interface.SerialInterface(**kwargs)
        elif interface_type == "tcp":
            hostname = address or "meshtastic.local"
            return meshtastic.tcp_interface.TCPInterface(hostname=hostname, **kwargs)
        elif interface_type == "ble":
            if address:
                return meshtastic.ble_interface.BLEInterface(address=address, **kwargs)
            else:
                return meshtastic.ble_interface.BLEInterface(**kwargs)
        else:
            raise ValueError(f"Unknown interface_type: {interface_type}")
    except Exception as e:
        click.echo(f"Failed to connect: {e}", err=True)
        return None

def address_options(func):
    """Decorator to add address and interface-type options to a click command."""
    func = click.option(
        "--interface-type",
        default="auto",
        show_default=True,
        help="Interface type: serial, tcp, ble, or auto"
    )(func)
    func = click.option(
        "--address",
        default="any", # any bluetooth device
        help="Device address (serial port, IP, or BLE MAC/name)"
    )(func)
    return func