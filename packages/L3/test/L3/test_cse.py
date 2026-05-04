from L3.cse import cse_program, optimize_program, simplify
from L3.syntax import (Abstract, Allocate, Begin, Branch, Immediate, Let,
                        Load, Primitive, Program, Reference, Store, Term, Apply)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run(term: Term) -> Term:
    """Run the full pipeline: CSE then simplify (copy prop + constant fold)."""
    return simplify(cse_program(term))


# ---------------------------------------------------------------------------
# Copy Propagation
# ---------------------------------------------------------------------------

class TestCopyPropagation:

    def test_simple_copy_is_propagated(self) -> None:
        # (let ([x y]) x)
        # result: (let ([x y]) y)
        term: Term = Let(
            bindings=(("x", Reference(name="y")),),
            body=Reference(name="x")
        )
        result = simplify(term)
        assert result == Let(
            bindings=(("x", Reference(name="y")),),
            body=Reference(name="y")
        )

    def test_copy_chain_is_propagated(self) -> None:
        # (let ([x y]) (let ([z x]) z))
        # result: (let ([x y]) (let ([z y]) y))
        term: Term = Let(
            bindings=(("x", Reference(name="y")),),
            body=Let(
                bindings=(("z", Reference(name="x")),),
                body=Reference(name="z")
            )
        )
        result = simplify(term)
        assert result == Let(
            bindings=(("x", Reference(name="y")),),
            body=Let(
                bindings=(("z", Reference(name="y")),),
                body=Reference(name="y")
            )
        )

    def test_copy_used_in_primitive(self) -> None:
        # (let ([x y]) (+ x 1))
        # result: (let ([x y]) (+ y 1))
        term: Term = Let(
            bindings=(("x", Reference(name="y")),),
            body=Primitive(operator="+", left=Reference(name="x"), right=Immediate(value=1))
        )
        result = simplify(term)
        assert result == Let(
            bindings=(("x", Reference(name="y")),),
            body=Primitive(operator="+", left=Reference(name="y"), right=Immediate(value=1))
        )

    def test_copy_does_not_cross_lambda(self) -> None:
        # (let ([x y]) (lambda (x) x))
        # x is rebound as a lambda parameter, body stays Reference("x").
        term: Term = Let(
            bindings=(("x", Reference(name="y")),),
            body=Abstract(parameters=("x",), body=Reference(name="x"))
        )
        result = simplify(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Abstract)
        assert result.body.body == Reference(name="x")

    def test_constant_propagation_still_works(self) -> None:
        # (let ([x 5]) (+ x 1))
        # result: (let ([x 5]) 6)
        term: Term = Let(
            bindings=(("x", Immediate(value=5)),),
            body=Primitive(operator="+", left=Reference(name="x"), right=Immediate(value=1))
        )
        result = simplify(term)
        assert result == Let(
            bindings=(("x", Immediate(value=5)),),
            body=Immediate(value=6)
        )

    def test_constant_fold_subtraction(self) -> None:
        # Cover line 61 False path: op == "-"
        # (- 10 3)  ->  7
        term: Term = Primitive(operator="-", left=Immediate(value=10), right=Immediate(value=3))
        assert simplify(term) == Immediate(value=7)

    def test_constant_fold_multiplication(self) -> None:
        # Cover line 61 False path: op == "*"
        # (* 4 5)  ->  20
        term: Term = Primitive(operator="*", left=Immediate(value=4), right=Immediate(value=5))
        assert simplify(term) == Immediate(value=20)

    def test_branch_with_non_constant_condition(self) -> None:
        # Cover line 72 False path: condition not both Immediate
        # (if (< x 2) 10 20)  ->  Branch unchanged (x is a Reference)
        term: Term = Branch(
            operator="<",
            left=Reference(name="x"),
            right=Immediate(value=2),
            consequent=Immediate(value=10),
            otherwise=Immediate(value=20)
        )
        result = simplify(term)
        assert isinstance(result, Branch)
        assert result.left == Reference(name="x")

    def test_apply_is_simplified(self) -> None:
        # Cover line 89: Apply case in simplify
        # ((lambda (x) (+ x 1)) 5)  ->  Apply with simplified args
        term: Term = Apply(
            target=Abstract(parameters=("x",), body=Primitive(operator="+", left=Reference(name="x"), right=Immediate(value=1))),
            arguments=(Immediate(value=5),)
        )
        result = simplify(term)
        assert isinstance(result, Apply)

    def test_store_is_simplified(self) -> None:
        # Cover line 103: Store case in simplify
        term: Term = Store(
            base=Reference(name="b"),
            index=0,
            value=Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2))
        )
        result = simplify(term)
        assert isinstance(result, Store)
        assert result.value == Immediate(value=3)


# ---------------------------------------------------------------------------
# CSE
# ---------------------------------------------------------------------------

