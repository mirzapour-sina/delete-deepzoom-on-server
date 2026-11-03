---
name: testing
description: Skill for running tests and verifying the Remote DeepZoom Folder Cleaner application
---

# Testing

This skill covers running tests and verifying the Remote DeepZoom Folder Cleaner application.

## When to use

Use this skill when you need to:
- Run existing tests
- Add new tests for backend functionality
- Verify changes don't break existing behavior
- Test SSH connection and file operations

## Test structure

- `tests/test_backend.py` - Backend tests
- `test_run.py` - Test/run script for the application

## Running tests

Run backend tests:
```
python -m pytest tests/
```

Or run a specific test file:
```
python -m pytest tests/test_backend.py
```

Run the application test script:
```
python test_run.py
```

## What to test

When making changes, verify:
1. Backend signals and slots work correctly with QML
2. SSH connection handling (connect, disconnect, host key verification)
3. File operations (list, navigate, delete, rename, create directory)
4. File transfers (upload, download via SFTP)
5. Archive operations (compress, extract)
6. Settings persistence (connection history, UI preferences)
7. Hidden file visibility toggle
8. Multiple session management

## Files to reference

- `tests/test_backend.py` - Existing backend tests
- `test_run.py` - Application test script
- `deepzoom_cleaner/backend.py` - Backend to test
- `deepzoom_cleaner/settings.py` - Settings to test