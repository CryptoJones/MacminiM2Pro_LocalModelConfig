# SPDX-License-Identifier: Apache-2.0
# Append this to ~/.bashrc on any user that will run `claude` (Claude Code)
# pointing at the local oMLX instance.

# --- oMLX (Mac mini) endpoint for Claude Code ---
export ANTHROPIC_BASE_URL=http://172.16.28.199:8000   # replace with your mini's address
export ANTHROPIC_API_KEY=local                        # any string; oMLX has skip_api_key_verification:true
export ANTHROPIC_DEFAULT_OPUS_MODEL=Qwen3-1.7B-4bit
export ANTHROPIC_DEFAULT_SONNET_MODEL=Qwen3-1.7B-4bit
export ANTHROPIC_DEFAULT_HAIKU_MODEL=Qwen3-1.7B-4bit
# --- end oMLX endpoint ---
