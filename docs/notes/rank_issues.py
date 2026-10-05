import sys; sys.path.insert(0,'/workspace/pipelines/lovhistorie')
import json, glob, os, gzip, re
from collections import defaultdict
frozen={os.path.basename(p).split('.')[0]:p for p in glob.glob('data/lovtidend_text/*.jsonl.gz')}
segmented={json.loads(l)['issue_id'] for l in open('data/segments.jsonl')}
unseg=[iid for iid in frozen if iid not in segmented]
# date from lovtidend_index by id
li={e['id']:e for e in json.load(open('data/lovtidend_index.json'))}
SKAL=re.compile(r'skal\s+ly[dd]e', re.I)       # amendment restatement marker
ENDR=re.compile(r'\bendr(?:ing|inger|es|et|a)\b|\boppheves\b', re.I)
rows=[]
for iid in unseg:
    txt="\n".join(json.loads(l).get("text","") for l in gzip.open(frozen[iid],'rt',encoding='utf-8'))
    n=len(txt)
    skal=len(SKAL.findall(txt)); endr=len(ENDR.findall(txt))
    meta=li.get(iid,{})
    rows.append({"iid":iid,"chars":n,"giant":n>600000,"skal_lyde":skal,"endr_markers":endr,
                 "issued":meta.get("issued"),"pages":meta.get("pageCount")})
# rank: non-giants first, by amendment density (skal_lyde desc)
rows.sort(key=lambda r:(r["giant"], -r["skal_lyde"], -r["endr_markers"]))
json.dump(rows, open('/tmp/claude-2100640/-workspace/00e5813b-a1f4-4aa2-8a23-e026876b8ba8/scratchpad/issue_priority.json','w'), ensure_ascii=False, indent=0)
ng=[r for r in rows if not r["giant"]]; g=[r for r in rows if r["giant"]]
print(f"unsegmented: {len(rows)}  (regular {len(ng)}, giants {len(g)})")
print(f"total 'skal lyde' amendment markers in unsegmented: {sum(r['skal_lyde'] for r in rows)}")
print(f"  in regular issues: {sum(r['skal_lyde'] for r in ng)} | in giants: {sum(r['skal_lyde'] for r in g)}")
print("TOP 15 regular issues by amendment-marker density:")
for r in ng[:15]:
    print(f"  {r['iid'][:12]} issued={r['issued']} chars={r['chars']:>7} skal_lyde={r['skal_lyde']:>3} endr={r['endr_markers']:>3}")
print(f"regular issues with >=5 skal_lyde: {sum(1 for r in ng if r['skal_lyde']>=5)}")
print(f"regular issues with 0 skal_lyde (likely no amendments -> deprioritize): {sum(1 for r in ng if r['skal_lyde']==0)}")
