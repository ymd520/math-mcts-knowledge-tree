"""Non-tautological 20x20 finite-set membership transportation benchmark.

For j=0..19, x_j is a distinct natural number in S_0. The sets form 20
strict inclusions S_0⊂S_1⊂...⊂S_20. The *single mathematical rule*
(x∈A ∧ A⊆B ⇒ x∈B) is instantiated to transport all 20 memberships across
20 steps. This is a real valid elementary set-theoretic inference schema,
though the concrete example is synthetically generated rather than a
research theorem or a held-out published proof.
"""
from __future__ import annotations

from math_mcts.reasoning import Atom, Rule, RuleBook
from math_mcts.layered import LayerConfig, derive_layers, replay_layers


def make_set_transport(*, width=20, depth=20, omit_subset_at=None):
    if width<20 or depth<20:
        raise ValueError("Capacity demonstration requires 20x20 or more")
    objs={f"x{i:02}":"Elem" for i in range(width)}
    objs.update({f"S{i:02}":"Set" for i in range(depth+1)})
    sig={"member":("Elem","Set"),"subset":("Set","Set")}
    x=Atom("member",("?x","?a"))
    sub=Atom("subset",("?a","?b"))
    y=Atom("member",("?x","?b"))
    rule=Rule("set_membership_transport",(x,sub),y,
              (("?x","Elem"),("?a","Set"),("?b","Set")),
              source="set inclusion definition: x∈A and A⊆B imply x∈B",
              status="reviewed")
    facts={Atom("member",(f"x{i:02}","S00")) for i in range(width)}
    facts.update(Atom("subset",(f"S{i:02}",f"S{i+1:02}"))
                 for i in range(depth) if i!=omit_subset_at)
    goals=tuple(Atom("member",(f"x{i:02}",f"S{depth:02}"))
                for i in range(width))
    book=RuleBook(sig,objs,[rule])
    cfg=LayerConfig(min_knowledge=20,min_layers=20,max_layers=depth,
                    batch_width=width,max_candidates=3000,batch_choices=8)
    return book,frozenset(facts),goals,cfg


def run_set_transport(*,iterations=3,seed=7,omit_subset_at=None):
    book,facts,goals,cfg=make_set_transport(omit_subset_at=omit_subset_at)
    result=derive_layers(book,facts,goals,config=cfg,iterations=iterations,seed=seed)
    result["real_mathematical_schema"]="set inclusion preserves element membership"
    result["generated_instance_not_research_theorem"]=True
    return result
