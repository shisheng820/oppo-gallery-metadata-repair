# Repository Guidelines

## Project Structure & Module Organization

- `repair.py` implements copy-only JPEG metadata editing and batch reports.
- `oplus_metadata.py` inspects OnePlus compound JPEGs and builds experimental motion-photo containers.
- `run.ps1` provides the Windows batch entry point; `profiles/` contains reusable JSON field presets.
- `scripts/video_lab.py` creates experimental MP4 metadata variants; it additionally requires FFmpeg/ffprobe.
- `tests/` holds unit and integration tests. `scripts/audit_public.py` checks tracked files for privacy risks.
- `docs/` contains the tutorial, format research, validation evidence, and media attribution. Approved public screenshots belong in `docs/images/`.
- Keep personal inputs, extracted media, device evidence, and scratch scripts in ignored `.private/`.

## Build, Test, and Development Commands

Use Python 3.10+ and install ExifTool separately on `PATH`. There is no compilation step or Python runtime dependency.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
exiftool -ver
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/audit_public.py
```

Pillow supports generated test images. Preview a batch without writing:

```powershell
python repair.py 'D:\Photos' --output 'D:\Photos-New' --model 'My Camera'
python oplus_metadata.py inspect 'D:\Photos\sample.jpg'
```

Add `--apply` only when ready to create a new output directory.

## Coding Style & Naming Conventions

Follow existing Python style: four-space indentation, `snake_case` functions and variables, and uppercase constants. Use `pathlib`, explicit UTF-8 text handling, and argument lists for subprocesses. Preserve established CLI names and JSON keys. No formatter or linter is currently configured; run `git diff --check` before submitting.

## Testing Guidelines

Use standard-library `unittest`; name files `test_*.py` and methods `test_*`. Integration tests require ExifTool and generate temporary images rather than reading personal photos. Cover source preservation, metadata readback, invalid inputs, and container boundaries when changing those behaviors. No numerical coverage threshold is configured. Automated structure checks do not establish gallery recognition or playback; document device observations separately.

## Commit & Pull Request Guidelines

History uses concise imperative subjects, such as “Fix ColorOS motion-photo XMP scope and verify playback.” Follow that style. PRs should explain the problem, resulting behavior, validation commands, and compatibility limits; link related issues when available. Include reviewed screenshots for gallery behavior changes and update relevant documentation.

## Data Safety & Publication

Preserve originals and keep compound-file guards intact. Never publish personal GPS, filenames, embedded previews, videos, audio, credentials, or device logs. The audit reads Git-tracked files: stage intended assets before running it and manually review screenshots and diffs. Distinguish synthetic metadata, observed behavior, and unverified hypotheses.

## Local Operator Handoff

For authorized work on the owner's device or publishing account, read `.private/AGENTS.md` if present. It holds local connection details, reusable automation paths, privacy-review evidence, and known device behavior. Keep that file and its evidence ignored; never copy its contents into this public guide. A tracked `AGENTS.md` must contain only contributor-safe instructions. Removing a file from tracking does not remove earlier committed versions.
