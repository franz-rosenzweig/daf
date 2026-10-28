# Daf.ico, from Daf's own icon (design/icon/final, Tree D): every size Windows asks for, each a PNG
# inside the .ico. Run by windows\build.ps1 and the Windows workflow; git leaves the result out.
#
#   powershell -File windows\tools\make-icon.ps1 [-Source design\icon\final\web\icon-512.png] [-Out windows\Daf\Assets\Daf.ico]
param(
    [string]$Source = "design\icon\final\web\icon-512.png",
    [string]$Out = "windows\Daf\Assets\Daf.ico"
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$image = [System.Drawing.Image]::FromFile((Resolve-Path $Source))
$sizes = 16, 20, 24, 32, 40, 48, 64, 128, 256
$pngs = foreach ($size in $sizes) {
    $bitmap = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bitmap)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $g.DrawImage($image, 0, 0, $size, $size)
    $g.Dispose()
    $stream = New-Object System.IO.MemoryStream
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    , $stream.ToArray()
}
$image.Dispose()

New-Item -ItemType Directory -Force (Split-Path $Out) | Out-Null
$file = [System.IO.File]::Create((Join-Path (Resolve-Path (Split-Path $Out)) (Split-Path $Out -Leaf)))
$w = New-Object System.IO.BinaryWriter $file
# the header, one entry per size, then the pictures
$w.Write([uint16]0); $w.Write([uint16]1); $w.Write([uint16]$sizes.Count)
$offset = 6 + 16 * $sizes.Count
for ($i = 0; $i -lt $sizes.Count; $i++) {
    $side = if ($sizes[$i] -ge 256) { 0 } else { $sizes[$i] }      # 0 means 256
    $w.Write([byte]$side); $w.Write([byte]$side); $w.Write([byte]0); $w.Write([byte]0)
    $w.Write([uint16]1); $w.Write([uint16]32)
    $w.Write([uint32]$pngs[$i].Length); $w.Write([uint32]$offset)
    $offset += $pngs[$i].Length
}
foreach ($png in $pngs) { $w.Write([byte[]]$png) }
$w.Close()
"made $Out"
