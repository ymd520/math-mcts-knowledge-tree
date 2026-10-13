import re,json,gzip,hashlib,collections
from pathlib import Path
out=Path('repo/math_mcts/data/imported');out.mkdir(parents=True,exist_ok=True)
rawdir=Path('repo/imports/mcts_text_20261013');rawdir.mkdir(parents=True,exist_ok=True)
fields=['原始说明','名称','类型','模块','完整数学陈述','假设与参数','结论','核验状态','领域树映射','原1378核心子库标记','陈述SHA256','数据层','层内编号','文档定位','源码定位','源码文件','源码行范围']
pat=re.compile(r'^【知识卡 ([^】]+)】\n',re.M)
seen=set(); stats=collections.Counter();manifest=[];bad=[];domains={}
for f in sorted(Path('inputs').glob('*.txt')):
 data=f.read_bytes();text=data.decode('utf-8-sig'); matches=list(pat.finditer(text)); cards=[]
 rawname=f.name+'.gz';(rawdir/rawname).write_bytes(gzip.compress(data,mtime=0))
 for i,m in enumerate(matches):
  block=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
  # Card ends at first blank line after symbol references or at next section marker.
  vals={}
  for key in fields:
   hit=re.search('^'+re.escape(key)+'：(.*)$',block,re.M)
   if hit: vals[key]=hit.group(1)
  required=['名称','模块','完整数学陈述','核验状态','陈述SHA256', ]
  if any(k not in vals for k in required):bad.append([f.name,m.group(1),'missing fields']);continue
  formal=vals['完整数学陈述'];sha=hashlib.sha256((formal.removeprefix('theorem '+vals['名称']).strip() if vals['类型']=='upstream_theorem' else formal).encode()).hexdigest()
  if vals['类型']=='upstream_theorem' and sha!=vals['陈述SHA256']:bad.append([f.name,m.group(1),'hash mismatch']);continue
  key=(vals['模块'],vals['名称'],sha)
  if key in seen:stats['duplicates']+=1;continue
  seen.add(key);parts=vals['模块'].split('.');domain=parts[1] if len(parts)>1 else 'Other';domains[domain]=domain
  refs=[]; refpart=block.split('陈述中的符号引用：\n',1)
  if len(refpart)>1:
   for line in refpart[1].splitlines():
    if not line.strip():break
    if '\t' not in line:break
    name,url=line.split('\t',1);refs.append({'name':name,'doc_url':url.replace('@DOC/','https://leanprover-community.github.io/mathlib4_docs/')})
  source=vals.get('源码定位','')
  if vals['类型']=='upstream_theorem' and '/54c01c3314d33d15d77893cbe4e0472ff26bb34d/' not in source:bad.append([f.name,m.group(1),'source revision mismatch']);continue
  card=dict(id='IM'+hashlib.sha256(('\0'.join(key)).encode()).hexdigest(),domain_cn=domain,domain_en=domain,branch_cn=parts[2] if len(parts)>2 else domain,topic_cn='.'.join(parts[3:]) or domain,cn=vals['名称'],en=vals['名称'],definition='上游形式化声明；中文释义与重要性待审核。假设见 formal 与 assumptions。',formulas=[],level=5,prereq=[],tags=['导入待审'],kind='形式声明' if vals['类型']=='upstream_theorem' else '标准知识待审',example='',formal=formal,module=vals['模块'],doc_url=vals.get('文档定位','').replace('@DOC/','https://leanprover-community.github.io/mathlib4_docs/'),assumptions=vals.get('假设与参数',''),conclusion=vals.get('结论',''),verification_status=vals['核验状态'],curation_status='pending_semantic_and_importance_review',source_url=source,statement_sha256=sha,statement_symbol_references=refs,reference_relation='statement_symbol_reference_not_proof_dependency',original_metadata=vals,import_source_file=f.name,import_card_number=m.group(1),level_status='conservative_placeholder_not_assessed',prereq_status='not_extracted')
  cards.append(card);stats[vals['类型']]+=1
 p=out/(f.stem+'.json.gz');payload=json.dumps({'concepts':cards},ensure_ascii=False,separators=(',',':')).encode();p.write_bytes(gzip.compress(payload,mtime=0))
 manifest.append({'source_file':f.name,'source_sha256':hashlib.sha256(data).hexdigest(),'source_bytes':len(data),'raw_archive':'imports/mcts_text_20261013/'+rawname,'shard':p.name,'card_count':len(cards),'shard_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 print(f.name,len(cards),flush=True)
report={'expected_cards':234576,'imported_cards':len(seen),'errors':bad,'counts':dict(stats),'files':manifest,'scope':'structural and provenance audit; no local Lean kernel run; no exhaustive semantic or importance certification'}
(out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
assert not bad,bad[:5]
assert len(seen)==234576,len(seen)
print('PASS',len(seen))
