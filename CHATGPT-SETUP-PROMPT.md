# EVAVO HIGH-QUALITY LOCAL GENERATION SETUP PROMPT FOR CHATGPT

## Context
I have ComfyUI installed on Windows with NVIDIA GPU support (RTX 4080, CUDA 11.8, PyTorch 2.7.1). I'm implementing local AI generation with several tools:
- ComfyUI for image generation (Stable Diffusion XL)
- Kokoro-FastAPI for text-to-speech
- atmosphere-studio-tools for advanced creative capabilities

My initial image generation tests produced blurry, low-quality output (only 5 sampling steps). I've now improved the scripts to use 25-30 steps for much better quality. I need help optimizing the entire setup for production-quality results across all generation tools.

## Current Status

### ComfyUI (Image Generation)
**Installation:** C:\AI\ComfyUI
**Model:** Stable Diffusion XL Base 1.0 (6.5GB)
**Hardware:** RTX 4080 (12GB VRAM), NVIDIA CUDA 11.8, PyTorch 2.7.1+cu118
**API Endpoint:** http://127.0.0.1:8188

**Current Improved Settings (still needs optimization):**
- Resolution: 768x768
- Sampling Steps: 25-30
- Sampler: Euler with Karras scheduler
- CFG Scale: 8.0-8.5
- Model: sd_xl_base_1.0.safetensors

**Known Scripts:**
- RUN-IMPROVED-GENERATION-TEST.bat - Starts ComfyUI server
- RUN-IMPROVED-TESTS.py - Runs test generations

### Kokoro-FastAPI (Text-to-Speech)
**Installation:** C:\AI\Kokoro-FastAPI
**Status:** Not yet tested
**Need:** Full setup and testing guide

### Atmosphere-Studio-Tools
**Installation:** C:\AI\atmosphere-studio-tools
**Status:** Not yet tested
**Need:** Full setup and testing guide

## Task: Complete Optimization Guide

Please provide a COMPREHENSIVE setup and optimization guide that includes:

### 1. ComfyUI Image Generation Optimization
- **Quality Tuning:**
  - Optimal step counts for different image types (fast vs detailed)
  - Best CFG values for prompt adherence without over-saturation
  - Recommended sampler choices (euler, dpmpp, etc) and tradeoffs
  - Negative prompts that prevent artifacts (blurriness, distortion, etc)
  
- **Prompt Engineering:**
  - Detailed prompt templates for different subjects (portraits, landscapes, products, abstract, etc)
  - Common quality keywords and modifiers
  - What to avoid in prompts
  - Examples of good vs poor prompts
  
- **Performance Tuning:**
  - VRAM optimization for RTX 4080
  - Batch processing strategies
  - Memory management for multiple generations
  - Estimated generation times for different settings
  
- **Advanced Features:**
  - LoRA model usage for specific styles
  - Seed management for reproducibility
  - Multi-stage workflows (upscaling, refinement, etc)
  - Quality assessment metrics

### 2. Kokoro-FastAPI Setup & Optimization
- Complete installation verification steps
- Configuration for optimal audio quality
- Voice selection and customization
- Integration with ComfyUI workflows
- Performance optimization
- Testing procedures

### 3. Atmosphere-Studio-Tools Setup & Optimization
- Installation and dependency verification
- Capability overview
- Configuration for best results
- Integration with other tools
- Testing procedures

### 4. Complete Testing Suite
- Comprehensive test cases for each tool
- Quality assessment procedures
- Automated testing scripts
- Results verification and logging
- Benchmarking procedures

### 5. Integration & Automation
- How to chain tools together (image→speech→video, etc)
- Batch processing workflows
- Error handling and recovery
- Logging and monitoring setup

### 6. Python Scripts & Automation
Provide ready-to-use Python scripts for:
- Starting all services automatically
- Running comprehensive quality tests
- Logging results and metrics
- Generating comparison reports
- Batch processing workflows

### 7. Git & Version Control
- Recommended .gitignore setup for large models
- Best practices for tracking configs vs models
- Setup for CI/CD if desired
- Documentation structure

## Specific Requirements

1. **Quality First:** Every recommendation should prioritize output quality over speed
2. **Detailed Explanations:** Explain the "why" behind each setting, not just values
3. **Practical Examples:** Include concrete prompt examples, config snippets, etc
4. **Testing Validation:** How to actually verify that quality has improved
5. **Troubleshooting:** Common issues and solutions for each tool
6. **Future-Proofing:** Advice on handling model updates, new versions, etc

## Expected Output Format

Please provide:
1. Detailed configuration guide (markdown)
2. Optimized Python scripts (ready to run)
3. Quality assessment procedures
4. Troubleshooting guide
5. Example prompts library
6. Performance benchmarks
7. Best practices checklist

## Current Issues to Address

1. Previous generations were blurry/low quality - now fixed with more steps, but need to verify quality is actually good
2. Need to test ALL generation tools, not just ComfyUI
3. Need comprehensive quality verification procedures
4. Need batch processing workflows
5. Need error handling and recovery strategies

## Success Criteria

Output will be considered successful when:
- All three generation tools (ComfyUI, Kokoro, Atmosphere) are properly configured and tested
- Generated images/audio/3D models are visibly high quality (not blurry, not artifacts, proper colors, good detail)
- Comprehensive test suite is created and passing
- Setup can be automated with reliable scripts
- Complete documentation and prompts are provided
- Performance benchmarks show RTX 4080 is being effectively utilized

---

Please provide the complete optimization guide now. Start with ComfyUI, then Kokoro, then Atmosphere-Studio-Tools.
