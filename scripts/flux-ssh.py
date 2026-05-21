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
import re
import shlex
import subprocess
import sys
import time

MINI_HOST = os.environ.get("FLUX_MINI_HOST", "Aarons-Mac-mini.local")
MINI_USER = os.environ.get("FLUX_MINI_USER", "akclark")
MINI_REMOTE_FLUX = os.environ.get("FLUX_MINI_BIN", "/Users/akclark/.local/bin/flux")
LOCAL_OUTPUT_DIR = pathlib.Path(
    os.environ.get("FLUX_OUTPUT_DIR", "~/Pictures/mflux")
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
        "--reference",
        action="append",
        default=None,
        help=(
            "Reference image (URL or local file path). Pass once for img2img on schnell. "
            "Pass 2+ times (`--reference A --reference B`) for FLUX Redux multi-image blend "
            "(triggers FLUX.1-dev path on the mini; non-commercial license)."
        ),
    )
    parser.add_argument(
        "--image-strength",
        type=float,
        action="append",
        default=None,
        help=(
            "Strength per reference. Single value with one --reference = img2img blend "
            "(0.0 = ignore ref, 1.0 = keep ref; defaults to 0.4). Multiple values matched "
            "positionally with multiple --reference = per-image Redux weights (defaults to 1.0 each)."
        ),
    )
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


URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def stage_reference_on_mini(ref: str, idx: int = 0) -> str:
    """Place the reference image on the mini and return its remote path.

    Accepts either an http(s) URL (downloaded on the mini via curl) or a
    local file path (scp'd to the mini). Returns the absolute remote path.
    """
    unique = f"flux-ref-{os.getpid()}-{int(time.time())}-{idx}"
    if URL_RE.match(ref):
        ext = pathlib.Path(ref.split("?", 1)[0]).suffix.lower() or ".img"
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
            ext = ".img"
        remote_ref = f"/tmp/{unique}{ext}"
        print(f"downloading reference on mini: {ref} -> {remote_ref}", flush=True)
        rc = subprocess.run(
            ssh_cmd(f"curl -fsSL --max-time 60 {shlex.quote(ref)} -o {shlex.quote(remote_ref)}"),
        ).returncode
        if rc != 0:
            print(f"error: failed to download reference (curl exit {rc})", file=sys.stderr)
            sys.exit(1)
    else:
        local = pathlib.Path(ref).expanduser().resolve()
        if not local.is_file():
            print(f"error: --reference '{ref}' is neither an http(s) URL nor an existing local file", file=sys.stderr)
            sys.exit(1)
        ext = local.suffix.lower() or ".img"
        remote_ref = f"/tmp/{unique}{ext}"
        print(f"uploading reference to mini: {local} -> {remote_ref}", flush=True)
        rc = subprocess.run(
            ["scp", "-q", str(local), f"{MINI_USER}@{MINI_HOST}:{remote_ref}"],
        ).returncode
        if rc != 0:
            print(f"error: scp failed (exit {rc})", file=sys.stderr)
            sys.exit(1)
    return remote_ref


def main() -> int:
    args = parse_args()

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"mflux-{timestamp}.png"
    remote_png = f"/Users/{MINI_USER}/Pictures/mflux/{filename}"
    remote_meta = remote_png.replace(".png", ".metadata.json")

    references = args.reference or []
    remote_refs: list[str] = []
    for idx, ref in enumerate(references):
        remote_refs.append(stage_reference_on_mini(ref, idx=idx))

    flux_args = [
        shlex.quote(args.prompt),
        "--steps", str(args.steps),
        "--width", str(args.width),
        "--height", str(args.height),
        "--output", remote_png,
    ]
    if args.seed is not None:
        flux_args.extend(["--seed", str(args.seed)])
    for r in remote_refs:
        flux_args.extend(["--image-path", r])
    if args.image_strength is not None:
        for s in args.image_strength:
            flux_args.extend(["--image-strength", str(s)])

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

    cleanup_targets = []
    if not args.keep_remote:
        cleanup_targets.extend([remote_png, remote_meta])
    cleanup_targets.extend(remote_refs)
    if cleanup_targets:
        subprocess.run(
            ssh_cmd("rm -f " + " ".join(shlex.quote(p) for p in cleanup_targets)),
            check=False,
        )

    print(f"saved: {local_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
