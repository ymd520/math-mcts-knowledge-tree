import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
from mcts import search
from build import strip_comments
class Tiny:
    def children(self,n):return {'root':['bad','good'],'bad':['dead'],'good':['goal'],'goal':['root']}.get(n,[])
class TestMCTS(unittest.TestCase):
    def test_actual_uct_and_backpropagation(self):
        r=search(Tiny(),{'goal':1},{'good':1,'goal':1},iterations=200,max_depth=20)
        self.assertEqual(r['iterations_completed'],200)
        nodes={n['state']:n for n in r['tree_nodes']}
        self.assertGreater(nodes['good']['visits'],nodes['bad']['visits'])
        self.assertTrue(any(h['id']=='goal' for h in r['hits']))
        self.assertLessEqual(r['actual_expanded_depth'],3)
        self.assertAlmostEqual(nodes['root']['value_sum'],nodes['good']['value_sum'])
    def test_reproducibility(self):
        args=(Tiny(),{'goal':1},{'good':1,'goal':1})
        self.assertEqual(search(*args),search(*args))
    def test_no_signal(self):
        r=search(Tiny(),{},{});self.assertEqual(r['hits'],[])
        self.assertTrue(all(n['value_sum']==0 for n in r['tree_nodes']))
    def test_comment_stripping(self):
        s='/-- theorem fake /- lemma nested -/ -/\n theorem real : True := by trivial\n-- def fake2\n def x := "theorem fake3"'
        out=strip_comments(s);self.assertNotIn('fake',out);self.assertIn('theorem real',out)
        self.assertEqual(s.count('\n'),out.count('\n'))
    def test_depth_and_validation(self):
        r=search(Tiny(),{'goal':1},{},max_depth=1)
        self.assertTrue(all(n['depth']<=1 for n in r['tree_nodes']))
        with self.assertRaises(ValueError):search(Tiny(),{},{},iterations=0)
if __name__=='__main__':unittest.main()
