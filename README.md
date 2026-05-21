# MacminiM2Pro_LocalModelConfig

Sanitized configuration for running local AI workloads on a 16 GB Apple Silicon M2 Pro Mac mini:

- **Tool-call-capable LLM** for Claude Code via [oMLX](https://omlx.app/) — currently `Qwen3-1.7B-4bit`, ~85 tok/s end-to-end.
- **Image generation** via [MFLUX](https://github.com/filipstrand/mflux) — `FLUX.1-schnell` 4-bit, ~20-30 s per 1024×1024 image.

> oMLX is open source at [github.com/jundot/omlx](https://github.com/jundot/omlx) — bug reports, releases, and source live there.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?logo=apache)](LICENSE)
[![Codeberg](https://img.shields.io/badge/Codeberg-CryptoJones%2FMacminiM2Pro_LocalModelConfig-2185D0?logo=codeberg&logoColor=white)](https://codeberg.org/CryptoJones/MacminiM2Pro_LocalModelConfig)
[![GitHub](https://img.shields.io/badge/GitHub-CryptoJones%2FMacminiM2Pro_LocalModelConfig-181717?logo=github&logoColor=white)](https://github.com/CryptoJones/MacminiM2Pro_LocalModelConfig)
[![Version](https://img.shields.io/badge/version-v0.1.0-orange)]()

> Mirrored on both [GitHub](https://github.com/CryptoJones/MacminiM2Pro_LocalModelConfig) and
> [Codeberg](https://codeberg.org/CryptoJones/MacminiM2Pro_LocalModelConfig). Issues filed on
> either are welcome; commits are pushed to both.

---

## What it does

Captures a known-good config for serving a local model from oMLX on tight-memory Apple Silicon hardware (16 GB unified) so that Claude Code (and any other Anthropic-API-compatible client) sees usable inference throughput — currently around **85 tok/s** end-to-end on Claude-Code-shaped prompts. The configs here are sanitized copies of what's actually deployed.

## What got us to ~85 tok/s

The setup went from 4.9 tok/s (with constant client-side cancellations) to 85.7 tok/s. Every change that mattered, in roughly the order it had impact:

### Model selection

1. **Avoid code-completion-tuned models for agentic use.** Started on `Qwen2.5-Coder-7B-Instruct-MLX-4bit` (downloaded automatically by oMLX integrations). That model is fine-tuned to *write code in response to instructions*, not to call tools — so Claude Code asked it to do things and it answered with prose explaining how. Classic "gives instructions instead of acting" symptom.
2. **Avoid models whose weight footprint plus macOS overhead exceeds RAM.** Tried `Qwen3-8B-4bit` (~4.6 GB) on 16 GB unified. Loaded fine, but combined with macOS + apps + KV cache the system stayed under heavy memory pressure, oMLX engine pool unloaded/reloaded mid-session, and effective tok/s dropped to single digits.
3. **Prefer dedicated non-thinking ("Instruct") variants over unified-mode Qwen3 where they exist.** `Qwen3-4B-Instruct-2507-4bit` (2.1 GB) was a big jump in stability — fits comfortably, doesn't burn tokens on chain-of-thought. Hit ~40 tok/s sustained on 1k-token prompts.
4. **Drop the model size further if the larger one isn't head-room-clear.** `Qwen3-1.7B-4bit` (~1 GB) cut prompt-eval cost in half (which is the dominant cost on this hardware) and got us to ~88 tok/s server-side, ~85 tok/s end-to-end through Claude Code. Quality drop is noticeable on complex reasoning, fine for short interactive turns.
5. **For unified-mode Qwen3 models (no Instruct-2507 variant at that size), force-disable thinking.** Add a per-model entry to `~/.omlx/model_settings.json` with `thinking_budget_enabled: false`. Without it the model emits `<think>...</think>` preambles that eat the generation budget before the user-visible reply starts. The 1.7B has no `Instruct-2507` variant, so this is the only way to get clean output.

### oMLX server tunings

6. **On 16 GB Apple Silicon, leave caching off: `cache.enabled: false`, `hot_cache_max_size: "0"`.** This is hardware-dependent. oMLX v0.3.9rc1 *does* fix the dev2 bug where `hot_cache_only: true` was silently ignored (you can now genuinely run RAM-only caching), and on a synthetic 2K-token repeated-prefix benchmark we measured 4.4× speedup. But on 16 GB unified, allocating even 2 GB to hot cache pushes the system into heavy swap (was at 81% swap usage / 5 GB swap during testing), prompt eval slows under page pressure, and the `GeneratorExit` cancellations come back — same symptom, different cause (memory pressure, not the rc1-fixed code bug). Real Claude Code prompts also vary turn-to-turn (timestamps, dynamic context), so cache hit rate is lower than the synthetic test suggests. Net: on 16 GB this hardware, you pay more in memory pressure than you save in cached prefixes. **On 32 GB+ Apple Silicon, set `cache.enabled: true`, `hot_cache_only: true`, `hot_cache_max_size: "4GB"` instead** — the cache benefit is real once you have headroom for it.
7. **In rc1, the cache-init log line `paged SSD cache enabled: cache_dir=...` appears even with `hot_cache_only: true` correctly working at runtime.** The line is misleading text from a code path that wasn't updated; verify actual cache behavior with `du -sh ~/.omlx/cache` (shouldn't grow) and `grep "queue full" ~/.omlx/logs/server.log` (shouldn't fire) — not the init log string.
8. **Set `claude_code.target_context_size` to match the local model's real window**, not Claude's. The default 200 000 tells Claude Code "this model has Claude's context window" and Claude Code happily sends 30–60K token prompts. Setting it to 30 000 (matching Qwen3's ~32K context) caps the prompts at what the model can actually handle without saturating prompt eval.
9. **Clean stale model entries out of `~/.omlx/model_settings.json`.** Old per-model entries for models that no longer exist on disk trigger `WARNING - Default model 'X' not found, using first model` on every startup and can interact with model discovery in subtle ways. Set `models: {}` to a blank dict and re-add only what's actually installed.

### Client-side wiring (Claude Code)

10. **Tell Claude Code which Anthropic API endpoint to use:** `export ANTHROPIC_BASE_URL=http://<mini-ip>:8000`. oMLX serves the Anthropic Messages API at `/v1/messages` on the same port as the OpenAI-compatible API.
11. **Set a placeholder API key:** `export ANTHROPIC_API_KEY=local`. oMLX's `auth.skip_api_key_verification: true` setting means the key isn't actually checked, but Claude Code refuses to start without *some* key set.
12. **Map every Claude tier (opus/sonnet/haiku) to the local model name** via `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`. Claude Code sends the literal model name (`claude-haiku-4-5`, etc.) in the request body; without these env vars oMLX 404s on every request because it has no `claude-*` model loaded. The oMLX `claude_code.opus_model/sonnet_model/haiku_model` settings only apply when oMLX *launches* Claude Code via its own integration — for manual `claude` launches you must set the env vars yourself.
13. **Consider raising `API_TIMEOUT_MS`** for sessions where prompt eval may exceed Claude Code's default request timeout (e.g., big repo context). `export API_TIMEOUT_MS=300000` (5 min) prevents premature client disconnects on cold-start requests.

### macOS-level

14. **Reboot after switching to a smaller model** if you were previously running a larger one. macOS will sometimes pin several GB of swap from a previously-loaded model even after that model is unloaded by oMLX, leaving the new smaller model fighting for resident memory. A reboot reliably drains the swap. Cheap, but it matters on 16 GB.
15. **Quit memory-hungry GUI apps** (Chrome, Signal, Creative Cloud, Dropbox Helper) before serious inference. Each GB you free reduces compressor pressure on the model's working set and stops macOS from spilling KV state to swap. Activity Monitor → sort by Memory → make decisions.

### What's *not* in this config but would help (future work)

- **Speculative decoding.** oMLX supports `specprefill_enabled` for matched draft/target pairs; no public Qwen3 draft model exists today for this exact target, but Qwen2.5-0.5B works as a rough draft for Qwen2.5-class targets — a research project, not a flip.
- **Hardware upgrade.** 32 GB+ M3/M4 Pro/Max would let you run the 4B comfortably alongside a working cache, and would more-than-double prompt-eval throughput thanks to higher memory bandwidth.

### Why this ceiling

Prompt eval on Apple Silicon M2 Pro runs roughly 1500 tokens/sec, so a 10K-token Claude Code prompt eats ~7 s before generation starts. On 16 GB hardware, that cost is paid in full every turn (caching off, per item 6). On 32 GB+ hardware with the hot cache enabled, the cost is paid once and then skipped on subsequent turns that share the same prefix. Expect 30–45 tok/s effective on this 16 GB mini, and 60–85 tok/s effective on bigger Apple Silicon with caching on.

## Image generation: FLUX.1-schnell via MFLUX

The same 16 GB box can run a credible image model alongside (just not _simultaneously with_) the LLM. We landed on **`FLUX.1-schnell`** through **[MFLUX](https://github.com/filipstrand/mflux)** — a community Apple-MLX port of Black Forest Labs' FLUX.1 family.

Why this pick:

- **Fits the box.** Quantized to 4-bit via MFLUX's `--quantize 4`, the weights cap out around **6-7 GB on disk** with a **~7-9 GB peak RAM** working set during a 1024×1024 generation. Comfortable on 16 GB unified, _as long as oMLX isn't also serving Qwen3 at the same moment_ (we stop the oMLX menubar app for image-gen sessions).
- **Apple Silicon native.** MLX runs on the unified-memory GPU path directly; no PyTorch+MPS translation layer, no CoreML conversion step. Generation time is ~20-30 s per 1024×1024 image at the model's recommended 4 inference steps. The schnell variant is _designed_ for low step counts (1-4) — the bigger FLUX.1-dev needs 20-50 steps and runs proportionally slower.
- **No built-in refusal.** FLUX.1-schnell is a base model — there is no safety-classifier layer that rejects prompts before generation. The training data is fairly clean (less explicit imagery than older SD checkpoints), but the model itself doesn't refuse and produces what you ask within whatever its weights learned. Good fit for an operator who wants "doesn't second-guess my prompts" without committing to NSFW-specialty fine-tunes.
- **Apache 2.0.** Matches this repo's license. Commercial use OK. (FLUX.1-_dev_ is slightly higher quality but ships under FLUX.1's non-commercial license — pick `schnell` unless your use case allows the non-commercial terms.)

Install + first-run is in [`configs/mflux-launch-snippet.sh`](configs/mflux-launch-snippet.sh): `pipx install mflux`, then `mflux-generate --model schnell --quantize 4 --steps 4 --width 1024 --height 1024 ...`. First generation pulls the un-quantized weights (~24 GB transient) and writes 4-bit weights under `~/.cache/mflux/`; subsequent runs reuse the quantized cache.

## Models we got running successfully

The history of what actually loaded and ran on this 16 GB M2 Pro box, in the order we tried them. "Got running" is generous — some loaded but were impractical for the workload. Read this with the [iteration notes above](#what-got-us-to-85-toks) for the why.

| Model | Size on disk | Framework | Role | Outcome on 16 GB M2 Pro |
|---|---|---|---|---|
| `Qwen2.5-Coder-7B-Instruct-MLX-4bit` | ~4.2 GB | oMLX | Claude Code LLM (tried) | Loaded and served, but completion-tuned — answered Claude Code's tool requests with prose instructions instead of calling tools. Replaced. |
| `Qwen3-8B-4bit` | ~4.6 GB | oMLX | Claude Code LLM (tried) | Loaded but combined with macOS + Claude Code + KV cache, the system stayed under heavy memory pressure; the oMLX engine pool unloaded/reloaded mid-session and effective throughput fell to single-digit tok/s. Replaced. |
| `Qwen3-4B-Instruct-2507-4bit` | ~2.1 GB | oMLX | Claude Code LLM (tried) | Comfortable fit, no thinking-token waste, ~40 tok/s sustained on 1k-token prompts. A reasonable choice if you want a little more headroom on complex reasoning at the cost of throughput. |
| **`Qwen3-1.7B-4bit`** | **~1 GB** | **oMLX** | **Claude Code LLM (current)** | **~88 tok/s server-side, ~85 tok/s end-to-end through Claude Code. Quality drop is noticeable on multi-step reasoning, fine for short interactive turns. Requires `thinking_budget_enabled: false` in `model_settings.json` because this size has no `Instruct-2507` variant.** |
| **`FLUX.1-schnell`** (4-bit via MFLUX) | **~6-7 GB** | **MFLUX** | **Image generation (current)** | **~20-30 s per 1024×1024 at 4 steps. ~7-9 GB peak RAM. Apache 2.0, base model, no refusal layer. Don't run concurrently with oMLX on this box.** |

Possible future additions not yet evaluated: speculative-decoding draft models for the Qwen3 target, FLUX.1-dev for higher-fidelity image gen on a 32 GB upgrade, a small TTS/STT model alongside the LLM.

## Files

| Path | What it is |
|---|---|
| `configs/settings.json` | Main oMLX server settings (`~/.omlx/settings.json` on the mini). API key + secret key redacted. |
| `configs/model_settings.json` | Per-model tuning (`~/.omlx/model_settings.json`). Currently holds the `Qwen3-1.7B-4bit` entry with thinking disabled. |
| `configs/hermes-bashrc-snippet.sh` | Env-var block to append to the client user's `~/.bashrc` so `claude` talks to the mini and asks for the right model name. |
| `configs/mflux-launch-snippet.sh` | One-time install + everyday `mflux-generate` invocation for FLUX.1-schnell image generation on the same mini. |

## How to apply

On the mini (the inference server):

```bash
# Replace placeholders in settings.json with real values, then:
cp configs/settings.json ~/.omlx/settings.json
cp configs/model_settings.json ~/.omlx/model_settings.json
# Restart oMLX from the menubar — settings load on server start.
```

You'll need to substitute these placeholders in `configs/settings.json`:

- `<YOUR_API_KEY>` — any string (the bundled config sets `skip_api_key_verification: true` so it's not enforced, but the key still has to exist)
- `<YOUR_SECRET_KEY>` — generated once by oMLX on first launch; either reuse your existing one or let oMLX regenerate by deleting the file
- `server_aliases` — the included list (`172.16.28.199` etc.) is operator-specific; replace with your mini's actual address
- Paths under `/Users/akclark/` — replace with your home directory

On the client (any machine running `claude`):

```bash
# Append the env vars to ~/.bashrc (idempotent: skip if already present)
cat configs/hermes-bashrc-snippet.sh >> ~/.bashrc
# Open a fresh shell, then:
claude
```

Pull the model on the mini first via the oMLX GUI's model browser, searching `mlx-community/Qwen3-1.7B-4bit`.

### For image generation (FLUX.1-schnell via MFLUX)

```bash
# One-time on the mini:
pipx install mflux

# First generation pulls + quantizes (~24 GB transient download,
# ~6-7 GB final on-disk). See configs/mflux-launch-snippet.sh for
# the full annotated command.
mflux-generate \
    --model schnell --quantize 4 --steps 4 \
    --width 1024 --height 1024 \
    --prompt "your prompt here" \
    --output ~/Pictures/out.png
```

**Stop the oMLX menubar app before running MFLUX on this 16 GB box.** They each fit individually but not together — running both at once pushes macOS into heavy swap and grinds both workloads.

## Hardware assumptions

- Apple Silicon M2 Pro, 16 GB unified memory
- macOS 26+ (Tahoe-era)
- oMLX 0.3.9.dev2 (or compatible)
- MFLUX 0.6+ (or compatible) for image generation
- ~5 GB free disk for the Qwen3 LLM + cache
- **Additional ~30 GB free disk transient (drops to ~7 GB steady-state)** if you also install FLUX.1-schnell via MFLUX

Bigger Apple Silicon (32 GB+, M3/M4 Max) can run the 4B comfortably and may benefit from re-enabling caching once the upstream bug is fixed. 32 GB+ also makes it practical to run the LLM and FLUX side-by-side without swap pressure.

## License

Apache 2.0. See [LICENSE](LICENSE).

Proudly Made in Nebraska. Go Big Red! 🌽 https://xkcd.com/2347/
