"""Main CLI module for meshcli."""

import click
from .discover import discover
from .list_nodes import list_nodes


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


# Add the commands to the main group
main.add_command(discover)
main.add_command(list_nodes)


if __name__ == "__main__":
    main()
