## Major Extension: Register Allocation

## 1. Justification

After CPS conversion, function bodies consist of a linear sequence of let-bindings followed by a tail call or primitive return. Each let-binding introduces a named temporary. In a real machine model, these temporaries must be mapped to a finite set of physical registers. Without register allocation, the compiler cannot produce realistic machine code or assembly.

A linear-scan register allocator is the standard choice for a course-level compiler, it is significantly simpler than graph-coloring allocation, produces acceptable code quality, and has well-understood worst-case behavior. It operates in a single left-to-right scan over the live intervals of all variables, assigning registers greedily and spilling the variable with the latest endpoint when no register is free.

**Who benefits:**
- Any student or engineer who wants the compiler to produce real, executable output — register allocation is the last major pass before instruction selection and code emission.
- Students studying compiler backends: this pass introduces liveness analysis, interference, and spilling in a controlled, tractable setting.
- Downstream code generation work: all subsequent backend work (instruction selection, stack layout, calling convention) assumes register-allocated output.

## 2. User-Facing Behavior

Register allocation is entirely transparent to the L3 programmer. No source-language changes are required. The user-visible effect is that the compiler now produces output annotated with register assignments, bringing the pipeline within one step of code emission.

Consider a simple function body in L1 IR after CPS conversion:

```scheme
(define (f x)
  (let ([a (+ x 1)])
    (let ([b (* a 2)])
      (let ([c (- b a)])
        c))))
```

After register allocation (assuming 3 available registers r0, r1, r2), the annotated output would resemble:

```scheme
(define (f x)
  ;; x    -> r0  [interval: 0-3]
  ;; a    -> r1  [interval: 1-3]
  ;; b    -> r2  [interval: 2-3]
  ;; c    -> r0  [interval: 3-3]  (reuses r0, x no longer live)
  (let ([a/r1 (+ x/r0 1)])
    (let ([b/r2 (* a/r1 2)])
      (let ([c/r0 (- b/r2 a/r1)])
        c/r0))))
```

When the number of live variables at any point exceeds the register count, the allocator spills the variable with the longest remaining live interval to a stack slot. A spill load/store is inserted at each use/def of the spilled variable.

## 3. Pipeline Impact

### New Pass: Linear-Scan Register Allocation

This pass is inserted after CPS conversion and operates on L1 function bodies. It produces register-annotated L1, where every variable reference carries a physical register assignment or a stack slot designation.

### Sub-Algorithms Required

- **Liveness Analysis:** For each function body, compute the live interval of each variable — the range [def, last-use] expressed as instruction indices. In CPS-form bodies (linear let-chains ending in a tail call), this reduces to a simple linear scan; no dataflow fixpoint is needed for straight-line code.
- **Interval Construction:** Walk the let-binding chain in order, recording the definition index and the last-use index for each variable.
- **Linear Scan Allocation:** Scan intervals left to right. Maintain an active set of currently live variables and a free register pool. At each interval start, assign the variable to a free register. If none is free, spill the active variable with the latest endpoint.
- **Spill Code Insertion:** For spilled variables, insert a stack-store immediately after the definition and a stack-load before each use. The stack frame layout is determined by the maximum number of spilled variables at any point.

### Interaction with Other Extensions

- **Type Inference:** Type information can inform register allocation decisions. For example, knowing a value is a boolean allows it to be stored in a 1-bit register or flag register. If type inference runs before register allocation, the allocator can exploit type annotations for better assignments.
- **Function Inlining:** Inlining increases function body size and thus the number of live variables at any point, potentially increasing register pressure. Register allocation must be run after inlining to correctly account for the merged variable sets.

## 4. Success Criteria

- **Correctness:** All existing test cases pass with register-annotated output. The semantics of every program is unchanged by register assignment.
- **Coverage:** Every variable in every function body receives either a register assignment or a spill slot. No variable is unallocated in the output.
- **Register bound:** At no program point are more physical registers in use simultaneously than the declared machine register count. This is verifiable by a simple post-pass checker.
- **Spill correctness:** For any spilled variable, a stack-store appears immediately after its definition and a stack-load appears before each of its uses.
- **Integration:** The register-allocated output is accepted as input by a code emitter (even a simple pretty-printer that maps register-annotated L1 to pseudo-assembly) without errors.
- **Performance comparison:** On a benchmark suite of 10+ programs, register-allocated output requires fewer than 2x the number of moves compared to a naive allocate-everything-to-stack baseline.
