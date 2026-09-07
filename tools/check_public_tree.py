"""Check staged source before public publication; never print matched secrets."""
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
patterns=[
    rb'(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_\-]{20,}',
    rb'AKIA[0-9A-Z]{16}',
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    rb'(?i)SecurityToken\s*=\s*[A-Za-z0-9]{16,}',
]


def main():
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    issues=[]
    count=total=0
    for name in filter(None,paths):
        path=Path(name)
        if any(part.lower() in {'.runtime','logs','saved','intermediate','binaries','content'} for part in path.parts):
            issues.append(name+': generated/private directory')
        if path.name=='settings.local.json' or path.suffix in {'.blend','.csv','.log','.env','.dll','.exe'}:
            issues.append(name+': private/binary output')
        data=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
        count+=1
        total+=len(data)
        if path.suffix!='.whl':
            if any(re.search(pattern,data) for pattern in patterns):
                issues.append(name+': possible credential')
        if len(data)>10*1024*1024:
            issues.append(name+': unexpected large file')
    if issues:
        raise SystemExit('\n'.join(issues))
    print(f'ARRIETTY_PUBLIC_TREE_OK files={count} bytes={total}; generated content and local credentials excluded')


if __name__=='__main__': main()
