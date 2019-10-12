Push-Location $PSScriptRoot

Set-ExecutionPolicy Bypass -Scope Process -Force
Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))

if (-Not (Get-Command git -ErrorAction SilentlyContinue)) {
    choco install -y git
    $Env:ChocolateyInstall = Convert-Path "$((Get-Command choco).path)\..\.."
    Import-Module "$Env:ChocolateyInstall\helpers\chocolateyProfile.psm1"
    refreshenv
}

if (-Not (git rev-parse --git-dir 2> $NULL)) {
    git clone https://github.com/maya2250/dotfiles $Env:HOMEPATH\.dotfiles
    Set-Location $Env:HOMEPATH\.dotfiles\win10
    git remote set-url origin git@github.com:maya2250/dotfiles.git
}

choco install --yes --no-progress (Get-content -Path .\choco_packages.txt)
$Env:ChocolateyInstall = Convert-Path "$((Get-Command choco).path)\..\.."
Import-Module "$Env:ChocolateyInstall\helpers\chocolateyProfile.psm1"
refreshenv

ForEach ($extension in (Get-Content -Path ..\vscode\extensions.txt)) {
    code --install-extension $extension --force
}
New-Item -Force -ItemType SymbolicLink -Path $Env:APPDATA\Code\User\settings.json -Target ..\vscode\settings.json

New-Item -Force -ItemType SymbolicLink -Path $profile -Target .\profile.ps1
New-Item -Force -ItemType SymbolicLink -Path $Env:APPDATA\ConEmu.xml -Target .\ConEmu.xml
reg import .\my.reg

Pop-Location
