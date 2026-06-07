$content = Get-Content 'frontend/public/landing.html' -Raw

# Find "bg shape" context
Write-Output "=== bg shape full context ==="
$idx = $content.IndexOf('"bg shape"')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 500)
    $end = [Math]::Min($content.Length, $idx + 1000)
    Write-Output $content.Substring($start, $end - $start)
}

Write-Output ""
Write-Output "=== hero context ==="
$idx = $content.IndexOf('"hero"')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 300)
    $end = [Math]::Min($content.Length, $idx + 2000)
    Write-Output $content.Substring($start, $end - $start)
}

Write-Output ""
Write-Output "=== Images context ==="
$idx = $content.IndexOf('"Images"')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 300)
    $end = [Math]::Min($content.Length, $idx + 2000)
    Write-Output $content.Substring($start, $end - $start)
}