class TestCSE:

    def test_duplicate_primitive_is_deduplicated(self) -> None:
        # (let ([a (* x x)]) (let ([b (* x x)]) (+ a b)))
        # After CSE: b's binding becomes Reference("a")
        # Cover line 152: is_pure(s_val) and s_val in table
        xx: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Let(
            bindings=(("a", xx),),
            body=Let(
                bindings=(("b", xx),),
                body=Primitive(operator="+", left=Reference(name="a"), right=Reference(name="b"))
            )
        )
        result = cse_program(term)
        assert isinstance(result, Let)
        inner = result.body
        assert isinstance(inner, Let)
        assert inner.bindings[0] == ("b", Reference(name="a"))

    def test_cse_does_not_merge_impure_expressions(self) -> None:
        # Allocate is impure — two Allocates must NOT be merged
        term: Term = Let(
            bindings=(("a", Allocate(count=1)),),
            body=Let(
                bindings=(("b", Allocate(count=1)),),
                body=Reference(name="b")
            )
        )
        result = cse_program(term)
        assert isinstance(result, Let)
        inner = result.body
        assert isinstance(inner, Let)
        assert isinstance(inner.bindings[0][1], Allocate)

    def test_cse_does_not_merge_across_lambda(self) -> None:
        # The inner lambda should get its own CSE scope
        xx: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Let(
            bindings=(("a", xx),),
            body=Abstract(
                parameters=("x",),
                body=Let(
                    bindings=(("b", xx),),
                    body=Reference(name="b")
                )
            )
        )
        result = cse_program(term)
        assert isinstance(result, Let)
        lam = result.body
        assert isinstance(lam, Abstract)
        inner = lam.body
        assert isinstance(inner, Let)
        assert isinstance(inner.bindings[0][1], Primitive)

    def test_triple_duplicate_all_replaced(self) -> None:
        # Three bindings with the same pure expression
        xx: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Let(
            bindings=(("a", xx),),
            body=Let(
                bindings=(("b", xx),),
                body=Let(
                    bindings=(("c", xx),),
                    body=Primitive(
                        operator="+",
                        left=Reference(name="a"),
                        right=Primitive(
                            operator="+",
                            left=Reference(name="b"),
                            right=Reference(name="c")
                        )
                    )
                )
            )
        )
        result = cse_program(term)
        assert isinstance(result, Let)
        b_let = result.body
        assert isinstance(b_let, Let)
        assert b_let.bindings[0] == ("b", Reference(name="a"))
        c_let = b_let.body
        assert isinstance(c_let, Let)
        assert c_let.bindings[0] == ("c", Reference(name="a"))

    def test_cse_apply(self) -> None:
        # Cover line 178: Apply case in cse
        xx: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Apply(
            target=Reference(name="f"),
            arguments=(xx, xx)
        )
        result = cse_program(term)
        assert isinstance(result, Apply)

    def test_cse_store(self) -> None:
        # Cover line 190: Store case in cse
        term: Term = Store(
            base=Reference(name="b"),
            index=0,
            value=Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2))
        )
        result = cse_program(term)
        assert isinstance(result, Store)

    def test_cse_branch(self) -> None:
        # Cover Branch case in cse
        xx: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Branch(
            operator="<",
            left=Reference(name="x"),
            right=Immediate(value=0),
            consequent=xx,
            otherwise=Immediate(value=0)
        )
        result = cse_program(term)
        assert isinstance(result, Branch)

    def test_cse_load(self) -> None:
        # Cover Load case in cse
        term: Term = Load(base=Reference(name="b"), index=0)
        result = cse_program(term)
        assert result == term

    def test_cse_begin(self) -> None:
        # Cover Begin case in cse
        term: Term = Begin(
            effects=(Store(base=Reference(name="b"), index=0, value=Immediate(value=1)),),
            value=Immediate(value=0)
        )
        result = cse_program(term)
        assert isinstance(result, Begin)


