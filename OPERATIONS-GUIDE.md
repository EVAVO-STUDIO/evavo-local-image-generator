# EVAVO Local Image Generator - Operations Guide

## Quick Start (3 Steps)

1. **Start Services**
   ```batch
   START-EVAVO-SERVICES.bat
   ```

2. **Generate Images**
   ```bash
   python generate-batch.py --examples
   ```

3. **Monitor Status**
   ```bash
   python monitor-evavo.py --continuous
   ```

## Command Reference

### Batch Generation
Queue multiple images at once:
```bash
python generate-batch.py --prompts "sunset landscape" "cyberpunk city" "underwater scene"
python generate-batch.py --examples              # Use built-in examples
python generate-batch.py --project my_project    # Specify project name
```

### System Monitoring
Check health or monitor continuously:
```bash
python monitor-evavo.py                    # Single health check
python monitor-evavo.py --continuous       # Continuous monitoring every 10s
python monitor-evavo.py --continuous --interval 5  # Check every 5s
```

### Task Tracking
View task history and statistics:
```bash
python task-tracker.py list                # Show last 20 tasks
python task-tracker.py list --limit 50     # Show last 50 tasks
python task-tracker.py stats               # Display statistics
python task-tracker.py clear               # Clear history
```

## Workflow Examples

### Example 1: Quick Batch Generation
```bash
# Start services
START-EVAVO-SERVICES.bat

# Queue 5 images
python generate-batch.py --examples

# Check results
python task-tracker.py stats
```

### Example 2: Continuous Monitoring During Generation
```bash
# Terminal 1: Start services
START-EVAVO-SERVICES.bat

# Terminal 2: Monitor system
python monitor-evavo.py --continuous

# Terminal 3: Queue generations
python generate-batch.py --prompts "landscape" "portrait" "abstract"
```

### Example 3: Production Batch Processing
```bash
# Generate large batch with custom prompts
python generate-batch.py --prompts \
  "professional headshot" \
  "product photography" \
  "architectural render" \
  --project production_batch

# Track task completion
python task-tracker.py list --limit 100

# Review statistics
python task-tracker.py stats
```

## Troubleshooting

### ComfyUI Not Responding
```bash
# Check status
python monitor-evavo.py

# Restart services
taskkill /F /IM python.exe
START-EVAVO-SERVICES.bat
```

### Tasks Not Queuing
- Verify ComfyUI is running: `curl http://127.0.0.1:8188/system`
- Check task-tracker for errors: `python task-tracker.py list`
- Review EVAVO wrapper output for detailed errors

### Port 8188 Already in Use
```batch
# Kill existing process
netstat -ano | findstr :8188
taskkill /PID <PID> /F

# Then restart
START-EVAVO-SERVICES.bat
```

## Performance Tips

1. **Batch Size**: Queue 5-10 images per batch for optimal throughput
2. **Monitoring**: Use `--interval 30` for production to reduce overhead
3. **Storage**: Check bee:// storage paths regularly to manage space
4. **Concurrent**: Run monitor and tracker in separate terminals

## Best Practices

- Start services before generating
- Monitor continuously during critical batches
- Track history for audit and statistics
- Clear old task history periodically
- Use project names to organize batches
