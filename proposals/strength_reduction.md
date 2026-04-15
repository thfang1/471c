## Minor Extension: Strength Reduction

## 1. Justification

Some arithmetic operations are semantically equivalent to cheaper ones for specific operand values. Multiplication by a power of two, for example, is equivalent to a left shift, multiplying by one is equivalent to the identity; adding zero is a no-op. These equivalences are collectively called strength reductions.

Unlike constant folding, strength reduction applies whenever one operand is a known constant, even if the other is a variable. This makes it applicable in many more situations and a natural complement to the existing constant propagation and folding infrastructure.

**Who benefits:**
- Users writing numeric code with common patterns like squaring, doubling, or scaling by constants.
- The backend: strength reductions produce operations that map more directly to efficient machine instructions (shifts instead of multiplications).
- The optimization loop: reductions may expose new constant-folding or DCE opportunities.

## 2. User-Facing Behavior

Strength reduction is fully transparent. The user sees only the correct result, produced faster. Examples of reductions applied:

```scheme
(* x 1)    ;; -> x
(* x 0)    ;; -> 0
(+ x 0)    ;; -> x
(- x 0)    ;; -> x
(* x 2)    ;; -> (+ x x)
(expt x 2) ;; -> (* x x)
(/ x 1)    ;; -> x
(* 0 x)    ;; -> 0
```

For example, a program containing `(* n 2)` is internally rewritten to `(+ n n)`, which on most architectures maps to a single ADD instruction rather than a MUL.

## 3. Pipeline Impact

Strength reduction is implemented as a small, self-contained peephole pass that runs within the existing optimization loop, after constant folding. It pattern-matches on primitive application nodes and rewrites them according to a fixed table of reduction rules.

The pass is purely local: each rewrite examines a single primitive application node and its immediate operands. No global analysis is required. This makes the pass easy to extend, new rules are added by appending to the rule table.

- **Interaction with CSE and Copy Propagation:** Rewriting `(* x 2)` to `(+ x x)` introduces a repeated reference to `x`. If `x` is itself a complex expression, CSE may introduce a shared binding. The two passes interact beneficially.
- **Interaction with Type Inference:** Type annotations can enable additional reductions. For example, if `x` is statically known to be an integer, `(* x 2)` can be reduced to a left-shift `(arithmetic-shift x 1)`. Without type information, this reduction is only safe for integers and cannot be applied unconditionally.
## 4. Success Criteria

- **Correctness:** All existing test cases pass unchanged. Each reduction rule is verified by a unit test that checks input/output equivalence.
- **Coverage:** A program containing each of the reduction patterns listed above produces the expected reduced form in the output IR.
- **No over-reduction:** Expressions that do not match any rule are left unchanged. A test suite of non-reducible expressions confirms no spurious rewrites occur.
- **Rule extensibility:** A new reduction rule can be added by appending a single case to the rule table and adding one test. No structural changes to the pass are required.
- **Synergy:** On a benchmark containing strength-reducible patterns, the combined output of strength reduction + constant folding contains fewer primitive operation nodes than constant folding alone.