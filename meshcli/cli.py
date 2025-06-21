"""Main CLI module for meshcli."""

import click


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


if __name__ == "__main__":
    main()
