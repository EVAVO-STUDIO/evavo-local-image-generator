#!/bin/bash
# Full EVAVO generation with real services - runs in background

echo "EVAVO FULL GENERATION START - $(date)" >> generation.log

# Start ComfyUI
cd "$HOME/mnt/AI/ComfyUI"
python main.py >> "$HOME/mnt/Gitrepos/evavo-local-image-generator/comfyui.log" 2>&1 &
COMFY_PID=$!
echo "ComfyUI started PID: $COMFY_PID" >> "$HOME/mnt/Gitrepos/evavo-local-image-generator/generation.log"

sleep 5

# Start Ollama
ollama serve >> "$HOME/mnt/Gitrepos/evavo-local-image-generator/ollama.log" 2>&1 &
OLLAMA_PID=$!
echo "Ollama started PID: $OLLAMA_PID" >> "$HOME/mnt/Gitrepos/evavo-local-image-generator/generation.log"

sleep 3

# Run test suite
cd "$HOME/mnt/Gitrepos/evavo-local-image-generator"
python COMPLETE-MULTIMODAL-TEST.py --execute >> "$HOME/mnt/Gitrepos/evavo-local-image-generator/test.log" 2>&1

# Copy to beestation
echo "Copying to beestation..." >> "$HOME/mnt/Gitrepos/evavo-local-image-generator/generation.log"

for dir in evavo-images evavo-videos evavo-audio evavo-text evavo-particles evavo-models evavo-textures evavo-state evavo-generations; do
  if [ -d "$dir" ]; then
    mkdir -p "$HOME/mnt/Users/User/beestation/evavo-generation/$dir"
    cp -r "$dir"/* "$HOME/mnt/Users/User/beestation/evavo-generation/$dir/" 2>/dev/null
    echo "Copied $dir" >> "$HOME/mnt/Gitrepos/evavo-local-image-generator/generation.log"
  fi
done

echo "GENERATION COMPLETE - $(date)" >> "$HOME/mnt/Gitrepos/evavo-local-image-generator/generation.log"

