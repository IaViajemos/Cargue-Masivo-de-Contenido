$ErrorActionPreference = "Stop"
$zipPath = "C:\Users\Miguel Martinez SSD\OneDrive - BROWSER TRAVEL SOLUTIONS S.A.S VIAJEMOS\Documentos\PROYECTOS\CARGUE MASIVO VJM Y MCR\mx_temp\m.zip"
$outPath = "C:\Users\Miguel Martinez SSD\OneDrive - BROWSER TRAVEL SOLUTIONS S.A.S VIAJEMOS\Documentos\PROYECTOS\CARGUE MASIVO VJM Y MCR\mx_temp\out"
if (Test-Path $outPath) { Remove-Item $outPath -Recurse -Force }
New-Item -ItemType Directory -Path $outPath -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $outPath)
Write-Host "DONE"
