"""Novulon's Sims Hub.

    python  -m speedkit.hub            serve on 127.0.0.1:8766 (opens nothing by itself)
    python  -m speedkit.hub --open     make sure the server runs (in the background, no console) and open the window
    pythonw -m speedkit.hub            the same as --open: what the Desktop shortcut runs
    options: --serve (just serve, even under pythonw), --port N, --stub (example data)

The __main__ guard matters: the engine may use worker processes (Windows 'spawn' re-imports this module)."""
import argparse
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m speedkit.hub', description="Novulon's Sims Hub")
    how = ap.add_mutually_exclusive_group()
    how.add_argument('--open', action='store_true', help='start the server if needed and open the Hub window')
    how.add_argument('--serve', action='store_true', help='only serve (the default for python.exe)')
    ap.add_argument('--port', type=int, help='port (default 8766, or SIMS_HUB_PORT)')
    ap.add_argument('--stub', action='store_true', help='show example data instead of using the engine')
    ap.add_argument('--profile', help=argparse.SUPPRESS)          # the window's browser profile (tests)
    args, _ = ap.parse_known_args(argv)
    if args.stub:
        os.environ['SIMS_HUB_API'] = 'stub'
    if args.port:
        os.environ['SIMS_HUB_PORT'] = str(args.port)
    windowed = os.path.basename(sys.executable or '').lower() == 'pythonw.exe'
    if args.open or (windowed and not args.serve):
        from speedkit.hub import launcher
        port = int(os.environ.get('SIMS_HUB_PORT', '8766'))
        return launcher.open_hub(port, stub=args.stub, profile=args.profile or launcher.PROFILE)
    from speedkit.hub.server import main as serve       # imported after the options: it reads the port then
    return serve()


if __name__ == '__main__':
    sys.exit(main())
