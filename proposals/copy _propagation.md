## Minor Extension: Copy Propagation

### 1) Justification

Often, after other optimizations like Common Subexpression Elimination or Constant Propagation, code ends up with redundant assignments like `x = y`. Copy propagation replaces uses of `x` with `y` to eliminate the extra variable.

### 2) User Viewpoint

Indirect. It cleans up the mess left behind by other optimizations, making the final assembly cleaner.

### 3) Compiler Impact

- **Pipeline:** Part of the Optimization Loop.
- **Mechanism:** For every assignment `u = v`, replace all subsequent uses of `u` with `v`, provided neither `u` nor `v` is reassigned in between.
- **Interaction:** Essential for Register Allocation — by reducing the number of active variables, it lowers the degree of nodes in the interference graph.

### 4) Success Criteria

- Elimination of chain assignments in the final AST (e.g., `a = b; c = a;` becomes `c = b;`).
