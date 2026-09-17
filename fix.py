import os
for root, _, files in os.walk('.'):
    for f in files:
        if f.endswith('.py') and f != 'fix.py':
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            if '\\\\\\\"' in content or '\\\"' in content:
                content = content.replace('\\\\\\\"', '\"').replace('\\\"', '\"')
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(content)
                print('Fixed ' + path)
