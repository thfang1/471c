from L3.cse import cse, is_pure, simplify
from L3.cse import optimize_program as optimize_program
from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Immediate,
                       Let, Load, Primitive, Program, Reference, Store, Term)


def _prog(body: Term, params: list[str] | None = None) -> Program:
    return Program(parameters=params or [], body=body)


def _opt(body: Term, params: list[str] | None = None) -> Term:
    return optimize_program(_prog(body, params)).body


class TestIsPure:
    def test_immediate(self):
        assert is_pure(Immediate(value=1))

    def test_reference(self):
        assert is_pure(Reference(name="x"))

    def test_primitive_pure_operands(self):
        assert is_pure(
            Primitive(operator="+", left=Immediate(value=1), right=Reference(name="x"))
        )

    def test_primitive_nested_pure(self):
        inner = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        assert is_pure(Primitive(operator="+", left=inner, right=Immediate(value=1)))

    def test_primitive_impure_child(self):
        assert not is_pure(
            Primitive(operator="+", left=Allocate(count=1), right=Immediate(value=1))
        )

    def test_allocate(self):
        assert not is_pure(Allocate(count=1))

    def test_load(self):
        assert not is_pure(Load(base=Reference(name="p"), index=0))

    def test_store(self):
        assert not is_pure(
            Store(base=Reference(name="p"), index=0, value=Immediate(value=1))
        )

    def test_abstract(self):
        assert not is_pure(Abstract(parameters=["x"], body=Reference(name="x")))

    def test_apply(self):
        assert not is_pure(Apply(target=Reference(name="f"), arguments=[]))

    def test_branch(self):
        assert not is_pure(
            Branch(operator="<", left=Immediate(value=1), right=Immediate(value=2),
                   consequent=Immediate(value=1), otherwise=Immediate(value=0))
        )

    def test_begin(self):
        assert not is_pure(Begin(effects=[], value=Immediate(value=0)))


class TestSimplifyImmediate:
    def test_unchanged(self):
        t = Immediate(value=42)
        assert simplify(t) == t

    def test_negative(self):
        t = Immediate(value=-7)
        assert simplify(t) == t


class TestSimplifyReference:
    def test_unbound_unchanged(self):
        assert simplify(Reference(name="x")) == Reference(name="x")

    def test_constant_propagation(self):
        assert simplify(Reference(name="x"), {"x": Immediate(value=5)}) == Immediate(value=5)

    def test_copy_propagation(self):
        assert simplify(Reference(name="x"), {"x": Reference(name="y")}) == Reference(name="y")


class TestSimplifyLet:
    def test_constant_propagated_into_body(self):
        expr = Let(bindings=[("x", Immediate(value=1))], body=Reference(name="x"))
        result = simplify(expr)
        assert isinstance(result, Let)
        assert result.body == Immediate(value=1)

    def test_copy_propagated_into_body(self):
        expr = Let(bindings=[("x", Reference(name="y"))], body=Reference(name="x"))
        result = simplify(expr, {"y": Immediate(value=3)})
        assert isinstance(result, Let)
        assert result.body == Immediate(value=3)

    def test_complex_rhs_not_propagated(self):
        expr = Let(
            bindings=[("x", Primitive(operator="+",
                                      left=Reference(name="a"),
                                      right=Reference(name="b")))],
            body=Reference(name="x"),
        )
        result = simplify(expr)
        assert isinstance(result, Let)
        assert result.body == Reference(name="x")

    def test_sequential_propagation(self):
        expr = Let(
            bindings=[("x", Immediate(value=1)), ("y", Reference(name="x"))],
            body=Reference(name="y"),
        )
        result = simplify(expr)
        assert isinstance(result, Let)
        assert result.body == Immediate(value=1)

    def test_rebinding_shadows_env(self):
        expr = Let(
            bindings=[("x", Primitive(operator="+",
                                      left=Immediate(value=1),
                                      right=Immediate(value=2)))],
            body=Reference(name="x"),
        )
        result = simplify(expr, {"x": Immediate(value=99)})
        assert isinstance(result, Let)
        assert result.bindings[0][1] == Immediate(value=3)
        assert result.body == Immediate(value=3)


class TestSimplifyPrimitive:
    def test_add(self):
        assert simplify(
            Primitive(operator="+", left=Immediate(value=3), right=Immediate(value=4))
        ) == Immediate(value=7)

    def test_sub(self):
        assert simplify(
            Primitive(operator="-", left=Immediate(value=10), right=Immediate(value=3))
        ) == Immediate(value=7)

    def test_mul(self):
        assert simplify(
            Primitive(operator="*", left=Immediate(value=6), right=Immediate(value=7))
        ) == Immediate(value=42)

    def test_unknown_operand_not_folded(self):
        result = simplify(
            Primitive(operator="+", left=Reference(name="x"), right=Immediate(value=1))
        )
        assert isinstance(result, Primitive)

    def test_operand_propagated_then_folded(self):
        result = simplify(
            Primitive(operator="+", left=Reference(name="x"), right=Immediate(value=1)),
            {"x": Immediate(value=4)},
        )
        assert result == Immediate(value=5)


