$ErrorActionPreference = "Stop"
$f = "C:\Users\Miguel Martinez SSD\OneDrive - BROWSER TRAVEL SOLUTIONS S.A.S VIAJEMOS\Documentos\PROYECTOS\CARGUE MASIVO VJM Y MCR\mx_temp\m.zip"
$d = "C:\Users\Miguel Martinez SSD\OneDrive - BROWSER TRAVEL SOLUTIONS S.A.S VIAJEMOS\Documentos\PROYECTOS\CARGUE MASIVO VJM Y MCR\mx_temp\out"
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($f, $d)
Write-Host "EXTRACTION DONE"
Get-ChildItem $d -Recurse | ForEach-Object { Write-Host $_.FullName }
