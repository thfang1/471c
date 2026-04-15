## Minor Extension: Function Inlining

## 1. Justification

Function calls carry overhead like argument passing, stack frame setup, and the call/return itself. For small functions, especially those called only once, this overhead can exceed the cost of the function body. Inlining substitutes the function body directly at the call site, eliminating the call overhead and, more importantly, exposing the function body to the surrounding optimization context.

Inlining is particularly impactful in a CPS converted pipeline because CPS introduces many small administrative functions. Inlining these reduces the IR size and simplifies the structure that downstream passes must handle.

**Who benefits:**
- Users with performance-sensitive code that uses many small helper functions.
- The optimization loop: inlining exposes new optimization opportunities to existing passes (constant folding, CSE, copy propagation) that were previously hidden behind call boundaries.
- Register allocation: fewer function boundaries means fewer save/restore points and potentially better register utilization.

## 2. User-Facing Behavior

Inlining is transparent to the user. A function that is inlined behaves identically to one that is not, the only observable difference is execution speed.

```scheme
(define (square x) (* x x))

(let ([a (square 5)])
  (let ([b (square 6)])
    (+ a b)))
```

After inlining `square` at both call sites (and running uniqification to avoid name collisions):

```scheme
(let ([x0 5])
  (let ([a (* x0 x0)])
    (let ([x1 6])
      (let ([b (* x1 x1)])
        (+ a b)))))
```

After constant folding and DCE, this reduces to:

```scheme
(+ 25 36)  ;; -> 61
```

The user sees the correct result, potentially computed entirely at compile time.

## 3. Pipeline Impact

Function inlining is added as a new pass in the optimization loop. The pass applies two inlining heuristics:

- **Single-use inlining:** If a let-bound function is called exactly once in its scope, inline unconditionally (the call site is the only use, so there is no code size increase).
- **Small-function inlining:** If a function body is below a size threshold (e.g., 5 AST nodes), inline at all call sites regardless of call count.

**Uniqification (prerequisite):** Inlining substitutes a function body into a new scope. Without fresh variable names, this can introduce variable capture bugs. Uniqification must run after each inline step to ensure all introduced bindings are globally unique.

- **Interaction with Register Allocation:** Inlining increases function body size and live variable count, raising register pressure. Register allocation must run after inlining. The register allocator should not assume function bodies remain small.
- **Interaction with CSE and Copy Propagation:** Inlining often introduces new duplicate subexpressions. Running CSE after inlining can eliminate this new redundancy.

## 4. Success Criteria

- **Correctness:** All existing test cases pass unchanged.
- **Inlining coverage:** All single-use functions and all functions below the size threshold are inlined. A post-pass check confirms no eligible call sites remain.
- **No variable capture:** After inlining and re-uniqification, no variable name collision exists in the output. This can be verified by checking that all bound names are globally unique.
- **Optimization synergy:** On programs with small helper functions, the combined output of inlining + constant folding + CSE + DCE contains strictly fewer operations than without inlining. A benchmark quantifies this.
- **Size threshold tuning:** The size threshold is configurable. Tests confirm that threshold = 0 (no small-function inlining) and threshold = ∞ (inline everything) both produce correct output.