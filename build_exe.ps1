param(
    [switch]$SkipInstall,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-PythonExecutable {
    if ($Python) {
        return $Python
    }

    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }

    return "python"
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $script:PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($Arguments -join ' ')"
    }
}

$script:PythonExe = Resolve-PythonExecutable

Push-Location $PSScriptRoot
try {
    Write-Host "Using Python: $script:PythonExe"

    if (-not $SkipInstall) {
        Write-Host "Installing dependencies..."
        Invoke-Python @("-m", "pip", "install", "-r", "requirements.txt")
    }

    Write-Host "Compiling Python files..."
    Invoke-Python @("-m", "compileall", "-q", "run_ui.py", "src")

    Write-Host "Checking core imports..."
    Invoke-Python @("-c", "from src.services.template_generation_service import TemplateGenerationService; print('ok')")

    Write-Host "Checking YAML configuration..."
    $yamlCheck = "import yaml; from pathlib import Path; partners=yaml.safe_load(Path('config/partners.yml').read_text(encoding='utf-8')); fields=yaml.safe_load(Path('config/field_mapping.yml').read_text(encoding='utf-8')); assert set(partners['partners']) == {'VAM', 'TSH', 'JFE', 'HT'}; assert {'od', 'wt', 'grade'} <= set(fields['fields']); print('yaml ok')"
    Invoke-Python @("-c", $yamlCheck)

    Write-Host "Build checks passed."
    Write-Host "PyInstaller packaging will be added after the application workflow is ready."
}
finally {
    Pop-Location
}
