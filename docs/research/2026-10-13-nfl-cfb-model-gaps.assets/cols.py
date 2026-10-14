import pyarrow.parquet as pq,re,glob,sys
src=sys.argv[1]; txt=open('/dev/stdin').read() if False else ''.join(open(f).read() for f in glob.glob(src+'/**/*.py',recursive=True)+glob.glob(src+'/../scripts/*.py'))
for name,f in [a.split('=') for a in sys.argv[2:]]:
    cols=pq.ParquetFile(f).schema_arrow.names
    used=[c for c in cols if re.search(r'["\']'+re.escape(c)+r'["\']',txt)]
    un=[c for c in cols if c not in used]
    print(f"## {name}: {len(cols)} cols, {len(used)} referenced in code\nUSED: {', '.join(used)}\nUNUSED({len(un)}): {', '.join(un)}\n")
