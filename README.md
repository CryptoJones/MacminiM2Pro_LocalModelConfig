# MacminiM2Pro_LocalModelConfig

**Memory-safe, LAN-accessible, OpenAI-compatible server for [Gemma 4 12B](https://developers.googleblog.com/gemma-4-12b-the-developer-guide/) running locally in [MLX](https://github.com/ml-explore/mlx) on a 16 GB Apple Silicon M2 Pro Mac mini.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?logo=apache)](LICENSE)
[![Codeberg](https://img.shields.io/badge/Codeberg-CryptoJones%2FMacminiM2Pro_LocalModelConfig-2185D0?logo=codeberg&logoColor=white)](https://codeberg.org/CryptoJones/MacminiM2Pro_LocalModelConfig)
[![GitHub](https://img.shields.io/badge/GitHub-CryptoJones%2FMacminiM2Pro_LocalModelConfig-181717?logo=github&logoColor=white)](https://github.com/CryptoJones/MacminiM2Pro_LocalModelConfig)

> Authoritative repo is on [Codeberg](https://codeberg.org/CryptoJones/MacminiM2Pro_LocalModelConfig); mirrored to [GitHub](https://github.com/CryptoJones/MacminiM2Pro_LocalModelConfig).

> 📺 Inspired by the video [*Gemma 4 12B on a 16GB Mac Mini Is Surprisingly Capable*](https://www.youtube.com/watch?v=PDxKrp-dTDA).

Gemma 4 12B is an encoder-free multimodal model (text/image/audio/video) that Google
positions for 16 GB machines. It *fits* — but only just. On 16 GB it sits right at the
Metal GPU memory ceiling, so a naive server **OOM-crashes on the first large prompt**.
This repo is the configuration and a small server wrapper that make it **safe to run
headless** and reachable by other agents on your LAN.

---

## The 16 GB problem (why this repo exists)

MLX inference is bounded by the **Metal recommended working-set size** — by default
~74 % of RAM = **11.84 GB** on a 16 GB machine. Measured peaks for Gemma 4 12B:

| Quant | Weights resident | Verdict on 16 GB |
|-------|------------------|------------------|
| `8bit` (12.7 GB) | — | ❌ won't load |
| `6bit` (11.9 GB) | **11.85 GB peak** | ❌ saturates the GPU budget → **Metal OOM on any real prompt**; forces 3.6 GB swap just to load |
| **`4bit` (10 GB)** | **10.99 GB load / 11.8 GB+ under load** | ✅ **only viable option** — and still needs the steps below |

Even 4-bit peaks **scale with input length** (prefill activations, *not* just KV cache):

| Input prompt | Peak memory |
|--------------|-------------|
| ~50 tokens   | 11.80 GB |
| ~360 tokens  | 11.80 GB |
| ~1,560 tokens| 13.21 GB |
| ~4,560 tokens| 💥 **OOM crash** |

Generation throughput: **~14–15 tokens/sec**.

### Two things make it safe

1. **Raise the Metal working-set limit** so the GPU may use more than the default 74 %.
   For a headless box, 13.5 GB leaves ~2.9 GB for macOS:
   ```bash
   sudo sysctl iogpu.wired_limit_mb=13500
   ```
   This resets on reboot — see [persisting it](#persist-the-gpu-limit-across-reboots).

2. **Guard against oversized prompts.** `server.py` rejects prompts over
   `MAX_INPUT_TOKENS` with **HTTP 413** instead of letting them OOM-crash the process,
   and **serializes** requests (a second concurrent generation would double the working
   set and OOM → **HTTP 429**).

---

## Quick start

```bash
git clone https://codeberg.org/CryptoJones/MacminiM2Pro_LocalModelConfig.git
cd MacminiM2Pro_LocalModelConfig
./setup.sh                                  # uv venv (py3.12) + deps + downloads 4-bit weights (~10 GB)
sudo sysctl iogpu.wired_limit_mb=13500      # raise GPU memory ceiling (per boot)
./.venv/bin/python server.py                # serves on 0.0.0.0:8080
```

> **Python note:** MLX has no wheels for Python 3.14 yet. `setup.sh` pins the venv to
> Python 3.12 via [`uv`](https://github.com/astral-sh/uv).

---

## Using it from the LAN

The server binds `0.0.0.0:8080`, so any agent on your network can use it as an
OpenAI-compatible endpoint. Find the host's LAN IP with `ipconfig getifaddr en0`.

```bash
curl http://<MAC_MINI_LAN_IP>:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Explain unified memory in one sentence."}],
       "max_tokens":80}'
```

```python
from openai import OpenAI
client = OpenAI(base_url="http://<MAC_MINI_LAN_IP>:8080/v1", api_key="not-needed")
print(client.chat.completions.create(
    model="mlx-community/gemma-4-12B-4bit",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

Endpoints: `GET /healthz`, `GET /v1/models`, `POST /v1/chat/completions`.

> **Security:** this server has **no authentication**. Only expose it on a trusted LAN,
> never directly to the internet. Put it behind a reverse proxy / firewall if needed.

---

## Files

| File | Purpose |
|------|---------|
| `server.py` | OpenAI-compatible FastAPI server with the memory-safety guards. |
| `run.py` | One-shot CLI generation (text or image), useful for testing. |
| `safety_test.py` | The authoritative memory/throughput test used to derive the limits above. |
| `setup.sh` | Creates the venv, installs deps, downloads the 4-bit weights. |
| `com.cryptojones.gemma4.plist` | Optional `launchd` agent to run the server headless at login. |

### One-shot CLI

```bash
./.venv/bin/python run.py "Write a haiku about unified memory."
./.venv/bin/python run.py "Describe this image." --image photo.jpg   # multimodal
```

### Re-run the safety test

```bash
./.venv/bin/python safety_test.py mlx-community/gemma-4-12B-4bit --kv-bits 8 --max-kv-size 2048
```

---

## Configuration

Edit the constants at the top of `server.py`:

| Constant | Default | Notes |
|----------|---------|-------|
| `MODEL` | `mlx-community/gemma-4-12B-4bit` | The only quant that fits 16 GB. |
| `MAX_INPUT_TOKENS` | `600` | Safety guard. ~600 in-tokens peaks ~12.1 GB. Raising it toward ~1,300 approaches the crash threshold — do so only if you raised `iogpu.wired_limit_mb` further. |
| `MAX_OUTPUT_TOKENS` | `512` | Hard cap on generation length. |
| `MAX_KV_SIZE` / `KV_BITS` | `2048` / `8` | Bounded, quantized KV cache. |

### A note on the chat template

The community MLX conversion ships **without** a `tokenizer.chat_template`. Feeding a raw
prompt makes Gemma 4 ramble and emit `<image|>`/`<audio|>` soft-tokens. Both `server.py`
and `run.py` apply the Gemma turn format manually
(`<start_of_turn>user … <end_of_turn><start_of_turn>model`) and stop on `<end_of_turn>`.

### Persist the GPU limit across reboots

`iogpu.wired_limit_mb` resets to 0 (default) on reboot. To make a headless server
survive reboots, install a `LaunchDaemon` that sets it at boot:

```bash
sudo tee /Library/LaunchDaemons/com.cryptojones.gpulimit.plist >/dev/null <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.cryptojones.gpulimit</string>
  <key>ProgramArguments</key>
  <array><string>/usr/sbin/sysctl</string><string>iogpu.wired_limit_mb=13500</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLIST
sudo launchctl load /Library/LaunchDaemons/com.cryptojones.gpulimit.plist
```

Then use `com.cryptojones.gemma4.plist` (a per-user `LaunchAgent`) to start the server itself.

---

## License

[Apache 2.0](LICENSE). Gemma 4 is released by Google under the Apache 2.0 license.

---

<p align="center"><em>Proudly Made in Nebraska. Go Big Red! 🌽 <a href="https://xkcd.com/2347/">https://xkcd.com/2347/</a></em></p>
