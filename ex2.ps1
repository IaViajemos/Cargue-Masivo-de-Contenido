$ErrorActionPreference = "Stop"
try {
    $zipPath = 'C:\Users\Miguel Martinez SSD\OneDrive - BROWSER TRAVEL SOLUTIONS S.A.S VIAJEMOS\Documentos\PROYECTOS\CARGUE MASIVO VJM Y MCR\mx_temp\m.zip'
    $outPath = 'C:\Users\Miguel Martinez SSD\OneDrive - BROWSER TRAVEL SOLUTIONS S.A.S VIAJEMOS\Documentos\PROYECTOS\CARGUE MASIVO VJM Y MCR\mx_temp\out2'

    Write-Host "ZIP exists: $(Test-Path $zipPath)"
    Write-Host "ZIP size: $((Get-Item $zipPath).Length)"

    if (Test-Path $outPath) { Remove-Item $outPath -Recurse -Force }
    New-Item -ItemType Directory -Path $outPath -Force | Out-Null

    Expand-Archive -Path $zipPath -DestinationPath $outPath -Force

    Write-Host "Files extracted:"
    Get-ChildItem $outPath -Recurse | ForEach-Object { Write-Host $_.FullName }
    Write-Host "ALLDONE"
} catch {
    Write-Host "ERROR: $_"
}
