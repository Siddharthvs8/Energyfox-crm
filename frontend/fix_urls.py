"""Bulk replace hardcoded localhost:8000 URLs with getApiBase() helper."""
import os, re

SRC = r"c:\Users\user\.gemini\antigravity\scratch\crm-saas\frontend\src\app\app"
IMPORT_LINE = 'import { getApiBase } from "@/lib/mock-data";'

# Pattern: `http://${domain}.localhost:8000  ->  `${getApiBase(domain)}
TENANT_PATTERN = re.compile(r'`http://\$\{domain\}\.localhost:8000')
TENANT_REPLACEMENT = '`${getApiBase(domain)}'

# Pattern: http://${domain}.localhost:8000  (without backtick prefix, inside template)
TENANT_PATTERN2 = re.compile(r'http://\$\{domain\}\.localhost:8000')
TENANT_REPLACEMENT2 = '${getApiBase(domain)}'

count = 0
for root, dirs, files in os.walk(SRC):
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
        if 'getApiBase' not in new_content:
            # Insert after "use client"; or at top
            if '"use client"' in new_content:
                new_content = new_content.replace(
                    '"use client";',
                    f'"use client";\n{IMPORT_LINE}',
                    1
                )
            else:
                new_content = IMPORT_LINE + '\n' + new_content
        
        # Replace URLs
        new_content = TENANT_PATTERN.sub(TENANT_REPLACEMENT, new_content)
        new_content = TENANT_PATTERN2.sub(TENANT_REPLACEMENT2, new_content)
        
        if new_content != content:
            with open(fp, 'w', encoding='utf-8') as fh:
                fh.write(new_content)
            count += 1
            print(f"Updated: {fp}")

print(f"\nTotal files updated: {count}")
