## Major Extension: Register Allocation

### 1) Justification

Currently, the compiler assumes an infinite supply of virtual registers. Physical hardware is limited. Efficiently mapping many variables to few registers is the single most important factor in generated code performance.

This benefits when requiring high-performance execution. It reduces writing to slow RAM and maximizes the use of fast CPU registers.

### 2) User Viewpoint

Users don't see syntax changes, but they see performance gains. Code generates many `mov` instructions to/from the stack before register allocation, but now variables stay in `%rax`, `%rbx`, etc., across multiple operations.

### 3) Compiler Impact

- **Pipeline:** Significant impact on the Backend/L1 pass.
- **Mechanism:** Compute which variables are live at each instruction. Build a graph where nodes are variables and edges represent variables that are live at the same time. Assign registers to nodes such that no adjacent nodes share a color.
- **Interaction:** Interacts with Copy Propagation — by removing unnecessary moves, the interference graph becomes simpler, leading to better coloring.

### 4) Success Criteria

- Successfully compiling L1 code using only the 16 available general-purpose registers.
- Measured reduction in Load/Store to stack compared to a naive allocator.
