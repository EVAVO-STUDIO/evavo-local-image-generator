# Contributing to EVAVO Local Image Generator

Thank you for your interest in contributing! This document outlines guidelines for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Focus on improving the project
- Report issues constructively
- Help others learn and grow

## How to Contribute

### Reporting Issues

1. Check if the issue already exists
2. Provide clear description and reproduction steps
3. Include logs from `claude_control.log`
4. Specify your environment (OS, Python version, GPU)

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes with clear commit messages
4. Add tests for new functionality
5. Run tests: `pytest test_autonomous.py -v`
6. Submit a pull request

### Coding Standards

- Follow PEP 8 style guide
- Use type hints for new functions
- Write docstrings for all functions
- Keep methods focused and single-purpose
- Comment complex logic

Example:

```python
def generate_image_series(
    self,
    subjects: List[str],
    quality: str = "high"
) -> List[Dict[str, Any]]:
    """
    Generate multiple images in sequence.
    
    Args:
        subjects: List of image descriptions
        quality: Quality level for all images
        
    Returns:
        List of generation results
        
    Raises:
        ValueError: If subjects list is empty
    """
```

### Testing

All new features must include tests:

```bash
# Run all tests
pytest test_autonomous.py -v

# Run with coverage
pytest test_autonomous.py --cov=. --cov-report=html

# Run specific test
pytest test_autonomous.py::TestClaudeController::test_generate_image_simple -v
```

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add retry logic for failed generations
fix: handle server timeout more gracefully
docs: update README with performance benchmarks
test: add tests for error recovery
refactor: simplify image generation code
```

### Pull Request Process

1. Update README.md with any new features
2. Update CHANGELOG in documentation
3. Ensure all tests pass locally
4. Request review from maintainers
5. Address feedback and iterate
6. Merge when approved

## Development Setup

```bash
# Clone repository
git clone https://github.com/your-fork/evavo-local-image-generator.git
cd evavo-local-image-generator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-cov black flake8 mypy

# Verify setup
python -c "from claude_control import ClaudeController; print('✓ Ready')"
```

## Testing Checklist

Before submitting:

- [ ] Code follows PEP 8 style
- [ ] All tests pass locally
- [ ] New tests added for features
- [ ] Docstrings updated
- [ ] No new warnings from linters
- [ ] Manual testing completed
- [ ] Logs verified for clarity

## Performance Considerations

When optimizing:

1. Profile before and after changes
2. Document performance impact
3. Consider VRAM usage
4. Test with different GPU models
5. Verify error handling doesn't degrade performance

## Documentation

Update documentation for:

- New features
- Configuration changes
- API modifications
- Error handling
- Performance improvements

## Asking Questions

- Open a discussion issue
- Provide context and examples
- Include relevant logs
- Specify your use case

## License

By contributing, you agree your code will be licensed under the project's license.

---

Thank you for making EVAVO Local Image Generator better!
