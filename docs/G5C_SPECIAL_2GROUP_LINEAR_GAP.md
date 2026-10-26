# G5-C: a proved linear gap for a special 2-group family

This note records a rigorous special-family result and an exact finite
enumeration. It does **not** solve the arbitrary-finite-group G5-C problem.

## 1. General collision identity

Let a finite group G satisfy |G|=m^2 and let A subset G with |A|=m. Define
r(g)=#{(a,b) in A^2 : ab=g}. Then sum_g r(g)=m^2=|G| and

z_2(A)=|G|-|AA|=sum_{g:r(g)>0}(r(g)-1).

Thus every forced collision among ordered products contributes to the defect.
If q(A) is the number of unordered pairs {a,b} of distinct commuting elements
of A, then

z_2(A) >= q(A).

Proof: for each g, let q_g count such pairs with ab=g. Each pair contributes
both (a,b) and (b,a) to r(g), so r(g)>=2q_g. When q_g>0,
r(g)-1>=2q_g-1>=q_g. Sum over g.

A second elementary bound comes from repeated squares. If
s(A)=|{a^2 : a in A}|, then

z_2(A) >= m-s(A).

Indeed, the m diagonal pairs (a,a) map to only s(A) outputs, forcing at least
m-s(A) excess representations.

## 2. Linear gap for G = E_n x C_2

Let E_n be an extraspecial 2-group of order 2^(2n+1), and set
G=E_n x C_2, with n>=2. Then |G|=2^(2n+2)=m^2 for m=2^(n+1).

The central quotient G/Z(G) is a 2n-dimensional vector space V over F_2.
Its commutator is encoded by a nondegenerate alternating bilinear form
B: V x V -> F_2. Elements a,b in G commute exactly when
B(v_a,v_b)=0, where v_a,v_b are their quotient vectors.

Enumerate A={a_1,...,a_m}. Let C be the m-by-m matrix over F_2 with entries
C_ij=B(v_ai,v_aj). Then rank(C)<=2n and C has zero diagonal. Let M be the
matrix with zero diagonal and every off-diagonal entry equal to 1. Over F_2,
M=I+J, where J is the all-ones matrix. Since m is even, J^2=0 and M^2=I;
hence rank(M)=m.

The matrix D=M+C has a 1 exactly at off-diagonal positions corresponding to
commuting pairs in A. If q=q(A), D is the sum of q matrices
E_ij+E_ji, each of rank at most 2. Therefore rank(D)<=2q. Since M=D+C,

m=rank(M)<=rank(D)+rank(C)<=2q+2n,

so

q >= (m-2n)/2 = m/2-n.

For n>=2, 2^(n-1)>=n, hence n<=m/4 and

q >= m/4.
Combining with z_2(A)>=q proves the theorem:

**For every A subset E_n x C_2 with |A|=m, z_2(A)>=m/4.**

This result is valid for the stated group family only. The rank argument uses
the class-2 commutator form and does not currently provide a corresponding
rank bound for an arbitrary finite group.

## 3. Exact restricted enumeration at n=2

Use the model E_n x C_2 with elements (x,y,t,c), where x,y are n-bit vectors
and t,c are bits, and multiplication is

(x,y,t,c)(x',y',t',c') =
(x xor x', y xor y', t xor t' xor dot(x,y'), c xor c').

For n=2, |G|=64 and m=8. Restrict A to elements with dot(x,y)=1, so every
element squares to the same central involution (0,0,1,0). Also require that
A contain no inverse pair. The eligible inverse-pair keys are (x,y,c);
there are 12 keys, each with two choices of t. The restricted family therefore
contains

C(12,8) * 2^8 = 126,720 subsets.

An independent exhaustive enumeration using a precomputed multiplication
table found minimum defect 25, attained by 18,432 candidates. This is an
exact statement about this restricted family, not about all 8-subsets of the
group. The script tools/g5c_special_2group_experiment.py reproduces the
enumeration with --mode exact-n2.

## 4. Search-algorithm experiment

The same script provides an MCTS mode for n>=2. It preserves the restricted
family under swaps, uses exact incremental product multiplicities, and allows
a bounded exact-lookahead candidate sample. Compare sample sizes 0, 16 and 32
using paired seeds. Each result records best defect, created nodes, candidate
evaluations and wall-clock time.

Do not compare iteration counts alone: exact-lookahead spends extra work
scoring candidates. A lower best defect is evidence for that tested budget and
seed, not a theorem or proof of optimality. The next useful experiment is to
compare equal wall-clock and equal exact-evaluation budgets, then test whether
the same admission policy helps outside this special group family.

## 5. What remains open

The arbitrary finite group statement remains unresolved here:

For every finite group G with |G|=m^2 and every A subset G of size m, is there
a universal gamma>0 such that |G|-|AA|>=gamma*m?

The proved special-family bound and the exact n=2 enumeration do not settle
this question. The next mathematical bottleneck is to replace the symplectic
commutator-rank argument with a structural quantity available for arbitrary
finite groups, or to construct a counterexample family.


## 6. First paired MCTS benchmark (10 seeds)

The checked-in paired-benchmark workflow completed on Python 3.12.15 for
n=3, |G|=256 and m=16, using seeds
11, 23, 37, 41, 53, 67, 79, 83, 217 and 2027. Every sample size used the same
initial subset for each seed. Lower defect is better.

### Equal iteration budget

250 iterations, depth limit 6, and a 120-node cap per run:

| Lookahead sample B | Mean best defect | Seeds improved vs B=0 | Tied | Worse | Mean exact swap evaluations | Mean seconds |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 102.1 | — | — | — | 119.1 | 0.0203 |
| 16 | 100.9 | 7/10 | 1/10 | 2/10 | 231.0 | 0.0267 |
| 32 | 98.5 | 10/10 | 0/10 | 0/10 | 362.3 | 0.0404 |

### Equal wall-clock budget

One second per run, depth limit 6, and a 10,000-node cap so the wall-clock
budget—not the node cap—controlled the run:

| Lookahead sample B | Mean best defect | Seeds improved vs B=0 | Tied | Worse | Mean exact swap evaluations |
|---:|---:|---:|---:|---:|---:|
| 0 | 96.8 | — | — | — | 955.4 |
| 16 | 97.2 | 4/10 | 2/10 | 4/10 | 1255.1 |
| 32 | 93.6 | 7/10 | 1/10 | 2/10 | 1507.6 |

### Interpretation

For this restricted n=3 family and these ten paired seeds, B=32 improved the
best defect in all ten equal-iteration comparisons and in seven of ten
equal-time comparisons. The mean best defect fell from 102.1 to 98.5 under
equal iterations, and from 96.8 to 93.6 under equal time. This is a useful
positive signal for bounded exact-lookahead admission, not a universal result:
the sample is still small, only one group family was tested, and equal-time
runs spent more exact swap evaluations when B increased. Keep B=32 opt-in
until additional group families, more seeds and held-out budgets are tested.
