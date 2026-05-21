#!/Users/akclark/.local/pipx/venvs/mflux/bin/python
# SPDX-License-Identifier: Apache-2.0
"""Generate an image with the locally-saved FLUX.1-schnell on the Mac mini.

Calls the MFLUX Python API directly (no subprocess to `mflux-generate`),
using the 4-bit model that lives at ~/mflux-models/schnell-4bit/.

Usage:
    flux.py "a tiny astronaut hatching from an egg on the moon"
    flux.py "a serene Japanese tea garden at golden hour" --seed 1812
    flux.py "neon-lit alley at night" --width 768 --height 1344 --steps 4

The shebang points at the mflux pipx venv's interpreter so the script
runs directly. If you move the script to a machine where mflux was
installed differently, change the shebang or invoke as:

    ~/.local/pipx/venvs/mflux/bin/python flux.py "..."
"""
import argparse
import datetime
import pathlib
import sys
import time

MODEL_PATH = pathlib.Path("~/mflux-models/schnell-4bit").expanduser()
DEV_MODEL_PATH = pathlib.Path("~/mflux-models/dev-4bit").expanduser()
OUTPUT_DIR = pathlib.Path("~/Pictures/mflux").expanduser()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an image with FLUX.1-schnell.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Output PNGs land in ~/Pictures/mflux-<timestamp>.png with a sidecar .metadata.json.",
    )
    parser.add_argument("prompt", help="What to draw.")
    parser.add_argument("--steps", type=int, default=4, help="Diffusion steps, 1-4 for schnell (default: 4).")
    parser.add_argument("--width", type=int, default=1024, help="Image width, multiple of 16 (default: 1024).")
    parser.add_argument("--height", type=int, default=1024, help="Image height, multiple of 16 (default: 1024).")
    parser.add_argument("--seed", type=int, default=None, help="Reproducible seed (default: time-based).")
    parser.add_argument(
        "--image-path",
        type=pathlib.Path,
        action="append",
        default=None,
        help=(
            "Reference image. Pass once for img2img on schnell. Pass 2+ times "
            "(`--image-path A --image-path B`) for FLUX Redux multi-image blend "
            "(uses FLUX.1-dev, non-commercial license). Default: text-to-image."
        ),
    )
    parser.add_argument(
        "--image-strength",
        type=float,
        action="append",
        default=None,
        help=(
            "Reference strength. Single value paired with single --image-path = img2img "
            "(0.0 = ignore ref, 1.0 = keep ref, default 0.4). Multiple values paired with "
            "multiple --image-path = per-image Redux weights (default 1.0 per image)."
        ),
    )
    parser.add_argument(
        "--dev-model-path",
        type=pathlib.Path,
        default=DEV_MODEL_PATH,
        help=f"Path to mflux-save'd FLUX.1-dev 4-bit directory (used in Redux mode only; default: {DEV_MODEL_PATH}).",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help=f"Output path (default: {OUTPUT_DIR}/mflux-<timestamp>.png).",
    )
    parser.add_argument(
        "--model-path",
        type=pathlib.Path,
        default=MODEL_PATH,
        help=f"Path to mflux-save'd 4-bit model directory (default: {MODEL_PATH}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    image_paths = args.image_path or []
    image_strengths = args.image_strength or []

    for p in image_paths:
        if not p.exists():
            print(f"error: reference image not found at {p}", file=sys.stderr)
            return 1

    if args.seed is None:
        args.seed = int(time.time())

    if args.output is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        args.output = OUTPUT_DIR / f"mflux-{timestamp}.png"

    args.output.parent.mkdir(parents=True, exist_ok=True)

    if len(image_paths) >= 2:
        return _generate_redux(args, image_paths, image_strengths)
    return _generate_schnell(args, image_paths, image_strengths)


def _generate_schnell(args, image_paths, image_strengths) -> int:
    if not args.model_path.exists():
        print(
            f"error: schnell model directory not found at {args.model_path}\n"
            f"run `mflux-save --model schnell --quantize 4 --path {args.model_path}` first.",
            file=sys.stderr,
        )
        return 1

    print(f"loading FLUX.1-schnell from {args.model_path} ...", flush=True)
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux.variants.txt2img.flux import Flux1

    flux = Flux1(
        model_config=ModelConfig.from_name(model_name=str(args.model_path), base_model="schnell"),
    )

    generate_kwargs = dict(
        seed=args.seed,
        prompt=args.prompt,
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
    )
    if image_paths:
        ref = image_paths[0]
        strength = image_strengths[0] if image_strengths else 0.4
        generate_kwargs["image_path"] = str(ref)
        generate_kwargs["image_strength"] = strength
        print(
            f"img2img: {args.width}x{args.height} at {args.steps} steps, "
            f"seed={args.seed}, ref={ref}, strength={strength}",
            flush=True,
        )
    else:
        print(f"generating {args.width}x{args.height} at {args.steps} steps, seed={args.seed}", flush=True)

    t0 = time.time()
    image = flux.generate_image(**generate_kwargs)
    image.save(path=str(args.output), export_json_metadata=True)
    print(f"done in {time.time() - t0:.1f}s -> {args.output}")
    return 0


def _generate_redux(args, image_paths, image_strengths) -> int:
    if not args.dev_model_path.exists():
        print(
            f"error: FLUX.1-dev model directory not found at {args.dev_model_path}\n"
            f"multi-image blending uses FLUX Redux on top of dev. Run:\n"
            f"  mflux-save --model dev --quantize 4 --path {args.dev_model_path}\n"
            f"first. Note: FLUX.1-dev is non-commercial license.",
            file=sys.stderr,
        )
        return 1

    print(f"loading FLUX.1-dev + Redux adapter from {args.dev_model_path} ...", flush=True)
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux.variants.redux.flux_redux import Flux1Redux
    from mflux.models.flux.variants.redux.redux_util import ReduxUtil

    flux = Flux1Redux(
        model_config=ModelConfig.dev_redux(),
        model_path=str(args.dev_model_path),
    )

    strengths = image_strengths if image_strengths else None
    strengths = ReduxUtil.validate_redux_image_strengths(
        redux_image_paths=image_paths,
        redux_image_strengths=strengths,
    )

    print(
        f"redux: {args.width}x{args.height} at {args.steps} steps, seed={args.seed}, "
        f"refs={[str(p) for p in image_paths]}, "
        f"strengths={strengths if strengths else 'default (1.0 each)'}",
        flush=True,
    )

    t0 = time.time()
    image = flux.generate_image(
        seed=args.seed,
        prompt=args.prompt,
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
        redux_image_paths=[str(p) for p in image_paths],
        redux_image_strengths=strengths,
    )
    image.save(path=str(args.output), export_json_metadata=True)
    print(f"done in {time.time() - t0:.1f}s -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
