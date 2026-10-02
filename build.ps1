param(
    [switch]$SkipSmokeTest,
    [switch]$RequireInstaller,
    [string]$IsccPath
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw 'Bitte zuerst mit py -3.12 -m venv .venv die virtuelle Umgebung erstellen.'
}

function Find-InnoCompiler {
    if ($IsccPath) {
        if (-not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
            throw "ISCC.exe wurde unter dem angegebenen Pfad nicht gefunden: $IsccPath"
        }
        return (Resolve-Path -LiteralPath $IsccPath).Path
    }
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $roots = @(${env:ProgramFiles(x86)}, $env:ProgramFiles)
    if ($env:LOCALAPPDATA) { $roots += (Join-Path $env:LOCALAPPDATA 'Programs') }
    foreach ($root in $roots) {
        if (-not $root) { continue }
        foreach ($name in @('Inno Setup 7', 'Inno Setup 6')) {
            $candidate = Join-Path $root "$name\ISCC.exe"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
    }
    return $null
}

Push-Location -LiteralPath $projectRoot
try {
    $version = (& $pythonExe -c 'from core.version import VERSION; print(VERSION)').Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
        throw 'Die zentrale Version in core/version.py ist ungültig.'
    }
    & $pythonExe tools\make_icons.py
    if ($LASTEXITCODE -ne 0) { throw 'Logo und Icons konnten nicht erzeugt werden.' }
    $pythonBaseDir = (& $pythonExe -c 'import sys; print(sys.base_prefix)').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Der Python-Installationsordner konnte nicht ermittelt werden.' }
    $originalBuildPath = $env:PATH
    $buildSearchDirs = @((Split-Path -Parent $pythonExe), $pythonBaseDir,
        (Join-Path $pythonBaseDir 'DLLs'), (Join-Path $env:WINDIR 'System32'), $env:WINDIR)
    try {
        # Fremde Programme im lokalen PATH dürfen keine DLLs in den Build einschleusen.
        $env:PATH = $buildSearchDirs -join [System.IO.Path]::PathSeparator
        & $pythonExe -m PyInstaller --noconfirm --clean EmulatorHub.spec
        if ($LASTEXITCODE -ne 0) { throw 'Der Ordner-Build ist fehlgeschlagen.' }
    } finally {
        $env:PATH = $originalBuildPath
    }
    $programDir = Join-Path $projectRoot 'dist\EmulatorHub'
    $programExe = Join-Path $programDir 'EmulatorHub.exe'
    if (-not (Test-Path -LiteralPath $programExe -PathType Leaf)) {
        throw 'Die Startdatei des Ordner-Builds wurde nicht gefunden.'
    }
    # Hinweise neben der EXE lassen sich auch ohne Programmstart lesen.
    foreach ($notice in @('LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $notice) -Destination $programDir -Force
    }
    # Einrichtung, Quellbezug und relative Links der Lizenzhinweise mitgeben.
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs') -Destination $programDir -Recurse -Force
    if (-not $SkipSmokeTest) {
        $smokeData = Join-Path $projectRoot 'test-artifacts\release-exe-smoke-data'
        $smokeImage = Join-Path $projectRoot 'test-artifacts\release-exe-smoke.png'
        if (Test-Path -LiteralPath $smokeImage -PathType Leaf) {
            Remove-Item -LiteralPath $smokeImage
        }
        & $programExe --smoke-test --check-integrations --data-dir $smokeData --screenshot $smokeImage | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $smokeImage -PathType Leaf)) {
            throw 'Der Starttest des Ordner-Builds ist fehlgeschlagen.'
        }
    }

    $outputDir = Join-Path $projectRoot 'Output'
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    # Eigener neuer Arbeitsordner: keine bestehenden portablen Nutzerdaten übernehmen.
    $portableStage = Join-Path $projectRoot ('build\portable-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $portableStage -Force | Out-Null
    Copy-Item -LiteralPath $programDir -Destination $portableStage -Recurse
    $portableProgram = Join-Path $portableStage 'EmulatorHub'
    Set-Content -LiteralPath (Join-Path $portableProgram 'portable.flag') -Value '' -Encoding ASCII
    $portableZip = Join-Path $outputDir "EmulatorHub-$version-portable.zip"
    Compress-Archive -LiteralPath $portableProgram -DestinationPath $portableZip -CompressionLevel Optimal -Force
    $artifacts = @($portableZip)
    Write-Output "Portable ZIP: $portableZip"

    $compiler = Find-InnoCompiler
    if ($compiler) {
        & $compiler "/DMyAppVersion=$version" (Join-Path $projectRoot 'installer\EmulatorHub.iss')
        if ($LASTEXITCODE -ne 0) { throw 'Der Inno-Setup-Build ist fehlgeschlagen.' }
        $setupExe = Join-Path $outputDir 'EmulatorHub-Setup.exe'
        if (-not (Test-Path -LiteralPath $setupExe -PathType Leaf)) {
            throw 'Inno Setup hat die erwartete Setup-Datei nicht erstellt.'
        }
        $artifacts += $setupExe
        Write-Output "Installer: $setupExe"
    } else {
        Write-Warning 'Inno Setup (ISCC.exe) ist nicht installiert. Der Installer wurde nicht gebaut; die portable ZIP steht trotzdem bereit. Inno Setup installieren oder -IsccPath angeben.'
    }
    $checksumLines = foreach ($artifact in $artifacts) {
        $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $([System.IO.Path]::GetFileName($artifact))"
    }
    $checksumFile = Join-Path $outputDir 'SHA256SUMS.txt'
    Set-Content -LiteralPath $checksumFile -Value $checksumLines -Encoding ASCII
    Write-Output "Prüfsummen: $checksumFile"
    if ($RequireInstaller -and -not $compiler) {
        throw 'Für diesen Release-Build ist ein Installer erforderlich. ISCC.exe fehlt; die ZIP wurde gebaut.'
    }
    Write-Output "Fertig: Emulator Hub $version (dist\EmulatorHub\EmulatorHub.exe)"
} finally {
    Pop-Location
}
