# Template Automation Tool

Template Automation Tool is being rebuilt from zero as a Windows desktop automation tool for internal use.

The final goal is to let a user select a POTS PDF, an Excel template, a target sheet, and an output folder, then generate a completed Excel template by parsing the PDF, routing connection data to partner-specific automation, and writing the final result.

This repository is currently in the early foundation stage. The current code proves that the application entry point, service package, configuration files, parser, router, mappers, writer, adapter interface, CI checks, and local build-check script are in place.

## Current Status

Implemented so far:

```text
.github/workflows/ci.yml
.github/workflows/release.yml
build_exe.ps1
config/partners.yml
config/field_mapping.yml
src/services/template_generation_service.py
src/utils/app_paths.py
src/parsers/pots_doc_parser.py
src/routers/partner_router.py
src/mappers/tsh_mapper.py
src/mappers/vam_mapper.py
src/adapters/base_adapter.py
src/adapters/vam_adapter.py
scripts/check_vam_adapter.py
src/writers/template_writer.py
run_ui.py
requirements.txt
.gitignore
```

Not implemented yet:

```text
CustomTkinter UI
Real VAM data extraction
Other partner adapters
PyInstaller packaging
```

## Project Structure

```text
run_ui.py
    Minimal application entry point.

src/services/template_generation_service.py
    Minimal service class. Full workflow orchestration will be added later.

src/utils/app_paths.py
    Path helpers for source resources and per-user AppData files.

src/parsers/pots_doc_parser.py
    POTS text/PDF parser that returns structured fields for downstream steps.

src/routers/partner_router.py
    Builds upper/lower partner targets from parsed connection data.

src/mappers/vam_mapper.py
    Converts routed VAM targets into VAM adapter input fields.

src/mappers/tsh_mapper.py
    Converts routed TSH targets into TSH adapter input fields.

src/adapters/base_adapter.py
    Shared interface for partner website adapters.

src/adapters/vam_adapter.py
    VAM adapter interface with mapped-data validation, Playwright browser lifecycle management, basic configurator navigation, filter selection, connection selection, and CDS opening.

scripts/check_vam_adapter.py
    Smoke check for VAM adapter lifecycle, navigation, filter orchestration, connection selection orchestration, CDS opening orchestration, and grade matching.

src/writers/template_writer.py
    Excel writer that fills parser-derived fields into a selected sheet.

config/partners.yml
    Minimal partner configuration for VAM, TSH, JFE, and HT.

config/field_mapping.yml
    Minimal field alias configuration for OD, WT, and grade.

.github/workflows/ci.yml
    Minimal GitHub Actions CI workflow.

.github/workflows/release.yml
    Manual release workflow. Packaging and upload will be added later.

build_exe.ps1
    Local build-check script. PyInstaller packaging will be added later.
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

## Run Current Baseline

```powershell
python run_ui.py
```

Current expected output:

```text
Template Automation Tool baseline is ready.
```

## Local Checks

Run the same core checks used by the current CI:

```powershell
python -m compileall -q run_ui.py src
python -c "from src.services.template_generation_service import GenerationRequest, GenerationResult, TemplateGenerationService; from src.parsers.pots_doc_parser import PotsDocParser; from src.routers.partner_router import PartnerRouter; from src.mappers.tsh_mapper import TshMapper; from src.mappers.vam_mapper import VamMapper; from src.writers.template_writer import TemplateWriter; from src.utils.app_paths import resource_path, get_ui_settings_path; print(resource_path('config/partners.yml')); print(get_ui_settings_path()); print('ok')"
python -c "import yaml; from pathlib import Path; partners=yaml.safe_load(Path('config/partners.yml').read_text(encoding='utf-8')); fields=yaml.safe_load(Path('config/field_mapping.yml').read_text(encoding='utf-8')); assert set(partners['partners']) == {'VAM', 'TSH', 'JFE', 'HT'}; assert {'od', 'wt', 'grade'} <= set(fields['fields']); print('yaml ok')"
python -c "from src.parsers.pots_doc_parser import PotsDocParser; text='POTS Document number: 123 Rev: A\nCP Part Number ABC-001\nProduct Description Pup Joint 13CR(80) 5.5 17# VAM TOP BOX X 5.5 17# TSH WEDGE PIN OAL 120\nANSI/NACE MR0175/ISO 15156 (Yes/No) Yes\nQCP (Standard/Client Specific) Standard\n'; parsed=PotsDocParser().parse_text(text); assert parsed.part_number == 'ABC-001'; assert parsed.rev == 'A'; assert parsed.product_material_grade == '13CR(80)'; assert parsed.connections['upper'].family == 'VAM'; assert parsed.connections['lower'].family == 'TSH'; print('parser ok')"
python -c "from src.adapters.vam_adapter import VamAdapter; print('vam adapter import ok')"
python scripts/check_vam_adapter.py
```

Or run the local build-check script:

```powershell
.\build_exe.ps1 -SkipInstall
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
Parser behavior smoke check
Router behavior smoke check
VAM mapper behavior smoke check
VAM adapter CDS opening smoke check
TSH mapper behavior smoke check
Writer behavior smoke check
Service flow smoke check
```

## Runtime Paths

Bundled or source-controlled resources are resolved with `resource_path()`, for example:

```text
config/partners.yml
config/field_mapping.yml
```

Per-user runtime files belong under:

```text
%LOCALAPPDATA%\TemplateAutomationTool\
```

Planned user-specific files:

```text
%LOCALAPPDATA%\TemplateAutomationTool\config\ui_settings.json
%LOCALAPPDATA%\TemplateAutomationTool\logs\
```

## Git Rules

Commit source and configuration files:

```text
src/
config/
requirements.txt
run_ui.py
build_exe.ps1
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
