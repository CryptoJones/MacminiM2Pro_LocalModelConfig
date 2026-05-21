# SPDX-License-Identifier: Apache-2.0
#
# MFLUX (FLUX.1 on MLX) — image generation alongside the oMLX LLM
# on a 16 GB Apple Silicon Mac mini.
#
# MFLUX (github.com/filipstrand/mflux) is a community port of Black
# Forest Labs' FLUX.1 to Apple's MLX framework. It runs entirely on
# the Mac's GPU + unified memory, has no server dependency, and
# supports 4-bit / 8-bit quantization so the model fits in the same
# 16 GB budget that runs Qwen3-1.7B for Claude Code (just not
# simultaneously — see Hardware notes in README).
#
# Model:    FLUX.1-schnell (Apache 2.0; 1-4 step diffusion;
#           base model, no refusal layer — see README).
# Storage:  ~9 GB on disk steady-state for the 4-bit weights
#           (~31 GB transient FP16 download during mflux-save; the
#           FP16 cache can be deleted afterwards).
# Peak RAM: ~9 GB resident working set during a 1024×1024 generation.
# Latency:  ~22-25 s per diffusion step at 1024×1024 on M2 Pro;
#           ~90 s end-to-end for the 4-step schnell preset.

# ---- one-time install ----
# pipx (preferred — keeps MFLUX out of any project venv):
#   pipx install mflux
#
# or in a dedicated venv:
#   python -m venv ~/.mflux-venv
#   source ~/.mflux-venv/bin/activate
#   pip install mflux

# ---- IMPORTANT: free RAM before the first generation ----
# On a 16 GB box with oMLX running and the usual desktop GUI apps
# open (Chrome, Discord, Firefox, Steam, Signal), MFLUX's warmup
# silently stalls in swap thrash — the process stays alive at
# ~1.5% CPU and ~66 MB RSS but never makes diffusion-step progress.
# Empirically observed: 48 minutes of zero progress in that state.
# Quitting those apps freed ~8 GB and the same warmup then ran in
# 91 s. Quit them via the menubar or:
#
#   osascript -e 'quit app "oMLX"'
#   osascript -e 'quit app "Google Chrome"'
#   osascript -e 'quit app "Discord"'
#   osascript -e 'quit app "Firefox"'
#   osascript -e 'quit app "Steam"'      # may show a confirm dialog
#   osascript -e 'quit app "Signal"'

# ---- one-time: pre-save the 4-bit-quantized model ----
# mflux-save downloads the FP16 weights from HuggingFace, quantizes
# them once, and writes the result to a self-contained directory at
# --path. Subsequent generations point --model at that directory and
# skip the (in-memory) re-quantization that --quantize would otherwise
# do on every cold start. Run this once, not per generation.
#
# IMPORTANT: mflux 0.17.5 does NOT auto-cache --quantize output under
# ~/.cache/mflux/. That directory does not exist after mflux-generate
# --quantize 4. mflux-save is the only way to persist the quantization.
mflux-save \
    --model schnell \
    --quantize 4 \
    --path ~/mflux-models/schnell-4bit

# After mflux-save completes, the 4-bit weights at the --path above
# are fully self-contained. You can free the ~31 GB FP16 cache:
#
#   rm -rf ~/.cache/huggingface/hub/models--black-forest-labs--FLUX.1-schnell
#
# Skip this rm only if you plan to re-quantize at a different bit
# width (3/5/6/8) and don't want to re-download the FP16 weights.

# ---- everyday generation ----
# --model points at the saved 4-bit directory, not the "schnell" alias.
# --base-model schnell tells mflux which sampler/step defaults apply
# (the saved path is a directory, not a known alias).
# Adjust --steps (1-4 for schnell), --width / --height (multiples of
# 16), --seed for reproducibility. --metadata writes a sidecar .json
# with the exact prompt + seed + flags so the image is regeneratable.
mflux-generate \
    --model ~/mflux-models/schnell-4bit \
    --base-model schnell \
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
#   non-commercial license — change `--model schnell` to `--model dev`
#   in the mflux-save step (and `--base-model dev` in generate) only
#   if your use case allows that license.
# - Don't run MFLUX and oMLX at the same time on a 16 GB box.
#   Either stop the oMLX menubar app before generating images, or
#   use a single-purpose session for each. Both at once will push
#   macOS into heavy swap and grind both workloads to a crawl.
# - The README's "Image generation" section has the same workflow
#   plus context on why we picked schnell over dev/SDXL.
