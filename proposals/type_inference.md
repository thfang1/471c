## Major Extension: Type Inference

## 1. Justification

Currently, the compiler operates on untyped L3 ASTs. There is no static verification that operations are applied to values of the correct type, a program that applies arithmetic to a boolean, for example, is only caught at runtime. Adding a type inference pass brings three concrete benefits, it catches a large class of programmer errors before execution, it enriches the AST with type annotations that downstream passes can exploit, and it is a foundational technique that every compiler engineer should understand.

**Who benefits:**
- L3 programmers: type errors are caught at compile time with precise error messages, rather than producing wrong results or crashing at runtime.
- Downstream optimization passes: type annotations enable type-directed optimizations.
- Students: implementing HM inference is a canonical exercise in understanding unification, substitution, and the relationship between syntax and semantics.

## 2. User-Facing Behavior

For programs that are already type-correct, behavior is unchanged, type inference runs silently and the program compiles as before. The new user-visible behavior is precise, early error reporting for type-incorrect programs.

**Example: valid program (unchanged behavior)**

```scheme
(let ([x 5])
  (let ([y (+ x 3)])
    (* y 2)))
;; Inferred type: Int
;; Compiles and runs as before.
```

**Example: type error caught at compile time**

```scheme
(let ([x #t])
  (+ x 1))
;; Type error: operator '+' expects Int, got Bool for argument x.
;; Compilation halts with a descriptive error message.
```

**Example: polymorphic function**

```scheme
(lambda (f x) (f x))
;; Inferred type: (('a -> 'b) -> 'a -> 'b)
;; Works for any argument type, no annotation required.
```

The surface syntax of L3 is unchanged. Type annotations are optional and, in the initial implementation, not required. The compiler accepts exactly the same programs as before, and rejects programs that would have produced type errors at runtime.

## 3. Pipeline Impact

### New Pass: HM Type Inference

The pass is inserted between the L3 parser and the semantic analysis pass. It operates on raw L3 ASTs and produces type-annotated L3 ASTs. Every expression node carries an inferred type after this pass.

### Sub-Algorithms Required

- **Type Variable Generation:** Each expression is initially assigned a fresh type variable. These are unified as constraints are collected.
- **Constraint Generation:** A recursive traversal of the AST generates type equality constraints. For example, `(+ e1 e2)` generates the constraints `type(e1) = Int`, `type(e2) = Int`, and `type(+ e1 e2) = Int`.
- **Unification:** Constraints are solved using Robinson's unification algorithm. If two types cannot be unified (e.g., `Int` and `Bool`), a type error is reported with the source location of the conflict.
- **Substitution Application:** Once all constraints are solved, the resulting substitution is applied to every type variable in the AST, producing fully-resolved type annotations.
- **Generalization / Let-Polymorphism:** Let-bound variables are generalized to polymorphic types (type schemes), enabling the same let-bound function to be used at multiple types within its scope.

### Interaction with Other Extensions

- **Register Allocation:** Type annotations produced by this pass can be consumed by the register allocator to make better register assignment decisions. For instance, boolean values may be stored in flag registers, and known-integer values can skip tag-checking in a tagged representation.
- **CEP-03 CSE and Copy Propagation:** CSE's structural equality check for duplicate subexpressions can be made more precise with type information, two expressions of different types cannot be the same subexpression even if they look syntactically similar.

## 4. Success Criteria

- **Correctness:** All existing type-correct test cases compile and produce the same results as before.
- **Error detection:** A suite of type-incorrect programs (wrong argument types, applying non-functions, mixing booleans and integers) are all rejected with an error message that includes the source location and a description of the type conflict.
- **Type completeness:** Every expression node in the output AST carries a fully-resolved type annotation (no remaining type variables in the output).
- **Polymorphism:** Let-polymorphism is correctly implemented, a polymorphic function can be used at two different types within the same scope without a type error.
- **Annotation utilization:** At least one downstream pass (register allocation or constant folding) demonstrably uses the type annotations to produce better output than it would without them.