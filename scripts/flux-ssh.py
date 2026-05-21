#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate an image by SSH'ing into the Mac mini and running `flux` there.

The mini has FLUX.1-schnell loaded via MFLUX (Apple-Silicon-only); this
wrapper lets any non-Mac machine on the LAN dispatch a generation to the
mini and pull the result back over scp. From the user's perspective:

    flux "your prompt"            # on Linux/other host
        => image appears in ~/Pictures/mflux-<timestamp>.png locally

The mini-side counterpart is `flux.py` in this same directory (deployed
on the mini as ~/.local/bin/flux). This wrapper deploys to the *client's*
~/.local/bin/flux. Same command name, different machine, transparent.

Defaults are set for Aaron's network. To repoint at a different mini,
override via env vars:

    FLUX_MINI_HOST=other-mini.local FLUX_MINI_USER=someone flux "..."

Or edit the constants below.
"""
import argparse
import datetime
import os
import pathlib
import shlex
import subprocess
import sys

MINI_HOST = os.environ.get("FLUX_MINI_HOST", "Aarons-Mac-mini.local")
MINI_USER = os.environ.get("FLUX_MINI_USER", "akclark")
MINI_REMOTE_FLUX = os.environ.get("FLUX_MINI_BIN", "/Users/akclark/.local/bin/flux")
LOCAL_OUTPUT_DIR = pathlib.Path(
    os.environ.get("FLUX_OUTPUT_DIR", "~/Pictures")
).expanduser()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an image with FLUX.1-schnell on the Mac mini, save it locally.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"Runs `{MINI_REMOTE_FLUX}` on {MINI_USER}@{MINI_HOST} and copies "
            f"the result to {LOCAL_OUTPUT_DIR}/mflux-<timestamp>.png."
        ),
    )
    parser.add_argument("prompt", help="What to draw.")
    parser.add_argument("--steps", type=int, default=4, help="Diffusion steps, 1-4 for schnell (default: 4).")
    parser.add_argument("--width", type=int, default=1024, help="Image width, multiple of 16 (default: 1024).")
    parser.add_argument("--height", type=int, default=1024, help="Image height, multiple of 16 (default: 1024).")
    parser.add_argument("--seed", type=int, default=None, help="Reproducible seed (default: time-based on the mini).")
    parser.add_argument(
        "--keep-remote",
        action="store_true",
        help="Don't delete the PNG and sidecar from the mini after copying (default: clean up).",
    )
    return parser.parse_args()


def ssh_cmd(remote_cmd: str) -> list[str]:
    # ssh joins all post-host argv with spaces before passing to the remote
    # shell, which collapses our list-of-args into a single command string.
    # So we hand it ONE pre-quoted command and let the remote shell parse it.
    return ["ssh", f"{MINI_USER}@{MINI_HOST}", remote_cmd]


def scp_cmd(remote_path: str, local_path: pathlib.Path) -> list[str]:
    return ["scp", "-q", f"{MINI_USER}@{MINI_HOST}:{remote_path}", str(local_path)]


def main() -> int:
    args = parse_args()

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"mflux-{timestamp}.png"
    remote_png = f"/Users/{MINI_USER}/Pictures/{filename}"
    remote_meta = remote_png.replace(".png", ".metadata.json")

    flux_args = [
        shlex.quote(args.prompt),
        "--steps", str(args.steps),
        "--width", str(args.width),
        "--height", str(args.height),
        "--output", remote_png,
    ]
    if args.seed is not None:
        flux_args.extend(["--seed", str(args.seed)])

    remote_cmd = f"{MINI_REMOTE_FLUX} {' '.join(flux_args)}"
    print(f"on {MINI_HOST}: {remote_cmd}", flush=True)

    proc = subprocess.Popen(
        ssh_cmd(remote_cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
    rc = proc.wait()
    if rc != 0:
        print(f"\nerror: remote flux exited {rc}", file=sys.stderr)
        return rc

    LOCAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_png = LOCAL_OUTPUT_DIR / filename
    local_meta = LOCAL_OUTPUT_DIR / filename.replace(".png", ".metadata.json")

    subprocess.run(scp_cmd(remote_png, local_png), check=True)
    subprocess.run(scp_cmd(remote_meta, local_meta), check=False)

    if not args.keep_remote:
        subprocess.run(
            ssh_cmd(f"rm -f {shlex.quote(remote_png)} {shlex.quote(remote_meta)}"),
            check=False,
        )

    print(f"saved: {local_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
