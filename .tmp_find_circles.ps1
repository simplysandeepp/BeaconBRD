$content = Get-Content 'frontend/public/landing.html' -Raw

# 1. Find elements with "bg-shape", "blob", "glow", "circle", "orb" in class names or data-framer-name
$patterns = @('bg-shape','bg_shape','blob','glow','circle','orb','blur-gradient')
foreach ($p in $patterns) {
    $matches = [regex]::Matches($content, "class=""[^""]*$p[^""]*""|data-framer-name=""[^""]*$p[^""]*""|id=""[^""]*$p[^""]*""")
    if ($matches.Count -gt 0) {
        Write-=== "PATTERN: $p" ===
        foreach ($m in $matches) {
            Write-Output $m.Value
        }
        Write-Output ""
    }
}

# 2. Find parent containers of the large hero image (Image #13/7 - the 1312x912 one)
# Look for framer-name containing "hero", "image", "graphic"
$nameMatches = [regex]::Matches($content, 'data-framer-name="([^"]+)"')
Write-Output "=== ALL framer names ==="
$nameMatches | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique | ForEach-Object { Write-Output $_ }
