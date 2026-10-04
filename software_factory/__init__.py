"""A deterministic evidence ledger for software tasks."""

try:
    from ._version import __version__
except ImportError:  # A source checkout can run without first building a wheel.
    __version__ = "0.2.0"
