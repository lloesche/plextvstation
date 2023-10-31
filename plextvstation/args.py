from argparse import ArgumentParser, Namespace
from typing import Callable, List, Optional
from . import __version__ as version, __description__ as description, __title__ as title


def parse_args(
    add_args: Optional[List[Callable[[ArgumentParser], None]]] = None,
    validate_args: Optional[List[Callable[[ArgumentParser, Namespace], None]]] = None,
) -> Namespace:
    parser = ArgumentParser(prog=title, description=f"{description} (v{version})")
    parser.add_argument("-v", "--verbose", dest="verbose", help="Enable verbose logging", action="store_true")
    parser.add_argument(
        "-d",
        "--directory",
        dest="directory",
        help="Working directory (default: ~/plextvstation)",
        default="~/plextvstation",
    )

    if add_args is not None:
        for add_arg in add_args:
            add_arg(parser)

    args = parser.parse_args()

    if validate_args is not None:
        for validate_arg in validate_args:
            validate_arg(parser, args)

    return args
