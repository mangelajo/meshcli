"""Connection utilities for meshcli."""

import re
import platform
import click
import meshtastic.serial_interface
import meshtastic.tcp_interface
import meshtastic.ble_interface


def detect_interface_type(address: str) -> str:
    """Auto-detect interface type based on address format."""
    if not address or address == "any":
        return "ble"  # Default to BLE for auto-discovery
    if address.startswith("/dev/"):
        return "serial"
    # IP addresses (IPv4 and IPv6)
    if (
        re.match(r"^\d{1,3}(\.\d{1,3}){3}$", address)
        or ":" in address
        and "::" in address
    ):
        return "tcp"
    # Hostnames (contain dots or are common hostnames)
    if "." in address or address in ["localhost", "meshtastic.local"]:
        return "tcp"
    # BLE MAC address format (XX:XX:XX:XX:XX:XX)
    if re.match(r"^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$", address):
        return "ble"
    # Default to BLE for other formats (device names, UUIDs, etc.)
    return "ble"


def connect(address: str = None, interface_type: str = "auto", **kwargs):
    """Create and return the appropriate interface based on type or auto-detect."""
    if interface_type == "auto":
        interface_type = detect_interface_type(address)
    try:
        if interface_type == "serial":
            if address:
                # On Darwin, recommend /dev/cu.* over /dev/tty.* for outbound connections
                if platform.system() == "Darwin" and address.startswith("/dev/tty."):
                    cu_address = address.replace("/dev/tty.", "/dev/cu.")
                    click.echo(
                        f"Note: On macOS, consider using {cu_address} instead of {address} for better compatibility",
                        err=True,
                    )
                return meshtastic.serial_interface.SerialInterface(
                    devPath=address, **kwargs
                )
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
        help="Interface type: serial, tcp, ble, or auto",
    )(func)
    func = click.option(
        "--address",
        default=None,
        help="Device address (serial port, IP, or BLE MAC/name)",
    )(func)
    return func
