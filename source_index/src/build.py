"""Build a pinned source-backed SQLite graph, without executing upstream code."""
import collections, hashlib, json, pathlib, re, sqlite3, tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
SHA='105b9b1ce126e77b467aac6f6ba36b510ac57368'
FIELDS=[
('Foundations','基础与数学逻辑','Logic,SetTheory,ModelTheory','命题逻辑|谓词逻辑|集合|函数|关系|数学归纳法|选择公理|形式证明|模型论|集合论'),
('Elementary','初等数学','Data/Nat,Data/Int,Data/Rat,Data/Real','自然数|整数|有理数|实数|分数|比例|方程|不等式|多项式|三角函数|坐标几何'),
('Algebra','抽象代数','Algebra,GroupTheory,RingTheory,FieldTheory','群|子群|商群|群作用|环|理想|商环|域|域扩张|伽罗瓦理论|模|张量积|交换代数'),
('LinearAlgebra','线性代数','LinearAlgebra','向量空间|线性映射|矩阵|行列式|秩|特征值|特征向量|内积|正交投影|谱定理|奇异值分解'),
('NumberTheory','数论','NumberTheory','整除|素数|同余|中国剩余定理|二次互反律|丢番图方程|代数数论|解析数论|椭圆曲线|模形式|p进数'),
('Analysis','实分析与微积分','Analysis/Calculus,Analysis/SpecialFunctions,Data/Real','极限|连续|导数|积分|级数|一致收敛|多元微积分|隐函数定理|逆函数定理|泰勒展开'),
('Complex','复分析','Analysis/Complex,Analysis/Meromorphic','复数|全纯函数|柯西积分定理|留数|解析延拓|黎曼曲面|亚纯函数'),
('Functional','泛函分析','Analysis/Normed,Analysis/InnerProduct,Analysis/LocallyConvex','赋范空间|巴拿赫空间|希尔伯特空间|连续线性泛函|对偶空间|Hahn–Banach定理|弱拓扑|算子谱'),
('Measure','测度与积分','MeasureTheory','σ代数|测度|可测函数|Lebesgue积分|控制收敛定理|Fubini定理|Radon–Nikodym定理'),
('Harmonic','调和分析','Analysis/Fourier,Analysis/Convolution','Fourier级数|Fourier变换|卷积|Plancherel定理|分布|小波|非交换调和分析'),
('Topology','拓扑学','Topology','拓扑空间|开集与闭集|紧致性|连通性|分离公理|商拓扑|乘积拓扑|度量空间|一致空间'),
('AlgebraicTopology','代数拓扑','AlgebraicTopology','同伦|基本群|覆盖空间|单纯复形|同调|上同调|谱序列|纤维丛'),
('Geometry','几何学与微分几何','Geometry','欧氏几何|仿射几何|射影几何|流形|切空间|微分形式|黎曼度量|曲率|测地线|辛几何'),
('AlgebraicGeometry','代数几何','AlgebraicGeometry','代数簇|概形|层|态射|除子|线丛|模空间|代数曲线|交点理论'),
('CategoryTheory','范畴与同调代数','CategoryTheory','范畴|函子|自然变换|极限与余极限|伴随|单子|链复形|导出函子|导出范畴'),
('RepresentationTheory','表示论与李理论','RepresentationTheory,Analysis/Lie','群表示|不可约表示|特征标|李群|李代数|根系|诱导表示'),
('Combinatorics','组合数学与图论','Combinatorics','计数原理|生成函数|图|树|匹配|图着色|极值组合|Ramsey理论|设计理论|拟阵'),
('Order','序与格理论','Order','偏序|全序|格|完备格|布尔代数|不动点定理|域理论'),
('Probability','概率与随机过程','Probability','概率空间|随机变量|条件概率|独立性|期望|大数定律|中心极限定理|鞅|马尔可夫链|布朗运动'),
('Statistics','统计学','Probability','估计|最大似然|假设检验|置信区间|贝叶斯推断|回归|实验设计|非参数统计'),
('Dynamics','微分方程与动力系统','Dynamics,Analysis/ODE,Analysis/Distribution','常微分方程|偏微分方程|初值问题|边值问题|稳定性|遍历理论|分岔|混沌|守恒律'),
('Numerics','数值分析与科学计算','Analysis/Normed,LinearAlgebra/Matrix','浮点误差|条件数|稳定算法|插值|数值积分|线性系统求解|迭代法|有限元|有限差分'),
('Optimization','优化与运筹学','Analysis/Convex,Analysis/Calculus','凸集|凸函数|线性规划|对偶性|KKT条件|梯度下降|整数规划|动态规划|最优控制'),
('Computability','计算理论与算法','Computability,Data','可计算性|图灵机|可判定性|复杂性类|NP完全性|随机算法|在线算法|算法下界'),
('InformationTheory','信息论与编码','InformationTheory','熵|互信息|信道容量|数据处理不等式|纠错码|压缩|密码学'),
('MathematicalPhysics','数学物理','Analysis,Geometry,Probability','变分法|Hamilton力学|量子力学|统计力学|谱分析|规范理论|可积系统'),
('Applied','交叉应用数学','Control,Analysis,Probability','控制理论|信号处理|金融数学|生物数学|网络科学|机器学习数学|逆问题'),
]

