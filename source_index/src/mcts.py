"""Task-conditioned UCT search. Rewards measure retrieval relevance, not truth."""
import argparse, dataclasses, json, math, pathlib, random, re, sqlite3
from storage import ensure_database
ROOT=pathlib.Path(__file__).resolve().parents[1]
ALIASES={'群':'Group','环':'Ring','矩阵':'Matrix','卷积':'Convolution','傅里叶':'Fourier','拓扑':'Topology','概率':'Probability','数论':'NumberTheory','同调':'Homology','范畴':'Category','积分':'Integral','导数':'Deriv','几何':'Geometry','特征值':'Eigenvalue','紧致':'Compact','鞅':'Martingale','凸':'Convex','优化':'Convex','素数':'Prime','伽罗瓦':'Galois','实数':'Real','整数':'Int','自然数':'Nat','线性代数':'LinearAlgebra'}
class Graph:
    def __init__(self,path=ROOT/'data/knowledge.sqlite',imports=False):
        if path==ROOT/'data/knowledge.sqlite':ensure_database()
        self.db=sqlite3.connect(path);self.relations=['contains','source_map']+(['imports'] if imports else [])
        self.cache={}
    def children(self,id):
        if id not in self.cache:
            q=','.join('?' for _ in self.relations)
            self.cache[id]=[r[0] for r in self.db.execute(f'SELECT DISTINCT dst FROM edges WHERE src=? AND relation IN ({q}) ORDER BY dst',[id]+self.relations)]
        return self.cache[id]
    def info(self,id):
        r=self.db.execute('SELECT label,kind,status,source,payload FROM nodes WHERE id=?',(id,)).fetchone()
        return dict(zip(['label','kind','status','source','payload'],r))
    def targets(self,query,limit=500):
        terms=re.findall(r'[\w]+',query)
        terms+= [v for k,v in ALIASES.items() if k in query]
        terms=list(dict.fromkeys(terms))
        if not terms:return {}
        # FTS syntax is built from quoted literal tokens, never from user SQL.
        expr=' OR '.join('"'+t.replace('"','""')+'"*' for t in terms)
        rows=list(self.db.execute('SELECT id,bm25(search) FROM search WHERE search MATCH ? ORDER BY bm25(search),id LIMIT ?',(expr,limit)))
        scores={}
        for id,_ in rows:
            label=self.info(id)['label'].lower()
            scores[id]=sum(t.lower() in label for t in terms)/len(terms)
        return {k:v for k,v in scores.items() if v>0}
    def potentials(self,targets,depth=40):
        # Propagate hints to ancestors. This supplies an expansion order only.
        p=dict(targets);front=dict(targets)
        q=','.join('?' for _ in self.relations)
        for _ in range(depth):
            nxt={}
            for dst,val in front.items():
                for (src,) in self.db.execute(f'SELECT src FROM edges WHERE dst=? AND relation IN ({q})',[dst]+self.relations):
                    value=.98*val
                    if value>p.get(src,0)+1e-12:p[src]=value;nxt[src]=max(value,nxt.get(src,0))
            if not nxt:break
            front=nxt
        return p
@dataclasses.dataclass
class TreeNode:
    state: str
    parent: object=None
    children: list=dataclasses.field(default_factory=list)
    visits: int=0
    value: float=0.
    actions: object=None
    path: tuple=()
    @property
    def mean(self):return self.value/self.visits if self.visits else 0.

def search(graph,targets,potentials,iterations=1000,max_depth=30,seed=42,exploration=math.sqrt(2),root='root'):
    if iterations<1 or max_depth<1:raise ValueError('iterations and max_depth must be positive')
    rng=random.Random(seed);tree=TreeNode(root,path=(root,));all_nodes=[tree];best={};rollout_steps=0
    def actions(n):
        if n.actions is None:
            n.actions=sorted((a for a in graph.children(n.state) if a not in n.path),key=lambda a:(-potentials.get(a,0),a))
        return n.actions
    for _ in range(iterations):
        n=tree
        # Select, then expand one node with progressive widening.
        while len(n.path)-1<max_depth:
            a=actions(n);width=max(1,math.ceil(2*math.sqrt(n.visits+1)))
            if a and len(n.children)<min(width,len(a)):
                state=a[len(n.children)];child=TreeNode(state,parent=n,path=n.path+(state,))
                n.children.append(child);all_nodes.append(child);n=child;break
            if not n.children:break
            n=max(n.children,key=lambda c:c.mean+exploration*math.sqrt(math.log(n.visits+1)/c.visits))
        path=list(n.path);reward=max((targets.get(s,0) for s in path),default=0)
        # Random rollouts; 80% of choices concentrate on the best 8 hinted successors.
        while len(path)-1<max_depth:
            options=[a for a in graph.children(path[-1]) if a not in path]
            if not options:break
            options.sort(key=lambda a:(-potentials.get(a,0),a))
            nxt=rng.choice(options[:8] if rng.random()<.8 else options)
            path.append(nxt);rollout_steps+=1;reward=max(reward,targets.get(nxt,0))
        for s in path:
            if s in targets:
                cut=tuple(path[:path.index(s)+1]);old=best.get(s)
                if old is None or len(cut)<len(old):best[s]=cut
        while n is not None:n.visits+=1;n.value+=reward;n=n.parent
    index={id(n):i for i,n in enumerate(all_nodes)}
    export=[{'index':i,'state':n.state,'parent':index[id(n.parent)] if n.parent else None,'visits':n.visits,'value_sum':n.value,'mean_reward':n.mean,'depth':len(n.path)-1} for i,n in enumerate(all_nodes)]
    hits=sorted(best,key=lambda s:(-targets[s],len(best[s]),s))
    return {'iterations_completed':tree.visits,'expanded_nodes':len(all_nodes),'rollout_steps':rollout_steps,'seed':seed,'max_depth_limit':max_depth,'actual_expanded_depth':max(len(n.path)-1 for n in all_nodes),'reward_semantics':'heuristic lexical relevance in [0,1], not proof, novelty, or correctness','hits':[{'id':s,'reward':targets[s],'path':list(best[s])} for s in hits],'tree_nodes':export}

def main():
    ap=argparse.ArgumentParser(description='Search mathematical source knowledge with actual UCT MCTS')
    ap.add_argument('--query',required=True);ap.add_argument('--iterations',type=int,default=1000);ap.add_argument('--depth',type=int,default=30);ap.add_argument('--seed',type=int,default=42);ap.add_argument('--imports',action='store_true');ap.add_argument('--output',default='reports/search.json');ap.add_argument('--root',default='root')
    a=ap.parse_args();g=Graph(imports=a.imports)
    if not g.db.execute('SELECT 1 FROM nodes WHERE id=?',(a.root,)).fetchone():ap.error('unknown root')
    targets=g.targets(a.query);result=search(g,targets,g.potentials(targets),a.iterations,a.depth,a.seed,root=a.root)
    result['query']=a.query;result['relations']=g.relations;result['target_count']=len(targets);result['target_limit']=500
    result['no_signal']=not bool(targets)
    for hit in result['hits']:
        info=g.info(hit['id']);info.pop('payload');hit.update(info)
    output=pathlib.Path(a.output)
    if not output.is_absolute():output=ROOT/output
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:result[k] for k in ['query','target_count','iterations_completed','expanded_nodes','rollout_steps','actual_expanded_depth','no_signal']},ensure_ascii=False,indent=2))
    for hit in result['hits'][:10]:print(hit['label'],hit['source'])
    print('Saved:',output)
if __name__=='__main__':main()
