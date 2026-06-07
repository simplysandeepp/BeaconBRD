$content = Get-Content 'frontend/src/app/(landing)/landing-body.json' -Raw -Encoding UTF8
$decoded = [System.Net.WebUtility]::HtmlDecode($content)

# Find "users" framer-name and extract surrounding context
$idx = $decoded.IndexOf('"users"')
if ($idx -ge 0) {
    $start = [Math]::Max(0, $idx - 200)
    $end = [Math]::Min($decoded.Length, $idx + 3000)
    Write-Output $decoded.Substring($start, $end - $start)
} else {
    Write-Output "'users' not found"
}
