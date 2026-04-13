## Major Extension: Closure Conversion

### 1) Justification

After CPS conversion, all function calls are in tail position and control flow is explicit. However, the L1 ASTs still contain lambdas that capture free variables from their lexical scope. Since low-level targets like L1 or assembly do not support scope, these variables would become invalid once the parent function returns, making the code impossible to compile directly.

Closure conversion fixes this by turning each lambda into a closed function and a closure record that stores its captured variables. All references to these variables are replaced with accesses to the closure, making the program suitable for low-level execution.

This benefits any downstream pass, like register allocation, code generation, that requires:
- All functions to be closed, flat procedures
- Optimization passes that benefit from knowing exactly which values are captured and shared across function boundaries

### 2) User Viewpoint (Surface Language)

Written in L3:

```scheme
(define (make-adder x)
  (lambda (y) (+ x y)))    ; x is a free variable in the lambda
(define add5 (make-adder 5))
(add5 10)    ; Returns 15
```

The compiler transforms this into a flat structure where the lambda becomes a top-level function that accepts an extra argument.

### 3) Compiler Impact

- **Pipeline:** Occurs after Uniqification but before/during CPS conversion.
- **Mechanism:** Identify variables used in a lambda not defined within it. Create a data structure to hold these variables. Rewrite the lambda to take the environment as an explicit parameter and replace free variable references with lookups into that environment.
- **Interaction:** Must be compatible with Tail Call Optimization — if a closure call is in a tail position, it should still be optimized.

### 4) Success Criteria

- Correct execution of L3 programs featuring nested functions and variable shadowing.
- Verification that all functions in the resulting L2/L1 code contain zero free variables.
