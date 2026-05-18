from collections.abc import Callable

from L3.inlining import (count_uses, inline_program, inline_term,
                        is_eligible, size)
from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Immediate,
                       Let, LetRec, Load, Primitive, Program, Reference,
                       Store, Term)


def _make_fresh() -> Callable[[str], str]:
    count = [0]
    seen: set[str] = set()

    def fresh(hint: str) -> str:
        while True:
            name = f"{hint}_{count[0]}"
            count[0] += 1
            if name not in seen:
                seen.add(name)
                return name

    return fresh


def _prog(body: Term, params: list[str] | None = None) -> Program:
    return Program(parameters=params or [], body=body)


def _inline(body: Term, params: list[str] | None = None, threshold: int = 5) -> Term:
    return inline_program(_prog(body, params), _make_fresh(), threshold).body


def _sq(var: str = "x") -> Abstract:
    """(lambda (x) (* x x))"""
    return Abstract(
        parameters=[var],
        body=Primitive(operator="*", left=Reference(name=var), right=Reference(name=var)),
    )

class TestSize:
    def test_immediate(self):
        assert size(Immediate(value=1)) == 1

    def test_reference(self):
        assert size(Reference(name="x")) == 1

    def test_allocate(self):
        assert size(Allocate(count=1)) == 1

    def test_primitive(self):
        assert size(Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2))) == 3

    def test_abstract(self):
        assert size(Abstract(parameters=["x"], body=Reference(name="x"))) == 2

    def test_apply(self):
        assert size(Apply(target=Reference(name="f"), arguments=[Immediate(value=1)])) == 3

    def test_let_single_binding(self):
        expr = Let(bindings=[("x", Immediate(value=1))], body=Reference(name="x"))
        assert size(expr) == 3

    def test_letrec(self):
        expr = LetRec(bindings=[("f", Abstract(parameters=["x"], body=Reference(name="x")))],
                      body=Reference(name="f"))
        assert size(expr) == 4

    def test_branch(self):
        expr = Branch(operator="<", left=Immediate(value=1), right=Immediate(value=2),
                      consequent=Immediate(value=3), otherwise=Immediate(value=4))
        assert size(expr) == 5

    def test_load(self):
        assert size(Load(base=Reference(name="p"), index=0)) == 2

    def test_store(self):
        assert size(Store(base=Reference(name="p"), index=0, value=Immediate(value=1))) == 3

    def test_begin(self):
        expr = Begin(effects=[Immediate(value=0)], value=Immediate(value=1))
        assert size(expr) == 3

    def test_nested(self):
        inner = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        outer = Primitive(operator="*", left=inner, right=inner)
        assert size(outer) == 7

class TestCountUses:
    def test_reference_match(self):
        assert count_uses("x", Reference(name="x")) == 1

    def test_reference_no_match(self):
        assert count_uses("x", Reference(name="y")) == 0

    def test_immediate(self):
        assert count_uses("x", Immediate(value=1)) == 0

    def test_allocate(self):
        assert count_uses("x", Allocate(count=1)) == 0

    def test_primitive(self):
        expr = Primitive(operator="+", left=Reference(name="x"), right=Reference(name="x"))
        assert count_uses("x", expr) == 2

    def test_abstract_body(self):
        lam = Abstract(parameters=["y"], body=Reference(name="x"))
        assert count_uses("x", lam) == 1

    def test_apply(self):
        expr = Apply(target=Reference(name="f"), arguments=[Reference(name="x")])
        assert count_uses("x", expr) == 1
        assert count_uses("f", expr) == 1

    def test_let(self):
        expr = Let(bindings=[("y", Reference(name="x"))], body=Reference(name="x"))
        assert count_uses("x", expr) == 2

    def test_letrec(self):
        expr = LetRec(bindings=[("f", Reference(name="x"))], body=Reference(name="x"))
        assert count_uses("x", expr) == 2

    def test_branch(self):
        expr = Branch(operator="<", left=Reference(name="x"), right=Immediate(value=0),
                      consequent=Reference(name="x"), otherwise=Immediate(value=0))
        assert count_uses("x", expr) == 2

    def test_load(self):
        assert count_uses("p", Load(base=Reference(name="p"), index=0)) == 1

    def test_store(self):
        expr = Store(base=Reference(name="p"), index=0, value=Reference(name="p"))
        assert count_uses("p", expr) == 2

    def test_begin(self):
        expr = Begin(effects=[Reference(name="x")], value=Reference(name="x"))
        assert count_uses("x", expr) == 2

    def test_zero_uses(self):
        assert count_uses("z", Immediate(value=99)) == 0


