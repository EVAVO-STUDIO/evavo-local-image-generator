# EVAVO Fully Automated Generation Guide

Complete automation system for EVAVO multi-modal AI generation. Works with Claude, ChatGPT, and direct command line.

## Quick Start

### From Claude (Cowork)
```
Execute this automation:
python EVAVO-AUTOMATION.py
```

### From ChatGPT / Command Line
```bash
cd C:\Gitrepos\evavo-local-image-generator
python EVAVO-AUTOMATION.py
```

## Modes

### Full Automation (Default)
```bash
python EVAVO-AUTOMATION.py
# or
python EVAVO-AUTOMATION.py --mode full
```
- Starts ComfyUI, Ollama, and Kokoro services
- Runs complete multi-modal generation tests (71 tests)
- Copies all outputs to `C:\Users\User\beestation\evavo-generation\`

**Duration:** ~10-30 minutes depending on system and generation complexity

### Test Only
```bash
python EVAVO-AUTOMATION.py --mode test
```
- Runs generation tests WITHOUT starting services
- **Requires:** ComfyUI, Ollama running separately
- Useful for testing when services are already running

### Generation Only
```bash
python EVAVO-AUTOMATION.py --mode generate
```
- Runs generation without full test suite
- **Requires:** ComfyUI, Ollama running separately

## What Gets Generated

The automation generates real, AI-produced content across 7 modalities:

1. **Images** (45 tests)
   - Text-to-image generation
   - Image upscaling and enhancement
   - Style transfers

2. **Videos** (3 tests)
   - Text-to-video synthesis
   - Image animation
   - Video interpolation

3. **Audio** (6 tests)
   - Text-to-speech synthesis
   - Voice cloning
   - Audio generation

4. **Text** (3 tests)
   - LLM-based text generation
   - Prompt refinement
   - Content creation

5. **3D Models** (6 tests)
   - 3D asset generation
   - Model variations
   - Mesh generation

6. **Particles & Effects** (4 tests)
   - Particle system generation
   - VFX creation
   - Animation effects

7. **PBR Textures** (4 tests)
   - Material generation
   - Texture creation
   - Surface attributes

**Total: 71 comprehensive tests** generating real AI content

## Output Location

All generated content is saved to:
```
C:\Users\User\beestation\evavo-generation\
```

Organized by modality:
```
evavo-generation/
├── evavo-images/        (45 generated images)
├── evavo-videos/        (3 generated videos)
├── evavo-audio/         (6 generated audio files)
├── evavo-text/          (3 generated text files)
├── evavo-particles/     (4 particle systems)
├── evavo-models/        (6 3D models)
├── evavo-textures/      (4 texture sets)
└── evavo-state/         (generation metadata & logs)
```

## Prerequisites

### On Windows Machine
- **Python 3.8+** installed
- **ComfyUI** running at `C:\AI\ComfyUI\`
- **Ollama** installed and available
- **Kokoro TTS** (optional, at `C:\AI\Kokoro-FastAPI\`)
- **GPU** with adequate VRAM (RTX 3080+ recommended for optimal speed)

### From Claude/ChatGPT
- Session linked to Windows machine via Cowork
- Device has `device_bash` access to mounted folders
- Sufficient disk space in `C:\Users\User\beestation\`

## Usage from AI Assistants

### Claude (Cowork)
```python
# In Cowork, run directly:
Execute full EVAVO automation:
python C:\Gitrepos\evavo-local-image-generator\EVAVO-AUTOMATION.py

# Or specify mode:
Run tests only:
python C:\Gitrepos\evavo-local-image-generator\EVAVO-AUTOMATION.py --mode test
```

### ChatGPT (with File Upload)
1. Attach this automation script to ChatGPT
2. Ask: "Run the EVAVO automation to generate content"
3. ChatGPT will execute the automation and report progress

### Direct Command Line
```bash
# Navigate to repo
cd C:\Gitrepos\evavo-local-image-generator

# Run automation
python EVAVO-AUTOMATION.py

# Or with specific mode
python EVAVO-AUTOMATION.py --mode full
```

## Troubleshooting

### ComfyUI Not Found
- Ensure ComfyUI is at `C:\AI\ComfyUI\`
- Run ComfyUI separately: `cd C:\AI\ComfyUI && python main.py`

### Ollama Not Running
- Install Ollama from https://ollama.ai/
- Start Ollama service before running automation
- Check: `ollama serve` in terminal

### Generation Errors
- Check `evavo-state/generation-report.json` for details
- Ensure GPU has sufficient VRAM
- Try running in test-only mode first

### Permission Errors
- Ensure write access to `C:\Users\User\beestation\`
- Check folder ownership and permissions
- Run as Administrator if needed

## Advanced Options

### Custom Output Location
Edit the script and change:
```python
self.beestation = Path("C:\\Users\\User\\your-custom-path\\evavo-generation")
```

### Custom Test Suite
Replace `COMPLETE-MULTIMODAL-TEST.py` with your own test file

### Extend Automation
Add new modalities by editing the `run_generation()` method

## Integration with CI/CD

The automation can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run EVAVO Generation
  run: python EVAVO-AUTOMATION.py --mode full
  timeout-minutes: 60
```

## Support

For issues or feature requests:
1. Check `evavo-state/generation-report.json` for error details
2. Review logs in the respective output directories
3. Verify all prerequisites are installed
4. Run in test-only mode to isolate issues

## Version

- **Current:** 1.0 (Production Ready)
- **Platform:** Windows + Linux VM (mounted paths)
- **Tested with:** Claude, ChatGPT, Direct CLI
