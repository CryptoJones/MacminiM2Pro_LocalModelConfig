# MacminiM2Pro_LocalModelConfig

Sanitized [oMLX](https://omlx.app/) configuration for running a tool-call-capable local LLM on a 16 GB Apple Silicon M2 Pro Mac mini, fronting Claude Code (and other Anthropic-API clients) with `Qwen3-1.7B-4bit`.

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

The setup went from 4.9 tok/s (with constant client-side cancellations) to 85.7 tok/s through five tunings, in roughly this order of impact:

1. **Right model tier.** Started on `Qwen2.5-Coder-7B-Instruct` (code-completion-tuned — answers prose instead of calling tools), tried `Qwen3-8B-4bit` (too heavy for 16 GB, thinking mode wastes tokens), settled on `Qwen3-4B-Instruct-2507-4bit` (2.1 GB, no thinking by default), then `Qwen3-1.7B-4bit` (~1 GB) with thinking explicitly suppressed for an additional 2× throughput.
2. **Disabled oMLX's paged SSD cache.** oMLX 0.3.9.dev2 has a bug where the SSD KV cache thrashes on Claude Code's large system prompts — `SSD cache write queue full` warnings, `store_cache_main_prep` time grows unboundedly per request, clients hit `[stream_generate] GeneratorExit` cancellations. Setting `cache.enabled: false` eliminates the failure mode at the cost of losing prefix caching (so prompt eval is paid in full each turn).
3. **Aligned `claude_code.target_context_size` with the model's real window.** Was at the default 200 000 (Claude's window); set to 30 000 so the local 4B / 1.7B isn't asked to handle prompts it can't actually fit.
4. **`thinking_budget_enabled: false` for the 1.7B in `model_settings.json`.** Qwen3-1.7B is a unified-mode model (no dedicated Instruct-2507 variant exists at this size); without this setting it emits `<think>...</think>` preambles that burn the generation budget before the user-visible reply starts.
5. **Fresh reboot after model swaps.** macOS jetsam will sometimes pin a few GB of swap from a previously-loaded larger model even after that model is unloaded; a reboot reliably drains it. Cheap, but it matters on 16 GB.

The realistic ceiling for this hardware is what's in this config. Prompt eval on Apple Silicon M2 Pro runs ~1500 tok/s, so a 10K-token Claude Code prompt eats ~7 s before generation starts; that's the dominant cost, not the model itself. The only big lever left is prefix caching — when oMLX fixes `hot_cache_only` (`hot_cache_only: true` is not currently honored — SSD cache still initializes), repeated Claude Code system prompts get cached in RAM and effective tok/s should ~2–3×.

## Files

| Path | What it is |
|---|---|
| `configs/settings.json` | Main oMLX server settings (`~/.omlx/settings.json` on the mini). API key + secret key redacted. |
| `configs/model_settings.json` | Per-model tuning (`~/.omlx/model_settings.json`). Currently holds the `Qwen3-1.7B-4bit` entry with thinking disabled. |
| `configs/hermes-bashrc-snippet.sh` | Env-var block to append to the client user's `~/.bashrc` so `claude` talks to the mini and asks for the right model name. |

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

## Hardware assumptions

- Apple Silicon M2 Pro, 16 GB unified memory
- macOS 26+ (Tahoe-era)
- oMLX 0.3.9.dev2 (or compatible)
- ~5 GB free disk for models + cache

Bigger Apple Silicon (32 GB+, M3/M4 Max) can run the 4B comfortably and may benefit from re-enabling caching once the upstream bug is fixed.

## License

Apache 2.0. See [LICENSE](LICENSE).

Proudly Made in Nebraska. Go Big Red! 🌽 https://xkcd.com/2347/