class TestIsEligible:
    def test_small_function_eligible(self):
        func = Abstract(parameters=["x"], body=Reference(name="x"))
        assert is_eligible("f", func, Immediate(value=0), threshold=5)

    def test_large_function_single_use_eligible(self):
        large_body = Primitive(
            operator="+",
            left=Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x")),
            right=Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x")),
        )
        func = Abstract(parameters=["x"], body=large_body)
        scope = Apply(target=Reference(name="f"), arguments=[Immediate(value=1)])
        assert is_eligible("f", func, scope, threshold=0)

    def test_large_function_multi_use_not_eligible(self):
        large_body = Primitive(
            operator="+",
            left=Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x")),
            right=Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x")),
        )
        func = Abstract(parameters=["x"], body=large_body)
        scope = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
        )
        assert not is_eligible("f", func, scope, threshold=0)

    def test_threshold_zero_only_single_use(self):
        func = Abstract(parameters=["x"], body=Reference(name="x"))
        single_use = Apply(target=Reference(name="f"), arguments=[Immediate(value=1)])
        multi_use = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
        )
        assert is_eligible("f", func, single_use, threshold=0)
        assert not is_eligible("f", func, multi_use, threshold=0)

class TestInlineTermPassthrough:
    def test_immediate(self):
        fresh = _make_fresh()
        t = Immediate(value=1)
        assert inline_term(t, {}, fresh, 5) == t

    def test_reference(self):
        fresh = _make_fresh()
        t = Reference(name="x")
        assert inline_term(t, {}, fresh, 5) == t

    def test_allocate(self):
        fresh = _make_fresh()
        t = Allocate(count=1)
        assert inline_term(t, {}, fresh, 5) == t

    def test_unknown_call_unchanged(self):
        fresh = _make_fresh()
        t = Apply(target=Reference(name="f"), arguments=[Immediate(value=1)])
        result = inline_term(t, {}, fresh, 5)
        assert isinstance(result, Apply)
        assert isinstance(result.target, Reference)
        assert result.target.name == "f"

    def test_dynamic_call_unchanged(self):
        fresh = _make_fresh()
        lam = Abstract(parameters=["x"], body=Reference(name="x"))
        t = Apply(target=lam, arguments=[Immediate(value=1)])
        result = inline_term(t, {}, fresh, 5)
        assert isinstance(result, Apply)
        assert isinstance(result.target, Abstract)


class TestInlineTermSingleUse:
    def test_single_use_inlined(self):
        body = Apply(target=Reference(name="f"), arguments=[Immediate(value=5)])
        expr = Let(bindings=[("f", _sq())], body=body)
        result = inline_term(expr, {}, _make_fresh(), threshold=0)
        assert count_uses("f", result) == 0

    def test_multi_use_not_inlined_at_threshold_zero(self):
        body = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=3)]),
        )
        expr = Let(bindings=[("f", _sq())], body=body)
        result = inline_term(expr, {}, _make_fresh(), threshold=0)
        assert isinstance(result, Let)
        assert any(name == "f" for name, _ in result.bindings)

