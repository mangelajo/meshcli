# meshctl

A CLI tool for mesh operations.

## Installation

### Using uv (recommended)

Run directly without installation:
```bash
uvx meshctl
```

### Using pip in a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install meshctl
```

## Usage

```bash
meshctl --help
```

## Development

### Setup

Install development dependencies:

```bash
make sync
```

Or manually with uv:

```bash
uv sync --dev
```

### Development Commands

Run tests:

```bash
make test
```

Format code:

```bash
make format
```

Lint code:

```bash
make lint
```

Build package:

```bash
make build
```

Run all checks:

```bash
make check
```

Clean build artifacts:

```bash
make clean
```

Install in development mode:

```bash
make install
```

See all available commands:

```bash
make help
```
