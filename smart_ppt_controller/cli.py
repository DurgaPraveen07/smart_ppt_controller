import argparse
from smart_ppt_controller import __version__
from smart_ppt_controller.app import start_app


def main():
    parser = argparse.ArgumentParser(
        prog="smart-ppt-controller",
        description="Smart PPT Controller - Control presentations with hand gestures and voice commands"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to bind server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to listen on (default: 5000)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode"
    )

    args = parser.parse_args()
    start_app(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