class TestInlineTermSmallFunction:
    def test_small_function_inlined_at_all_sites(self):
        identity = Abstract(parameters=["x"], body=Reference(name="x"))
        body = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
        )
        expr = Let(bindings=[("f", identity)], body=body)
        result = inline_term(expr, {}, _make_fresh(), threshold=5)
        assert not isinstance(result, Let) or all(name != "f" for name, _ in result.bindings)

    def test_threshold_zero_disables_small_function(self):
        identity = Abstract(parameters=["x"], body=Reference(name="x"))
        body = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
        )
        expr = Let(bindings=[("f", identity)], body=body)
        result = inline_term(expr, {}, _make_fresh(), threshold=0)
        assert isinstance(result, Let)
        assert any(name == "f" for name, _ in result.bindings)

    def test_large_threshold_inlines_everything(self):
        body = Apply(target=Reference(name="f"), arguments=[Immediate(value=1)])
        expr = Let(bindings=[("f", _sq())], body=body)
        result = inline_term(expr, {}, _make_fresh(), threshold=9999)
        assert not isinstance(result, Let) or all(name != "f" for name, _ in result.bindings)


class TestInlineTermNoCapture:
    def test_fresh_names_introduced(self):
        identity = Abstract(parameters=["x"], body=Reference(name="x"))
        expr = Let(
            bindings=[("f", identity)],
            body=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
        )
        result = inline_term(expr, {}, _make_fresh(), threshold=5)
        assert isinstance(result, Let)
        assert result.bindings[0][0] != "x"

    def test_two_inlines_get_distinct_names(self):
        identity = Abstract(parameters=["x"], body=Reference(name="x"))
        body = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
        )
        expr = Let(bindings=[("f", identity)], body=body)
        result = inline_term(expr, {}, _make_fresh(), threshold=5)

        def all_bound_names(t: Term) -> list[str]:
            match t:
                case Let(bindings=bs, body=b):
                    return [n for n, _ in bs] + all_bound_names(b)
                case Primitive(left=l, right=r):
                    return all_bound_names(l) + all_bound_names(r)
                case _:
                    return []

        names = all_bound_names(result)
        assert len(names) == len(set(names))


class TestInlineTermOtherTypes:
    def test_letrec_not_inlined(self):
        # LetRec bodies are recursed but functions not registered for inlining
        lam = Abstract(parameters=["x"], body=Reference(name="x"))
        expr = LetRec(
            bindings=[("f", lam)],
            body=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
        )
        result = inline_term(expr, {}, _make_fresh(), threshold=9999)
        assert isinstance(result, LetRec)

    def test_abstract_body_recursed(self):
        inner = Let(
            bindings=[("g", Abstract(parameters=["y"], body=Reference(name="y")))],
            body=Apply(target=Reference(name="g"), arguments=[Immediate(value=1)]),
        )
        lam = Abstract(parameters=["x"], body=inner)
        result = inline_term(lam, {}, _make_fresh(), threshold=5)
        assert isinstance(result, Abstract)

    def test_primitive_recursed(self):
        result = inline_term(
            Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2)),
            {}, _make_fresh(), threshold=5,
        )
        assert isinstance(result, Primitive)

    def test_branch_recursed(self):
        result = inline_term(
            Branch(operator="<", left=Immediate(value=0), right=Immediate(value=1),
                   consequent=Immediate(value=1), otherwise=Immediate(value=0)),
            {}, _make_fresh(), threshold=5,
        )
        assert isinstance(result, Branch)

    def test_load_recursed(self):
        result = inline_term(
            Load(base=Reference(name="p"), index=0), {}, _make_fresh(), threshold=5
        )
        assert isinstance(result, Load)

    def test_store_recursed(self):
        result = inline_term(
            Store(base=Reference(name="p"), index=0, value=Immediate(value=1)),
            {}, _make_fresh(), threshold=5,
        )
        assert isinstance(result, Store)

    def test_begin_recursed(self):
        result = inline_term(
            Begin(effects=[Immediate(value=0)], value=Immediate(value=1)),
            {}, _make_fresh(), threshold=5,
        )
        assert isinstance(result, Begin)