def strip_comments(s):
    # Preserve newlines/positions; remove nested Lean block comments, strings and line comments.
    out=list(s);i=0;depth=0;string=False
    while i<len(s):
        if depth:
            if s.startswith('/-',i): depth+=1;out[i:i+2]=[' ',' '];i+=2;continue
            if s.startswith('-/',i): depth-=1;out[i:i+2]=[' ',' '];i+=2;continue
            if s[i]!='\n':out[i]=' '
            i+=1;continue
        if string:
            if s[i]=='\\':
                out[i]=' ';i+=1
                if i<len(s) and s[i]!='\n':out[i]=' '
                i+=1;continue
            if s[i]=='"':string=False
            if s[i]!='\n':out[i]=' '
            i+=1;continue
        if s.startswith('/-',i):depth=1;out[i:i+2]=[' ',' '];i+=2;continue
        if s.startswith('--',i):
            end=s.find('\n',i)
            if end<0:end=len(s)
            out[i:end]=[' ']*(end-i);i=end;continue
        if s[i]=='"':string=True;out[i]=' '
        i+=1
    return ''.join(out)

def build():
    db=ROOT/'data/knowledge.sqlite';db.unlink(missing_ok=True)
    con=sqlite3.connect(db)
    con.executescript('''CREATE TABLE nodes(id TEXT PRIMARY KEY,label TEXT,kind TEXT,status TEXT,source TEXT,payload TEXT);
    CREATE TABLE edges(src TEXT,dst TEXT,relation TEXT,PRIMARY KEY(src,dst,relation));
    CREATE INDEX outgoing ON edges(src,relation); CREATE INDEX incoming ON edges(dst,relation);
    CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED,label,body);''')
    def node(id,label,kind,status,source='',payload=None):
        con.execute('INSERT OR IGNORE INTO nodes VALUES(?,?,?,?,?,?)',(id,label,kind,status,source,json.dumps(payload or {},ensure_ascii=False)))
        con.execute('INSERT INTO search VALUES(?,?,?)',(id,label,json.dumps(payload or {},ensure_ascii=False)))
    def edge(a,b,kind):con.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?)',(a,b,kind))
    node('root','数学知识 Mathematics','root','index')
    node('source:mathlib','mathlib4 形式化源码','source','source_snapshot','https://github.com/leanprover-community/mathlib4/tree/'+SHA)
    edge('root','source:mathlib','contains')
    dirs={'Mathlib':'source:mathlib'};modules={};source_text={}
    archive=ROOT/'vendor/mathlib4.tar.gz'
    with tarfile.open(archive) as tar:
        for m in tar.getmembers():
            if not m.isfile():continue
            path=m.name.split('/',1)[-1]
            if path in ['LICENSE','NOTICE','lean-toolchain','CITATION.md']:
                (ROOT/'vendor'/('mathlib4-'+path.replace('.md','.txt'))).write_bytes(tar.extractfile(m).read())
            if not(path.startswith('Mathlib/') and path.endswith('.lean')):continue
            body=tar.extractfile(m).read().decode();source_text[path]=body
            parts=path.split('/')[:-1]
            for k in range(2,len(parts)+1):
                d='/'.join(parts[:k])
                if d not in dirs:
                    dirs[d]='dir:'+d
                    node(dirs[d],d.replace('/',' · '),'directory','index','https://github.com/leanprover-community/mathlib4/tree/'+SHA+'/'+d)
                    edge(dirs['/'.join(parts[:k-1])],dirs[d],'contains')
            id='module:'+path;modules[path[:-5].replace('/','.')]=id
            url='https://github.com/leanprover-community/mathlib4/blob/'+SHA+'/'+path
            node(id,path,'module','source_indexed_not_locally_compiled',url,{'path':path,'commit':SHA,'sha256':hashlib.sha256(body.encode()).hexdigest()})
            edge(dirs['/'.join(parts)],id,'contains')
    count=0;missing=[]
    # This is a lexical locator, not a Lean AST or theorem dependency extractor.
    pat=re.compile(r'^\s*(?:(?:private|protected|noncomputable|unsafe|partial)\s+)*(theorem|lemma|def|abbrev|class|structure|inductive|axiom)\s+([^\s(:{\[=]+)')
    for path,body in sorted(source_text.items()):
        id='module:'+path;clean=strip_comments(body)
        for line_no,line in enumerate(clean.splitlines(),1):
            im=re.match(r'^\s*(?:public\s+)?import\s+(.*)',line)
            if im:
                for target in im.group(1).split():
                    if target in modules:edge(id,modules[target],'imports')
                    else:missing.append({'module':id,'target':target})
            match=pat.match(line)
            if match:
                kind,name=match.groups();decl='decl:'+path+':'+str(line_no)
                node(decl,name,'declaration','lexical_locator_not_ast', 'https://github.com/leanprover-community/mathlib4/blob/'+SHA+'/'+path+'#L'+str(line_no),{'path':path,'line':line_no,'declaration_kind':kind,'commit':SHA,'qualified_name':None})
                edge(id,decl,'contains');count+=1
    for key,zh,prefixes,topics in FIELDS:
        f='field:'+key;node(f,zh+' '+key,'field','editorial_index',payload={'coverage':'partial; see gap report'})
        edge('root',f,'contains')
        mapped=[]
        for prefix in prefixes.split(','):
            d='Mathlib/'+prefix
            if d in dirs:edge(f,dirs[d],'source_map');mapped.append(d)
        for i,topic in enumerate(topics.split('|')):
            c='concept:'+key+':'+str(i)
            node(c,topic,'concept','outline_only',payload={'scope':'topic label; definition/theorem card not yet curated','field':key,'reference_modules':mapped})
            edge(f,c,'contains')
        # Editorial mapping is explicitly not a prerequisite theorem dependency.
    con.commit()
    counts=dict(con.execute('SELECT kind,count(*) FROM nodes GROUP BY kind'))
    edges=dict(con.execute('SELECT relation,count(*) FROM edges GROUP BY relation'))
    manifest={'version':'0.1.0','source_commit':SHA,'source_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'node_counts':counts,'edge_counts':edges,'external_imports':len(missing),'declaration_extractor':'comment/string aware lexical locator; not Lean elaboration','status':'broad source-backed baseline; not all mathematical knowledge'}
    (ROOT/'reports/coverage.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    (ROOT/'reports/external-imports.json').write_text(json.dumps(missing,ensure_ascii=False,indent=2))
    (ROOT/'data/fields.json').write_text(json.dumps([{'id':x[0],'label':x[1],'source_prefixes':x[2].split(','),'topics':x[3].split('|')} for x in FIELDS],ensure_ascii=False,indent=2))
    con.close();print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':build()
