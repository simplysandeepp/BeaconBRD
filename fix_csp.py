import re

path = r"C:\Users\preet\Downloads\beacon\beaconbrd\frontend\public\landing.html"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Remove any existing CSP meta tags first
content = re.sub(r'<meta[^>]*Content-Security-Policy[^>]*>', '', content, flags=re.IGNORECASE)

# Add CSP meta tag right after <head>
csp_meta = '<meta http-equiv="Content-Security-Policy" content="default-src \'self\' https://framerusercontent.com https://*.framerusercontent.com; script-src \'self\' \'unsafe-inline\' \'unsafe-eval\' https://framerusercontent.com https://*.framerusercontent.com; style-src \'self\' \'unsafe-inline\' https://framerusercontent.com https://*.framerusercontent.com; img-src \'self\' data: https://framerusercontent.com https://*.framerusercontent.com; font-src \'self\' https://framerusercontent.com https://*.framerusercontent.com https://fonts.gstatic.com; connect-src \'self\' https://framerusercontent.com https://*.framerusercontent.com; frame-src \'self\';">'

content = content.replace("<head>", "<head>\n" + csp_meta, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("CSP meta tag added to landing.html")