class TestInlineProgram:
    def test_params_preserved(self):
        prog = _prog(Reference(name="n"), params=["n"])
        result = inline_program(prog, _make_fresh())
        assert list(result.parameters) == ["n"]

    def test_single_use_inlined(self):
        result = _inline(
            Let(
                bindings=[("f", _sq())],
                body=Apply(target=Reference(name="f"), arguments=[Immediate(value=5)]),
            )
        )
        # f binding dropped after inlining
        assert count_uses("f", result) == 0

    def test_threshold_zero_respects_use_count(self):
        body = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=3)]),
        )
        result = _inline(Let(bindings=[("f", _sq())], body=body), threshold=0)
        assert isinstance(result, Let)
        assert any(name == "f" for name, _ in result.bindings)

    def test_threshold_large_inlines_all(self):
        body = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=3)]),
        )
        result = _inline(Let(bindings=[("f", _sq())], body=body), threshold=9999)
        assert not isinstance(result, Let) or all(name != "f" for name, _ in result.bindings)

    def test_synergy_with_constant_folding(self):
        # let square = (lambda (x) (* x x)) in (square 5)
        # inline → let x_N = 5 in (* x_N x_N)
        # then constant folding can reduce to 25
        from L3.cse import simplify
        inlined = _inline(
            Let(
                bindings=[("square", _sq())],
                body=Apply(target=Reference(name="square"), arguments=[Immediate(value=5)]),
            )
        )
        folded = simplify(inlined)
        # simplify may leave a Let wrapper; the body should be Immediate(25)
        assert folded == Immediate(value=25) or (
            isinstance(folded, Let)
            and folded.body == Immediate(value=25)
        )

    def test_no_eligible_call_unchanged(self):
        # no function bindings at all — output should be the same
        body = Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2))
        result = _inline(body)
        assert result == body


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------

class TestCoverageGaps:


    def test_let_non_abstract_binding_not_registered(self):
        expr = Let(bindings=[("x", Immediate(value=1))], body=Reference(name="x"))
        result = inline_term(expr, {}, _make_fresh(), threshold=5)
        assert isinstance(result, Let)
        assert result.bindings[0][1] == Immediate(value=1)

    def test_let_primitive_binding_not_registered(self):
        expr = Let(
            bindings=[("x", Primitive(operator="+",
                                      left=Immediate(value=1), right=Immediate(value=2)))],
            body=Reference(name="x"),
        )
        result = inline_term(expr, {}, _make_fresh(), threshold=5)
        assert isinstance(result, Let)

    def test_known_function_arity_mismatch_not_inlined(self):
        identity = Abstract(parameters=["x"], body=Reference(name="x"))
        expr = Let(
            bindings=[("f", identity)],
            body=Apply(
                target=Reference(name="f"),
                arguments=[Immediate(value=1), Immediate(value=2)],
            ),
        )
        result = inline_term(expr, {}, _make_fresh(), threshold=9999)
        assert isinstance(result, Let)
        assert isinstance(result.body, Apply)
        assert isinstance(result.body.target, Reference)
        assert result.body.target.name == "f"

    def test_known_function_not_eligible_not_inlined(self):
        large = Abstract(
            parameters=["x"],
            body=Primitive(
                operator="+",
                left=Primitive(operator="*",
                               left=Reference(name="x"), right=Reference(name="x")),
                right=Primitive(operator="*",
                               left=Reference(name="x"), right=Reference(name="x")),
            ),
        )
        body = Primitive(
            operator="+",
            left=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
            right=Apply(target=Reference(name="f"), arguments=[Immediate(value=2)]),
        )
        expr = Let(bindings=[("f", large)], body=body)
        result = inline_term(expr, {}, _make_fresh(), threshold=0)
        assert isinstance(result, Let)
        assert any(name == "f" for name, _ in result.bindings)