class TestSimplifyBranch:
    def test_less_than_true(self):
        assert simplify(
            Branch(operator="<", left=Immediate(value=1), right=Immediate(value=2),
                   consequent=Immediate(value=10), otherwise=Immediate(value=20))
        ) == Immediate(value=10)

    def test_less_than_false(self):
        assert simplify(
            Branch(operator="<", left=Immediate(value=2), right=Immediate(value=1),
                   consequent=Immediate(value=10), otherwise=Immediate(value=20))
        ) == Immediate(value=20)

    def test_equal_true(self):
        assert simplify(
            Branch(operator="==", left=Immediate(value=5), right=Immediate(value=5),
                   consequent=Immediate(value=1), otherwise=Immediate(value=0))
        ) == Immediate(value=1)

    def test_equal_false(self):
        assert simplify(
            Branch(operator="==", left=Immediate(value=5), right=Immediate(value=6),
                   consequent=Immediate(value=1), otherwise=Immediate(value=0))
        ) == Immediate(value=0)

    def test_unknown_condition_preserved(self):
        result = simplify(
            Branch(operator="<", left=Reference(name="x"), right=Immediate(value=2),
                   consequent=Immediate(value=1), otherwise=Immediate(value=0))
        )
        assert isinstance(result, Branch)

    def test_children_simplified(self):
        result = simplify(
            Branch(
                operator="<", left=Reference(name="x"), right=Immediate(value=2),
                consequent=Primitive(operator="+",
                                     left=Immediate(value=1), right=Immediate(value=2)),
                otherwise=Immediate(value=0),
            )
        )
        assert isinstance(result, Branch)
        assert result.consequent == Immediate(value=3)


class TestSimplifyAbstract:
    def test_body_simplified(self):
        result = simplify(
            Abstract(parameters=["x"],
                     body=Primitive(operator="+",
                                    left=Immediate(value=1), right=Immediate(value=2)))
        )
        assert isinstance(result, Abstract)
        assert result.body == Immediate(value=3)

    def test_parameter_shadows_env(self):
        result = simplify(
            Abstract(parameters=["x"], body=Reference(name="x")),
            {"x": Immediate(value=99)},
        )
        assert isinstance(result, Abstract)
        assert result.body == Reference(name="x")

    def test_free_variable_propagated(self):
        result = simplify(
            Abstract(parameters=["x"], body=Reference(name="y")),
            {"y": Immediate(value=5)},
        )
        assert isinstance(result, Abstract)
        assert result.body == Immediate(value=5)


class TestSimplifyOther:
    def test_apply_args_simplified(self):
        result = simplify(
            Apply(
                target=Reference(name="f"),
                arguments=[Primitive(operator="+",
                                     left=Immediate(value=1), right=Immediate(value=2))],
            )
        )
        assert isinstance(result, Apply)
        assert result.arguments[0] == Immediate(value=3)

    def test_begin_effects_simplified(self):
        result = simplify(
            Begin(
                effects=[Primitive(operator="+",
                                   left=Immediate(value=1), right=Immediate(value=2))],
                value=Immediate(value=0),
            )
        )
        assert isinstance(result, Begin)
        assert result.effects[0] == Immediate(value=3)

    def test_load_base_propagated(self):
        result = simplify(Load(base=Reference(name="p"), index=0), {"p": Reference(name="q")})
        assert isinstance(result, Load)
        assert result.base == Reference(name="q")

    def test_store_value_folded(self):
        result = simplify(
            Store(base=Reference(name="p"), index=0,
                  value=Primitive(operator="+",
                                  left=Immediate(value=1), right=Immediate(value=2)))
        )
        assert isinstance(result, Store)
        assert result.value == Immediate(value=3)

    def test_allocate_unchanged(self):
        t = Allocate(count=3)
        assert simplify(t) == t


