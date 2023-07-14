# dotfiles for Windows 10
## Installation
### Install by using git

```ps1
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Force
git clone https://github.com/4n86rakam1/dotfiles ~\.dotfiles
cd ~\.dotfiles\win10
& .\bootstrap.ps1
```

### Install without git

```ps1
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Force
Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/4n86rakam1/dotfiles/master/win10/bootstrap.ps1'))
```
