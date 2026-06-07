$content = Get-Content 'frontend/public/landing.html' -Raw
# Find all framer-background-image-wrapper instances
$pattern = 'data-framer-background-image-wrapper'
$idx = 0
$count = 0
while (($idx = $content.IndexOf($pattern, $idx)) -ge 0) {
    $count++
    $start = [Math]::Max(0, $idx - 100)
    $end = [Math]::Min($content.Length, $idx + 400)
    Write-Output "=== Image #$count at offset $idx ==="
    Write-Output $content.Substring($start, $end - $start)
    Write-Output ""
    $idx += $pattern.Length
}
Write-Output "Total images found: $count"
