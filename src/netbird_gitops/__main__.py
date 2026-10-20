"""Command line: python -m netbird_gitops [--config FILE] [--dry-run] [--validate]

Environment:
  NB_API_URL     management URL, e.g. https://netbird.example.com (required unless --validate)
  NB_TOKEN_FILE  file holding a personal access token of an admin service user
  NB_TOKEN       the token itself (NB_TOKEN_FILE takes precedence)
  NB_CONFIG      configuration file (default /etc/netbird-gitops/config.json)
  NB_DRY_RUN     "true" to only print the plan
"""

import argparse
import os
import sys

from . import __version__, config
from .api import ApiError, NetBirdApi
from .reconcile import Reconciler


def _log(msg):
    print(msg, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="netbird-gitops", description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=os.environ.get("NB_CONFIG", "/etc/netbird-gitops/config.json"))
    parser.add_argument("--dry-run", action="store_true",
                        default=os.environ.get("NB_DRY_RUN", "").lower() in ("1", "true", "yes"))
    parser.add_argument("--validate", action="store_true", help="only validate the configuration")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    try:
        cfg = config.load(args.config)
    except config.ConfigError as exc:
        _log(f"ERROR: configuration: {exc}")
        return 2
    if args.validate:
        _log(f"configuration OK: {len(cfg['tools'])} tool(s), {len(cfg['userGroups'])} user group(s)")
        return 0

    url = os.environ.get("NB_API_URL")
    token = None
    token_file = os.environ.get("NB_TOKEN_FILE")
    if token_file:
        try:
            with open(token_file, encoding="utf-8") as f:
                token = f.read().strip()
        except OSError as exc:
            _log(f"ERROR: cannot read NB_TOKEN_FILE: {exc}")
            return 2
    token = token or os.environ.get("NB_TOKEN")
    if not url or not token:
        _log("ERROR: NB_API_URL and NB_TOKEN_FILE (or NB_TOKEN) are required")
        return 2

    api = NetBirdApi(url, token, dry_run=args.dry_run, log=_log)
    _log(f"netbird-gitops {__version__}: {'dry run' if args.dry_run else 'apply'}"
         f"{', strict' if cfg['strict'] else ''}")
    try:
        return Reconciler(api, cfg, log=_log).run()
    except ApiError as exc:
        _log(f"ERROR: {exc}")
        _log(f"aborted after {api.changes} change(s)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
