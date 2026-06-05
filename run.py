#!/usr/bin/env python
"""Run Gemma 4 12B (4-bit MLX) on Apple Silicon with the correct chat template.

Usage:
  ~/gemma4/.venv/bin/python ~/gemma4/run.py "your prompt here"
  ~/gemma4/.venv/bin/python ~/gemma4/run.py "describe this" --image path.jpg
"""
import argparse
from mlx_vlm import load, generate

MODEL = "mlx-community/gemma-4-12B-4bit"

# This MLX conversion ships without tokenizer.chat_template, so apply the
# Gemma turn format manually. <bos> is added by the tokenizer automatically.
GEMMA_TMPL = "<start_of_turn>user\n{p}<end_of_turn>\n<start_of_turn>model\n"

ap = argparse.ArgumentParser()
ap.add_argument("prompt", nargs="?", default="Explain why MLX is fast on Apple Silicon in two sentences.")
ap.add_argument("--image", nargs="*", default=[])
ap.add_argument("--max-tokens", type=int, default=300)
ap.add_argument("--temperature", type=float, default=0.7)
args = ap.parse_args()

model, processor = load(MODEL)

formatted = GEMMA_TMPL.format(p=args.prompt)

generate(
    model, processor, formatted,
    image=args.image,
    max_tokens=args.max_tokens,
    temperature=args.temperature,
    eos_tokens=["<end_of_turn>"],
    repetition_penalty=1.1,
    skip_special_tokens=True,
    verbose=True,
)
