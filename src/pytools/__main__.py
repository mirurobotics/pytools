import sys

from pytools.commands.root import run


def main() -> None:
    """Run the pytools command line."""
    run(sys.argv[1:])


if __name__ == "__main__":
    main()
