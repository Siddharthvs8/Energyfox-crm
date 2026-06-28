"""Replace hardcoded localhost:8000 in public pages with getPublicApiBase()."""
import os, re

# For public pages (owner-portal, contact-sales), the URL is just http://localhost:8000
# We need a different helper for these

PUBLIC_SRC = r"c:\Users\user\.gemini\antigravity\scratch\crm-saas\frontend\src\app"

IMPORT_LINE = 'import { getPublicApiBase } from "@/lib/mock-data";'

# Pattern: "http://localhost:8000  ->  getPublicApiBase() + "
PATTERN = re.compile(r'"http://localhost:8000(/[^"]*)"')

count = 0
for folder in ['owner-portal', 'contact-sales']:
    folder_path = os.path.join(PUBLIC_SRC, folder)
    if not os.path.exists(folder_path):
        continue
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if not f.endswith(('.tsx', '.ts')):
                continue
            fp = os.path.join(root, f)
            with open(fp, 'r', encoding='utf-8') as fh:
                content = fh.read()
            
            if 'localhost:8000' not in content:
                continue
            
            new_content = content
            
            # Add import if missing
            if 'getPublicApiBase' not in new_content:
                if '"use client"' in new_content:
                    new_content = new_content.replace(
                        '"use client";',
                        f'"use client";\n{IMPORT_LINE}',
                        1
                    )
                else:
                    new_content = IMPORT_LINE + '\n' + new_content
            
            # Replace: "http://localhost:8000/path" -> `${getPublicApiBase()}/path`
            new_content = PATTERN.sub(r'`${getPublicApiBase()}\1`', new_content)
            
            if new_content != content:
                with open(fp, 'w', encoding='utf-8') as fh:
                    fh.write(new_content)
                count += 1
                print(f"Updated: {fp}")

print(f"\nTotal files updated: {count}")