# ---------------------------------------------------------------------------
# CSE + Copy Propagation (full pipeline, no DCE)
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_proposal_example(self) -> None:
        # (let ([a (* x x)]) (let ([b (* x x)]) (+ a b)))
        # result: (let ([a (* x x)]) (let ([b a]) (+ a a)))
        xx: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Let(
            bindings=(("a", xx),),
            body=Let(
                bindings=(("b", xx),),
                body=Primitive(operator="+", left=Reference(name="a"), right=Reference(name="b"))
            )
        )
        result = run(term)
        assert isinstance(result, Let)
        assert result.bindings[0] == ("a", xx)
        inner = result.body
        assert isinstance(inner, Let)
        assert inner.bindings[0] == ("b", Reference(name="a"))
        assert inner.body == Primitive(
            operator="+",
            left=Reference(name="a"),
            right=Reference(name="a")
        )

    def test_constant_and_copy_together(self) -> None:
        # (let ([x 3]) (let ([y x]) (+ y y)))
        # result: (let ([x 3]) (let ([y 3]) 6))
        term: Term = Let(
            bindings=(("x", Immediate(value=3)),),
            body=Let(
                bindings=(("y", Reference(name="x")),),
                body=Primitive(operator="+", left=Reference(name="y"), right=Reference(name="y"))
            )
        )
        result = run(term)
        assert result == Let(
            bindings=(("x", Immediate(value=3)),),
            body=Let(
                bindings=(("y", Immediate(value=3)),),
                body=Immediate(value=6)
            )
        )

    def test_no_change_on_already_optimal(self) -> None:
        term: Term = Immediate(value=42)
        assert run(term) == Immediate(value=42)

    def test_branch_condition_constant_folded(self) -> None:
        # (if (< 1 2) (* x x) (* x x))  ->  (* x x)
        xx: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Branch(
            operator="<",
            left=Immediate(value=1),
            right=Immediate(value=2),
            consequent=xx,
            otherwise=xx
        )
        result = run(term)
        assert result == xx

    def test_begin_effects_preserved(self) -> None:
        effect: Term = Store(base=Reference(name="b"), index=0, value=Immediate(value=1))
        term: Term = Begin(
            effects=(effect,),
            value=Immediate(value=0)
        )
        result = run(term)
        assert isinstance(result, Begin)
        assert len(result.effects) == 1

    def test_nested_primitives_cse(self) -> None:
        # (let ([a (+ x y)]) (let ([b (+ x y)]) (+ a b)))
        # result: (let ([a (+ x y)]) (let ([b a]) (+ a a)))
        xy: Term = Primitive(operator="+", left=Reference(name="x"), right=Reference(name="y"))
        term: Term = Let(
            bindings=(("a", xy),),
            body=Let(
                bindings=(("b", xy),),
                body=Primitive(operator="+", left=Reference(name="a"), right=Reference(name="b"))
            )
        )
        result = run(term)
        assert isinstance(result, Let)
        assert result.bindings[0] == ("a", xy)
        inner = result.body
        assert isinstance(inner, Let)
        assert inner.bindings[0] == ("b", Reference(name="a"))
        assert inner.body == Primitive(
            operator="+",
            left=Reference(name="a"),
            right=Reference(name="a")
        )


# ---------------------------------------------------------------------------
# simplify: Load and Allocate cases (lines 110-114)
# ---------------------------------------------------------------------------

class TestSimplifyLoadAllocate:

    def test_load_is_simplified(self) -> None:
        # Load base should be simplified
        term: Term = Load(base=Reference(name="b"), index=0)
        result = simplify(term)
        assert result == Load(base=Reference(name="b"), index=0)

    def test_load_base_reference_propagated(self) -> None:
        # (let ([x b]) (load x 0))  ->  (let ([x b]) (load b 0))
        term: Term = Let(
            bindings=(("x", Reference(name="b")),),
            body=Load(base=Reference(name="x"), index=1)
        )
        result = simplify(term)
        assert isinstance(result, Let)
        assert result.body == Load(base=Reference(name="b"), index=1)

    def test_allocate_is_unchanged(self) -> None:
        # Allocate has no subterms to simplify
        term: Term = Allocate(count=4)
        result = simplify(term)
        assert result == Allocate(count=4)


# ---------------------------------------------------------------------------
# optimize_program (lines 209-218)
# ---------------------------------------------------------------------------

class TestOptimizeProgram:

    def test_optimize_program_constant_fold(self) -> None:
        # Program with a foldable expression converges in one iteration
        prog = Program(
            parameters=(),
            body=Primitive(operator="+", left=Immediate(value=2), right=Immediate(value=3))
        )
        result = optimize_program(prog)
        assert result.body == Immediate(value=5)

    def test_optimize_program_cse_and_copy(self) -> None:
        # (program () (let ([a (* x x)]) (let ([b (* x x)]) (+ a b))))
        xx: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        prog = Program(
            parameters=("x",),
            body=Let(
                bindings=(("a", xx),),
                body=Let(
                    bindings=(("b", xx),),
                    body=Primitive(operator="+", left=Reference(name="a"), right=Reference(name="b"))
                )
            )
        )
        result = optimize_program(prog)
        assert isinstance(result.body, Let)

    def test_optimize_program_already_optimal(self) -> None:
        # A program that is already at fixed point should return unchanged
        prog = Program(
            parameters=(),
            body=Immediate(value=99)
        )
        result = optimize_program(prog)
        assert result.body == Immediate(value=99)

    def test_optimize_program_preserves_parameters(self) -> None:
        prog = Program(
            parameters=("a", "b"),
            body=Primitive(operator="+", left=Reference(name="a"), right=Reference(name="b"))
        )
        result = optimize_program(prog)
        assert result.parameters == prog.parameters