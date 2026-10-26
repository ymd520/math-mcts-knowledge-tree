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
