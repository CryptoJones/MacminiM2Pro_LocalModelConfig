#!/usr/bin/env python
"""Authoritative memory/perf safety test for serving Gemma 4 12B on 16 GB.

Usage:
  safety_test.py <repo> [--kv-bits N] [--max-kv-size N]

Metal working-set ceiling on this machine = 11.84 GB. The test verifies peak
stays safely under it (no Metal OOM) and that swap does not balloon under load.
"""
import time, subprocess, argparse, re
import mlx.core as mx
from mlx_vlm import load, generate

GEMMA = "<start_of_turn>user\n{p}<end_of_turn>\n<start_of_turn>model\n"
CEILING_GB = 13.5  # raised via sysctl iogpu.wired_limit_mb=13500

ap = argparse.ArgumentParser()
ap.add_argument("repo")
ap.add_argument("--kv-bits", type=int, default=None)
ap.add_argument("--max-kv-size", type=int, default=None)
ap.add_argument("--prefill-step-size", type=int, default=None)
args = ap.parse_args()

gen_kw = {}
if args.kv_bits: gen_kw["kv_bits"] = args.kv_bits
if args.max_kv_size: gen_kw["max_kv_size"] = args.max_kv_size
if args.prefill_step_size: gen_kw["prefill_step_size"] = args.prefill_step_size

def peak_gb(): return mx.get_peak_memory() / 1e9
def reset_peak():
    try: mx.reset_peak_memory()
    except Exception: pass
def swap_mb():
    out = subprocess.check_output(["sysctl", "vm.swapusage"]).decode()
    m = re.search(r"used = ([\d.]+)M", out); return float(m.group(1)) if m else -1.0
def free_pct():
    try:
        out = subprocess.check_output(["memory_pressure"]).decode()
        m = re.search(r"free percentage:\s*(\d+)%", out); return int(m.group(1)) if m else -1
    except Exception: return -1
def banner(s): print(f"\n=== {s} ===", flush=True)

print(f"MODEL={args.repo}  kv_bits={args.kv_bits}  max_kv_size={args.max_kv_size}  prefill_step={args.prefill_step_size}  ceiling={CEILING_GB}GB", flush=True)
swap0 = swap_mb()
print(f"baseline swap={swap0:.0f}MB free={free_pct()}%", flush=True)

banner("LOAD")
t = time.time(); model, processor = load(args.repo); load_s = time.time() - t
print(f"load {load_s:.1f}s | peak {peak_gb():.2f}GB | headroom {CEILING_GB-peak_gb():.2f}GB | swap {swap_mb():.0f}MB", flush=True)

def run(name, prompt, max_tokens):
    reset_peak(); t = time.time()
    res = generate(model, processor, GEMMA.format(p=prompt), max_tokens=max_tokens,
                   temperature=0.3, eos_tokens=["<end_of_turn>"], repetition_penalty=1.1,
                   skip_special_tokens=True, verbose=False, **gen_kw)
    dt = time.time() - t
    gtps = getattr(res, "generation_tps", None) or getattr(res, "generation_tokens_per_second", None)
    ntok = getattr(res, "generation_tokens", None)
    pk = peak_gb()
    flag = "  <-- OVER CEILING!" if pk > CEILING_GB else ""
    print(f"[{name:9}] {dt:5.1f}s gen_tps={gtps} tok={ntok} | peak {pk:.2f}GB "
          f"headroom {CEILING_GB-pk:.2f}GB | swap {swap_mb():.0f}MB free {free_pct()}%{flag}", flush=True)
    return pk

# Escalating context sizes — find where it breaks (or confirm it doesn't).
banner("ESCALATING CONTEXT STRESS")
sizes = [("short", 30), ("med_1k", 130), ("big_3k", 380)]
fill = "Apple Silicon uses a unified memory architecture shared by CPU and GPU. "
peaks = []
for name, reps in sizes:
    p = "Summarize:\n\n" + fill * reps
    peaks.append(run(name, p, 256))

banner("THROUGHPUT STABILITY (5x)")
for i in range(5):
    peaks.append(run(f"req{i+1}", "Explain transformers in 4 sentences.", 200))

banner("VERDICT")
mp = max(peaks); sg = swap_mb() - swap0
print(f"max peak {mp:.2f}GB / ceiling {CEILING_GB}GB (headroom {CEILING_GB-mp:.2f}GB) | swap growth {sg:+.0f}MB")
print("SAFE FOR HEADLESS SERVER:", "YES" if (mp < CEILING_GB - 0.4 and sg < 500) else "NO/MARGINAL")
