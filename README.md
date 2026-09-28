# 506th Arma 3 Mod Sync v5

This repository builds the Windows member updater and can publish it directly through GitHub Releases.

## Local build

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\Build-Release.ps1"
```

Output:

```text
release\506th-Arma3-Mod-Sync-v5.0.0-Windows-x64.zip
release\SHA256SUMS.txt
```

The updater is a PyInstaller `--onedir` build. End users must extract the ZIP and keep the EXE and `_internal` directory together.

## Automatic GitHub build

Push updater source changes to `main`.

GitHub Actions runs **Build Windows Updater** and produces a downloadable workflow artifact.

## Publish to end users

Create and push a release tag:

```powershell
git tag v5.0.0
git push origin v5.0.0
```

The **Publish GitHub Release** workflow builds the package and automatically creates a GitHub Release containing the Windows ZIP and SHA-256 checksum.

## R2

The updater uses:

```text
https://pub-c5632053ba844beca4069371167a6fff.r2.dev/manifest.json
```

No R2 API credentials are included in the updater.

## Exact sync

The user first previews all DOWNLOAD and DELETE operations. After confirmation, repository-managed top-level paths are mirrored to the R2 manifest.

## Antivirus

This uses `--onedir`, not PyInstaller `--onefile`. An unsigned new executable can still receive reputation or heuristic warnings. Do not instruct users to disable antivirus; code-signing is the appropriate long-term solution.
