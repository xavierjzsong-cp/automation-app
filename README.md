# Template Automation Tool

Template Automation Tool is being rebuilt from zero as a Windows desktop automation tool for internal use.

The final goal is to let a user select a POTS PDF, an Excel template, a target sheet, and an output folder, then generate a completed Excel template by parsing the PDF, routing connection data to partner-specific automation, and writing the final result.

This repository is currently in the early scaffold stage. The current code proves that the application entry point, service package, minimal configuration files, and CI checks are in place.

## Current Status

Implemented so far:

```text
.github/workflows/ci.yml
config/partners.yml
config/field_mapping.yml
src/services/template_generation_service.py
run_ui.py
requirements.txt
.gitignore
```

Not implemented yet:

```text
CustomTkinter UI
POTS PDF parser
Partner router
Partner mappers
Playwright partner adapters
Excel template writer
PyInstaller packaging
Release workflow
```

## Project Structure

```text
run_ui.py
    Minimal application entry point.

src/services/template_generation_service.py
    Minimal service class. Full workflow orchestration will be added later.

config/partners.yml
    Minimal partner configuration for VAM, TSH, JFE, and HT.

config/field_mapping.yml
    Minimal field alias configuration for OD, WT, and grade.

.github/workflows/ci.yml
    Minimal GitHub Actions CI workflow.
```

## Development Setup

Create and activate a local virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run Current Scaffold

```powershell
python run_ui.py
```

Current expected output:

```text
Template Automation Tool scaffold is ready.
```

## Local Checks

Run the same core checks used by the current CI:

```powershell
python -m compileall -q run_ui.py src
python -c "from src.services.template_generation_service import TemplateGenerationService; print('ok')"
python -c "import yaml; from pathlib import Path; partners=yaml.safe_load(Path('config/partners.yml').read_text(encoding='utf-8')); fields=yaml.safe_load(Path('config/field_mapping.yml').read_text(encoding='utf-8')); assert set(partners['partners']) == {'VAM', 'TSH', 'JFE', 'HT'}; assert {'od', 'wt', 'grade'} <= set(fields['fields']); print('yaml ok')"
```

## CI

GitHub Actions runs the minimal CI workflow on:

```text
push to main
pull request
manual workflow_dispatch
```

The workflow currently checks:

```text
Python compilation
Core service import
Minimal YAML configuration loading
```

## Git Rules

Commit source and configuration files:

```text
src/
config/
requirements.txt
run_ui.py
.github/workflows/
README.md
.gitignore
```

Do not commit local runtime files, virtual environments, logs, samples, generated outputs, or build artifacts:

```text
.venv/
py314/
build/
dist/
logs/
input_doc/
input_docs/
output_doc/
output_docs/
template/
templates/
config/ui_settings.json
```
