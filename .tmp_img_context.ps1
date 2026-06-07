$content = Get-Content 'frontend/public/landing.html' -Raw

# Find "text & graphic" which likely contains the hero image
Write-Output "=== text & graphic context ==="
$idx = $content.IndexOf('"text & graphic"')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 300)
    $end = [Math]::Min($content.Length, $idx + 5000)
    Write-Output $content.Substring($start, $end - $start)
}

Write-Output ""
Write-Output "=== Images framer-name context ==="
$idx = $content.IndexOf('"Images"')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 200)
    $end = [Math]::Min($content.Length, $idx + 3000)
    Write-Output $content.Substring($start, $end - $start)
}

Write-Output ""
Write-Output "=== IMG framer-name context ==="
$idx = $content.IndexOf('"IMG"')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 200)
    $end = [Math]::Min($content.Length, $idx + 1000)
    Write-Output $content.Substring($start, $end - $start)
}
