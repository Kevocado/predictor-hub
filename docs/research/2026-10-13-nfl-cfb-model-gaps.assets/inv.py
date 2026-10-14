import glob,os,re,sys,pyarrow.parquet as pq,collections,json
root=sys.argv[1]
g=collections.defaultdict(list)
for f in sorted(glob.glob(root+'/**/*.parquet',recursive=True)):
    b=os.path.basename(f); d=os.path.relpath(os.path.dirname(f),root)
    m=re.search(r'(20\d\d)',b); kind=re.sub(r'20\d\d','YYYY',b)
    g[(d,kind)].append((int(m.group(1)) if m else None,f))
for (d,k),L in g.items():
    ys=[y for y,_ in L if y]; f=L[0][1] if not ys else max(L)[1]
    s=pq.ParquetFile(f); print(f"{d}/{k} | {min(ys) if ys else '-'}-{max(ys) if ys else '-'} ({len(L)}f) | rows_last={s.metadata.num_rows} | ncol={len(s.schema_arrow.names)}")
