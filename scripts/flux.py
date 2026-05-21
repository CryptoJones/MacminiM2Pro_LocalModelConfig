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
OUTPUT_DIR = pathlib.Path("~/Pictures").expanduser()


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
        default=None,
        help="Reference image for image-to-image generation (default: text-to-image, no reference).",
    )
    parser.add_argument(
        "--image-strength",
        type=float,
        default=None,
        help="How much the reference image influences the output: 0.0 = ignore ref (pure text2img), 1.0 = keep ref unchanged. Defaults to 0.4 when --image-path is set. (Schnell at 4 steps doesn't have much room to transform — for strong prompt-driven changes use a low strength like 0.2-0.3.)",
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

    if not args.model_path.exists():
        print(
            f"error: model directory not found at {args.model_path}\n"
            f"run `mflux-save --model schnell --quantize 4 --path {args.model_path}` first.",
            file=sys.stderr,
        )
        return 1

    if args.seed is None:
        args.seed = int(time.time())

    if args.output is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        args.output = OUTPUT_DIR / f"mflux-{timestamp}.png"

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"loading FLUX.1-schnell from {args.model_path} ...", flush=True)
    from mflux.models.common.config import ModelConfig
    from mflux.models.flux.variants.txt2img.flux import Flux1

    flux = Flux1(
        model_config=ModelConfig.from_name(model_name=str(args.model_path), base_model="schnell"),
    )

    if args.image_path is not None:
        if not args.image_path.exists():
            print(f"error: reference image not found at {args.image_path}", file=sys.stderr)
            return 1
        if args.image_strength is None:
            args.image_strength = 0.4  # MFLUX default; without this, --image-path is silently ignored.
        print(
            f"img2img: {args.width}x{args.height} at {args.steps} steps, "
            f"seed={args.seed}, ref={args.image_path}, "
            f"strength={'default' if args.image_strength is None else args.image_strength}",
            flush=True,
        )
    else:
        print(
            f"generating {args.width}x{args.height} at {args.steps} steps, seed={args.seed}",
            flush=True,
        )
    t0 = time.time()
    generate_kwargs = dict(
        seed=args.seed,
        prompt=args.prompt,
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
    )
    if args.image_path is not None:
        generate_kwargs["image_path"] = str(args.image_path)
    if args.image_strength is not None:
        generate_kwargs["image_strength"] = args.image_strength
    image = flux.generate_image(**generate_kwargs)
    image.save(path=str(args.output), export_json_metadata=True)
    elapsed = time.time() - t0
    print(f"done in {elapsed:.1f}s -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
