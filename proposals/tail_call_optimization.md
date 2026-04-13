## Minor Extension: Tail Call Optimization

### 1) Justification

Functional programs often use recursion instead of loops. Without tail call optimization, each recursive call consumes a stack frame, eventually leading to a Stack Overflow.

This benefits users writing recursive algorithms or state machines.

### 2) User Viewpoint

This would crash without tail call optimization on large `n`:

```scheme
(define (count-down n)
  (if (= n 0) 'done (count-down (- n 1))))
```

With TCO, `count-down` runs in constant stack space, effectively behaving like a `while` loop.

### 3) Compiler Impact

- **Pipeline:** Implemented during or after CPS conversion.
- **Mechanism:** Identify calls where the continuation is the identity function. Instead of a `call` instruction, emit a `jmp` to the start of the function after updating arguments.
- **Interaction:** Works perfectly with Closure Conversion to ensure tail-called closures don't leak stack memory.

### 4) Success Criteria

- Deeply recursive functions execute without crashing the stack.
