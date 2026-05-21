# SPDX-License-Identifier: Apache-2.0
#
# MFLUX (FLUX.1 on MLX) — image generation alongside the oMLX LLM
# on a 16 GB Apple Silicon Mac mini.
#
# MFLUX (github.com/filipstrand/mflux) is a community port of Black
# Forest Labs' FLUX.1 to Apple's MLX framework. It runs entirely on
# the Mac's GPU + unified memory, has no server dependency, and
# supports on-the-fly 4-bit / 8-bit quantization so the model fits
# in the same 16 GB budget that runs Qwen3-1.7B for Claude Code
# (just not simultaneously — see Hardware notes in README).
#
# Model:    FLUX.1-schnell (Apache 2.0; 1-4 step diffusion;
#           base model, no refusal layer — see README).
# Storage:  ~6-7 GB on disk after 4-bit quantization
#           (~24 GB for the un-quantized weights MFLUX downloads first).
# Peak RAM: ~7-9 GB during generation at 512x512 / 4 steps on M2 Pro.
# Latency:  ~20-30 s per 512x512 image at 4 steps; ~45-60 s at 768x768.

# ---- one-time install ----
# pipx (preferred — keeps MFLUX out of any project venv):
#   pipx install mflux
#
# or in a dedicated venv:
#   python -m venv ~/.mflux-venv
#   source ~/.mflux-venv/bin/activate
#   pip install mflux

# ---- one-time: pull + quantize the model ----
# The `--quantize 4` flag converts the safetensors to 4-bit on first
# generation and writes the result under ~/.cache/mflux/. Subsequent
# runs reuse the quantized weights. Without --quantize you'd run the
# full ~24 GB FP16 model, which won't fit alongside macOS.
#
# `--init-time-only` warms the model load + quantization cache without
# producing an image — handy to do once on a fast network instead of
# blocking your first real generation:
#
#   mflux-generate \
#     --model schnell \
#     --prompt "warmup" \
#     --steps 1 \
#     --quantize 4 \
#     --output /tmp/warmup.png

# ---- everyday generation ----
# Adjust --steps (1-4 for schnell), --width / --height (multiples of
# 16), --seed for reproducibility. --metadata writes a sidecar .json
# with the exact prompt + seed + flags so the image is regeneratable.
mflux-generate \
    --model schnell \
    --quantize 4 \
    --steps 4 \
    --width 1024 \
    --height 1024 \
    --seed 42 \
    --metadata \
    --output ~/Pictures/mflux-$(date +%Y%m%d-%H%M%S).png \
    --prompt "a tiny astronaut hatching from an egg on the moon, hyperrealistic"

# ---- notes ----
# - FLUX.1-schnell is Apache 2.0 (commercial use OK). FLUX.1-dev
#   exists at slightly higher quality but ships under the FLUX.1
#   non-commercial license — swap `--model schnell` for
#   `--model dev` only if your use case allows that license.
# - Don't run MFLUX and oMLX at the same time on a 16 GB box.
#   Either stop the oMLX menubar app before generating images, or
#   use a single-purpose session for each. Both at once will push
#   macOS into heavy swap and grind both workloads to a crawl.
