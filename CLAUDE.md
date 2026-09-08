# Claude operating notes

## EVAVO Local Image Generator

This is the production-grade autonomous AI image and video generation system integrating with:
- **evavo-local-storage** for BeeStation access (`bee://primary/EVAVO/ImageGeneration`)
- **evavo-local-compute** for Windows workstation execution (digest-bound tasks)
- **evavo-storage** for immutable milestone handoff
- **ComfyUI** local inference engine on http://127.0.0.1:8188

## Integration Points

### BeeStation Access
Use `bee://` URIs for all BeeStation storage:
- Generation outputs: `bee://primary/EVAVO/ImageGeneration/outputs`
- Model cache: `bee://primary/EVAVO/AI/Models`
- Project data: `bee://primary/Projects/<project-name>`

**Never** assume hosted Claude can see Windows paths. Always use evavo-local-storage APIs and bee:// URIs.

### Local Execution
Register generation tasks through evavo-local-compute's `storage.compute_repository_task_*` actions:
- Task manifest: `evavo-repository-task-manifest.json` (digest-bound)
- Supported runtimes: Python script/module, PowerShell, Git Bash
- No inline interpreter text; scripts checked into this repository only
- Network access requires explicit FullHostShell policy review

### ComfyUI Integration  
- Endpoint: http://127.0.0.1:8188 (configurable via env)
- Workflows: Stored in `workflows/` directory
- Generated images: Immediate transfer to `bee://primary/EVAVO/ImageGeneration/outputs`
- No intermediate staging on C: drive; use evavo-local-storage transfer APIs

### evavo-storage Handoff
For completed milestones:
- Export immutable versioned snapshots via `storage.transfer_to_beestation`
- Retain generation logs and metadata as durable records
- Use exact-SHA verification for all transferred content

## File Organization

```
evavo-local-image-generator/
├── .mcp.json                            # MCP server configuration
├── evavo-repository-task-manifest.json  # Digest-bound tasks
├── CLAUDE.md                            # This file
├── CLAUDE-CONTROL.md                    # API documentation  
├── scripts/
│   ├── generate.py                      # Main generation entry point
│   ├── workflows.py                     # ComfyUI workflow management
│   └── storage.py                       # BeeStation transfer layer
├── workflows/
│   ├── image_generation.json            # ComfyUI workflows
│   └── video_generation.json
├── requirements.txt                     # Python dependencies
└── tests/
    └── test_generation.py               # Integration tests
```

## Operating Guidelines

1. **No Interim Windows Paths**: All storage uses `bee://` URIs via evavo-local-storage
2. **Digest-Bound Tasks Only**: Submit work through evavo-local-compute task API with digest validation
3. **Immutable Milestones**: Completed generations transferred to evavo-storage as immutable versions
4. **Error Handling**: Failed jobs logged to `bee://primary/EVAVO/ImageGeneration/logs`
5. **Model Provisioning**: Models hydrated via evavo-model-lab, never bulk-downloaded by this service

## Testing

Run locally on Windows with proper environment setup:
```powershell
# Ensure evavo-local-storage is initialized
.\scripts\ensure-local-ai-platform.ps1 -GitReposPath C:\GitRepos

# Run integration tests
python -m pytest tests/

# Submit a generation task through evavo-local-compute
evavo-local-storage compute-repository-task-submit \
  --repository evavo-local-image-generator \
  --task generate-image-batch \
  --arguments '{"project": "demo", "count": 5}'
```

## Security & Audit

- All task execution is digest-bound and logged to evavo-local-compute queue
- BeeStation access audited through evavo-local-storage provider audit
- Model weights verified against immutable checksums
- No credentials stored in repository; use evavo-local-compute auth fabric
