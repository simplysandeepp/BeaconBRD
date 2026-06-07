$content = Get-Content 'frontend/public/landing.html' -Raw

# Find all framer names
$nameMatches = [regex]::Matches($content, 'data-framer-name="([^"]+)"')
$names = $nameMatches | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
Write-Output "=== ALL framer names ==="
$names | ForEach-Object { Write-Output $_ }

Write-Output ""
Write-Output "=== bg-shape context ==="
$idx = $content.IndexOf('bg-shape')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 300)
    $end = [Math]::Min($content.Length, $idx + 500)
    Write-Output $content.Substring($start, $end - $start)
}

Write-Output ""
Write-Output "=== BlurGradient context ==="
$idx = $content.IndexOf('BlurGradient')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 300)
    $end = [Math]::Min($content.Length, $idx + 500)
    Write-Output $content.Substring($start, $end - $start)
}

# Find all class names with "blob" or "glow" or "circle"
Write-Output ""
Write-Output "=== blob/glow/circle class matches ==="
$classMatches = [regex]::Matches($content, 'class="([^"]*(?:blob|glow|circle|orb|blur)[^"]*)"')
foreach ($m in $classMatches) {
    Write-Output $m.Groups[1].Value
}