class TestCSE:
    def test_immediate_passthrough(self):
        assert cse(Immediate(value=1)) == Immediate(value=1)

    def test_reference_passthrough(self):
        assert cse(Reference(name="x")) == Reference(name="x")

    def test_allocate_passthrough(self):
        assert cse(Allocate(count=2)) == Allocate(count=2)

    def test_no_duplicate_not_replaced(self):
        expr = Let(
            bindings=[("x", Primitive(operator="*",
                                      left=Reference(name="a"), right=Reference(name="a")))],
            body=Reference(name="x"),
        )
        result = cse(expr)
        assert isinstance(result, Let)
        assert isinstance(result.bindings[0][1], Primitive)
        assert result.body == Reference(name="x")

    def test_duplicate_replaced_with_reference(self):
        sq = Primitive(operator="*", left=Reference(name="a"), right=Reference(name="a"))
        expr = Let(
            bindings=[("x", sq), ("y", sq)],
            body=Primitive(operator="+", left=Reference(name="x"), right=Reference(name="y")),
        )
        result = cse(expr)
        assert isinstance(result, Let)
        assert result.bindings[1][1] == Reference(name="x")

    def test_immediate_not_deduplicated(self):
        expr = Let(
            bindings=[("x", Immediate(value=1)), ("y", Immediate(value=1))],
            body=Reference(name="x"),
        )
        result = cse(expr)
        assert isinstance(result, Let)
        assert result.bindings[1][1] == Immediate(value=1)

    def test_reference_not_deduplicated(self):
        expr = Let(
            bindings=[("x", Reference(name="a")), ("y", Reference(name="a"))],
            body=Reference(name="x"),
        )
        result = cse(expr)
        assert isinstance(result, Let)
        assert result.bindings[1][1] == Reference(name="a")

    def test_impure_not_deduplicated(self):
        expr = Let(
            bindings=[("x", Allocate(count=1)), ("y", Allocate(count=1))],
            body=Reference(name="x"),
        )
        result = cse(expr)
        assert isinstance(result, Let)
        assert isinstance(result.bindings[1][1], Allocate)

    def test_lambda_boundary_isolates(self):
        sq = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        expr = Let(
            bindings=[
                ("f", Abstract(parameters=["x"], body=sq)),
                ("g", Abstract(parameters=["x"], body=sq)),
            ],
            body=Reference(name="f"),
        )
        result = cse(expr)
        assert isinstance(result, Let)
        assert isinstance(result.bindings[0][1].body, Primitive)  # type: ignore[union-attr]
        assert isinstance(result.bindings[1][1].body, Primitive)  # type: ignore[union-attr]

    def test_primitive_recursed(self):
        result = cse(
            Primitive(
                operator="+",
                left=Primitive(operator="*",
                               left=Reference(name="x"), right=Reference(name="x")),
                right=Immediate(value=1),
            )
        )
        assert isinstance(result, Primitive)

    def test_branch_recursed(self):
        result = cse(
            Branch(operator="<", left=Immediate(value=0), right=Immediate(value=1),
                   consequent=Immediate(value=1), otherwise=Immediate(value=0))
        )
        assert isinstance(result, Branch)

    def test_apply_recursed(self):
        result = cse(Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]))
        assert isinstance(result, Apply)

    def test_begin_recursed(self):
        result = cse(Begin(effects=[Immediate(value=0)], value=Immediate(value=1)))
        assert isinstance(result, Begin)

    def test_load_recursed(self):
        result = cse(Load(base=Reference(name="p"), index=0))
        assert isinstance(result, Load)

    def test_store_recursed(self):
        result = cse(Store(base=Reference(name="p"), index=0, value=Immediate(value=1)))
        assert isinstance(result, Store)


class TestOptimizeProgram:
    def test_constant_folded(self):
        assert _opt(
            Primitive(operator="+", left=Immediate(value=3), right=Immediate(value=4))
        ) == Immediate(value=7)

    def test_dead_branch_eliminated(self):
        assert _opt(
            Branch(operator="<", left=Immediate(value=1), right=Immediate(value=2),
                   consequent=Immediate(value=99), otherwise=Immediate(value=0))
        ) == Immediate(value=99)

    def test_copy_propagated_into_body(self):
        result = _opt(Let(bindings=[("x", Immediate(value=5))], body=Reference(name="x")))
        assert isinstance(result, Let)
        assert result.body == Immediate(value=5)

    def test_cse_deduplicates_and_copy_propagates(self):
        sq = Primitive(operator="*", left=Reference(name="a"), right=Reference(name="a"))
        body = Let(
            bindings=[("x", sq), ("y", sq)],
            body=Primitive(operator="+", left=Reference(name="x"), right=Reference(name="y")),
        )
        result = _opt(body, params=["a"])
        assert isinstance(result, Let)
        assert isinstance(result.body, Primitive)

    def test_nested_constant_folding(self):
        assert _opt(
            Primitive(
                operator="+",
                left=Primitive(operator="*", left=Immediate(value=2), right=Immediate(value=3)),
                right=Primitive(operator="-", left=Immediate(value=10), right=Immediate(value=4)),
            )
        ) == Immediate(value=12)

    def test_fixed_point(self):
        assert _opt(Immediate(value=42)) == Immediate(value=42)

    def test_params_preserved(self):
        result = optimize_program(_prog(Reference(name="n"), params=["n"]))
        assert list(result.parameters) == ["n"]

    def test_allocate_preserved(self):
        result = _opt(
            Let(bindings=[("b", Allocate(count=1))],
                body=Load(base=Reference(name="b"), index=0))
        )
        assert isinstance(result, Let)
        assert isinstance(result.bindings[0][1], Allocate)

    def test_begin_preserved(self):
        result = _opt(
            Begin(
                effects=[Store(base=Reference(name="p"), index=0, value=Immediate(value=1))],
                value=Immediate(value=0),
            ),
            params=["p"],
        )
        assert isinstance(result, Begin)