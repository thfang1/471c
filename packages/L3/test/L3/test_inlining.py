from L3.inlining import (ast_size, count_uses,
                          inline, inline_program, optimize_program,
                          substitute, uniqify_program)
from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Immediate,
                        Let, Load, Primitive, Program, Reference, Store, Term)


class TestAstSize:

    def test_immediate(self) -> None:
        assert ast_size(Immediate(value=1)) == 1

    def test_reference(self) -> None:
        assert ast_size(Reference(name="x")) == 1

    def test_allocate(self) -> None:
        assert ast_size(Allocate(count=1)) == 1

    def test_primitive(self) -> None:
        # 1 + 1 + 1 = 3
        term: Term = Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2))
        assert ast_size(term) == 3

    def test_abstract(self) -> None:
        # 1 (Abstract) + 1 (body) = 2
        term: Term = Abstract(parameters=("x",), body=Reference(name="x"))
        assert ast_size(term) == 2

    def test_apply(self) -> None:
        # 1 (Apply) + 1 (target) + 1 (arg) = 3
        term: Term = Apply(target=Reference(name="f"), arguments=(Immediate(value=1),))
        assert ast_size(term) == 3

    def test_let(self) -> None:
        # 1 (Let) + 1 (binding val) + 1 (body) = 3
        term: Term = Let(
            bindings=(("x", Immediate(value=1)),),
            body=Reference(name="x")
        )
        assert ast_size(term) == 3

    def test_branch(self) -> None:
        # 1 + 1 + 1 + 1 + 1 = 5
        term: Term = Branch(
            operator="<",
            left=Immediate(value=1),
            right=Immediate(value=2),
            consequent=Immediate(value=3),
            otherwise=Immediate(value=4)
        )
        assert ast_size(term) == 5

    def test_begin(self) -> None:
        # 1 (Begin) + 1 (effect) + 1 (value) = 3
        term: Term = Begin(
            effects=(Immediate(value=0),),
            value=Immediate(value=1)
        )
        assert ast_size(term) == 3

    def test_load(self) -> None:
        # 1 (Load) + 1 (base) = 2
        term: Term = Load(base=Reference(name="b"), index=0)
        assert ast_size(term) == 2

    def test_store(self) -> None:
        # 1 (Store) + 1 (base) + 1 (value) = 3
        term: Term = Store(base=Reference(name="b"), index=0, value=Immediate(value=1))
        assert ast_size(term) == 3


class TestCountUses:

    def test_reference_match(self) -> None:
        assert count_uses("x", Reference(name="x")) == 1

    def test_reference_no_match(self) -> None:
        assert count_uses("x", Reference(name="y")) == 0

    def test_immediate(self) -> None:
        assert count_uses("x", Immediate(value=1)) == 0

    def test_allocate(self) -> None:
        assert count_uses("x", Allocate(count=1)) == 0

    def test_primitive(self) -> None:
        term: Term = Primitive(operator="+", left=Reference(name="x"), right=Reference(name="x"))
        assert count_uses("x", term) == 2

    def test_abstract_shadows(self) -> None:
        # x is a parameter, so it should not be counted
        term: Term = Abstract(parameters=("x",), body=Reference(name="x"))
        assert count_uses("x", term) == 0

    def test_abstract_free(self) -> None:
        # y is free in the lambda
        term: Term = Abstract(parameters=("x",), body=Reference(name="y"))
        assert count_uses("y", term) == 1

    def test_apply(self) -> None:
        term: Term = Apply(
            target=Reference(name="f"),
            arguments=(Reference(name="x"), Reference(name="x"))
        )
        assert count_uses("x", term) == 2
        assert count_uses("f", term) == 1

    def test_let_shadowed(self) -> None:
        # x is rebound in inner let, uses before rebinding count
        term: Term = Let(
            bindings=(
                ("y", Reference(name="x")),
                ("x", Immediate(value=1)),
            ),
            body=Reference(name="x")
        )
        # x appears once in binding of y, then is shadowed
        assert count_uses("x", term) == 1

    def test_let_body(self) -> None:
        term: Term = Let(
            bindings=(("y", Immediate(value=1)),),
            body=Reference(name="x")
        )
        assert count_uses("x", term) == 1

    def test_branch(self) -> None:
        term: Term = Branch(
            operator="<",
            left=Reference(name="x"),
            right=Reference(name="x"),
            consequent=Reference(name="x"),
            otherwise=Immediate(value=0)
        )
        assert count_uses("x", term) == 3

    def test_begin(self) -> None:
        term: Term = Begin(
            effects=(Reference(name="x"),),
            value=Reference(name="x")
        )
        assert count_uses("x", term) == 2

    def test_load(self) -> None:
        term: Term = Load(base=Reference(name="x"), index=0)
        assert count_uses("x", term) == 1

    def test_store(self) -> None:
        term: Term = Store(base=Reference(name="x"), index=0, value=Reference(name="x"))
        assert count_uses("x", term) == 2


class TestUniqify:

    def test_let_binding_renamed(self) -> None:
        # (let ([x 1]) x)  ->  (let ([x_0 1]) x_0)
        term: Term = Let(
            bindings=(("x", Immediate(value=1)),),
            body=Reference(name="x")
        )
        result = uniqify_program(term)
        assert isinstance(result, Let)
        name = result.bindings[0][0]
        assert name != "x"
        assert result.body == Reference(name=name)

    def test_two_lets_same_name_get_different_ids(self) -> None:
        # (let ([x 1]) (let ([x 2]) x))
        # Both x bindings should get unique names
        term: Term = Let(
            bindings=(("x", Immediate(value=1)),),
            body=Let(
                bindings=(("x", Immediate(value=2)),),
                body=Reference(name="x")
            )
        )
        result = uniqify_program(term)
        assert isinstance(result, Let)
        outer_name = result.bindings[0][0]
        inner_let = result.body
        assert isinstance(inner_let, Let)
        inner_name = inner_let.bindings[0][0]
        assert outer_name != inner_name
        assert inner_let.body == Reference(name=inner_name)

    def test_abstract_parameters_renamed(self) -> None:
        term: Term = Abstract(parameters=("x",), body=Reference(name="x"))
        result = uniqify_program(term)
        assert isinstance(result, Abstract)
        new_param = result.parameters[0]
        assert new_param != "x"
        assert result.body == Reference(name=new_param)

    def test_free_variable_unchanged(self) -> None:
        # Free variables (not bound in this term) are not renamed
        term: Term = Reference(name="free_var")
        result = uniqify_program(term)
        assert result == Reference(name="free_var")

    def test_load_base_renamed(self) -> None:
        term: Term = Let(
            bindings=(("b", Allocate(count=1)),),
            body=Load(base=Reference(name="b"), index=0)
        )
        result = uniqify_program(term)
        assert isinstance(result, Let)
        new_name = result.bindings[0][0]
        assert result.body == Load(base=Reference(name=new_name), index=0)

    def test_store_renamed(self) -> None:
        term: Term = Let(
            bindings=(("b", Allocate(count=1)),),
            body=Store(base=Reference(name="b"), index=0, value=Immediate(value=1))
        )
        result = uniqify_program(term)
        assert isinstance(result, Let)
        new_name = result.bindings[0][0]
        assert isinstance(result.body, Store)
        assert result.body.base == Reference(name=new_name)

    def test_branch_renamed(self) -> None:
        term: Term = Let(
            bindings=(("x", Immediate(value=1)),),
            body=Branch(
                operator="<",
                left=Reference(name="x"),
                right=Immediate(value=2),
                consequent=Reference(name="x"),
                otherwise=Immediate(value=0)
            )
        )
        result = uniqify_program(term)
        assert isinstance(result, Let)
        new_name = result.bindings[0][0]
        branch = result.body
        assert isinstance(branch, Branch)
        assert branch.left == Reference(name=new_name)
        assert branch.consequent == Reference(name=new_name)

    def test_begin_renamed(self) -> None:
        term: Term = Let(
            bindings=(("x", Immediate(value=1)),),
            body=Begin(
                effects=(Reference(name="x"),),
                value=Reference(name="x")
            )
        )
        result = uniqify_program(term)
        assert isinstance(result, Let)
        new_name = result.bindings[0][0]
        begin = result.body
        assert isinstance(begin, Begin)
        assert begin.effects[0] == Reference(name=new_name)
        assert begin.value == Reference(name=new_name)


class TestSubstitute:

    def test_substitute_reference(self) -> None:
        result = substitute(Reference(name="x"), {"x": Immediate(value=42)})
        assert result == Immediate(value=42)

    def test_substitute_no_match(self) -> None:
        result = substitute(Reference(name="y"), {"x": Immediate(value=42)})
        assert result == Reference(name="y")

    def test_substitute_in_primitive(self) -> None:
        term: Term = Primitive(operator="+", left=Reference(name="x"), right=Immediate(value=1))
        result = substitute(term, {"x": Immediate(value=5)})
        assert result == Primitive(operator="+", left=Immediate(value=5), right=Immediate(value=1))

    def test_substitute_shadowed_by_abstract(self) -> None:
        # x is a parameter of the lambda, should not be substituted
        term: Term = Abstract(parameters=("x",), body=Reference(name="x"))
        result = substitute(term, {"x": Immediate(value=99)})
        assert result == Abstract(parameters=("x",), body=Reference(name="x"))

    def test_substitute_shadowed_by_let(self) -> None:
        # x is rebound in let, should not substitute in body
        term: Term = Let(
            bindings=(("x", Immediate(value=1)),),
            body=Reference(name="x")
        )
        result = substitute(term, {"x": Immediate(value=99)})
        assert isinstance(result, Let)
        assert result.body == Reference(name="x")

    def test_substitute_in_load(self) -> None:
        term: Term = Load(base=Reference(name="b"), index=0)
        result = substitute(term, {"b": Reference(name="c")})
        assert result == Load(base=Reference(name="c"), index=0)

    def test_substitute_in_store(self) -> None:
        term: Term = Store(base=Reference(name="b"), index=0, value=Reference(name="v"))
        result = substitute(term, {"b": Reference(name="c"), "v": Immediate(value=7)})
        assert result == Store(base=Reference(name="c"), index=0, value=Immediate(value=7))

    def test_substitute_in_branch(self) -> None:
        term: Term = Branch(
            operator="<",
            left=Reference(name="x"),
            right=Immediate(value=0),
            consequent=Reference(name="x"),
            otherwise=Immediate(value=1)
        )
        result = substitute(term, {"x": Immediate(value=3)})
        assert isinstance(result, Branch)
        assert result.left == Immediate(value=3)
        assert result.consequent == Immediate(value=3)

    def test_substitute_in_begin(self) -> None:
        term: Term = Begin(
            effects=(Reference(name="x"),),
            value=Reference(name="x")
        )
        result = substitute(term, {"x": Immediate(value=5)})
        assert isinstance(result, Begin)
        assert result.effects[0] == Immediate(value=5)
        assert result.value == Immediate(value=5)

    def test_substitute_allocate_unchanged(self) -> None:
        term: Term = Allocate(count=2)
        result = substitute(term, {"x": Immediate(value=1)})
        assert result == Allocate(count=2)


class TestInline:

    def test_single_use_inlined(self) -> None:
        # (let ([f (lambda (x) (* x x))]) (f 5))
        # f is used once -> inline
        f_body: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Let(
            bindings=(("f", Abstract(parameters=("x",), body=f_body)),),
            body=Apply(target=Reference(name="f"), arguments=(Immediate(value=5),))
        )
        result = inline(term)
        # After inlining, body should be a Let (wrapping argument), not an Apply
        assert isinstance(result, Let)
        assert not isinstance(result.body, Apply)

    def test_small_function_inlined_multiple_uses(self) -> None:
        # (let ([f (lambda (x) x)]) (+ (f 1) (f 2)))
        # f body size = 1 <= 5, so inline at both call sites
        term: Term = Let(
            bindings=(("f", Abstract(parameters=("x",), body=Reference(name="x"))),),
            body=Primitive(
                operator="+",
                left=Apply(target=Reference(name="f"), arguments=(Immediate(value=1),)),
                right=Apply(target=Reference(name="f"), arguments=(Immediate(value=2),))
            )
        )
        result = inline(term)
        assert isinstance(result, Let)
        # The body should not contain any Apply to f
        body = result.body
        assert not _contains_apply_to(body, "f")

    def test_large_multi_use_not_inlined(self) -> None:
        # Body size > threshold and used more than once -> do NOT inline
        # Build a body with 6 nodes: (* (* x x) (* x x)) = 7 nodes
        big_body: Term = Primitive(
            operator="*",
            left=Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x")),
            right=Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        )
        term: Term = Let(
            bindings=(("f", Abstract(parameters=("x",), body=big_body)),),
            body=Primitive(
                operator="+",
                left=Apply(target=Reference(name="f"), arguments=(Immediate(value=2),)),
                right=Apply(target=Reference(name="f"), arguments=(Immediate(value=3),))
            )
        )
        result = inline(term, size_threshold=5)
        assert isinstance(result, Let)
        # f should NOT be inlined: body still contains Apply to f
        assert _contains_any_apply(result.body)

    def test_non_function_binding_not_touched(self) -> None:
        # (let ([x 1]) (+ x 1))  ->  unchanged structure
        term: Term = Let(
            bindings=(("x", Immediate(value=1)),),
            body=Primitive(operator="+", left=Reference(name="x"), right=Immediate(value=1))
        )
        result = inline(term)
        assert result == term

    def test_threshold_zero_no_small_inlining(self) -> None:
        # threshold=0: only single-use functions are inlined
        # f used twice, body size 1 but threshold=0 -> not inlined
        term: Term = Let(
            bindings=(("f", Abstract(parameters=("x",), body=Reference(name="x"))),),
            body=Primitive(
                operator="+",
                left=Apply(target=Reference(name="f"), arguments=(Immediate(value=1),)),
                right=Apply(target=Reference(name="f"), arguments=(Immediate(value=2),))
            )
        )
        result = inline(term, size_threshold=0)
        assert isinstance(result, Let)
        assert _contains_any_apply(result.body)

    def test_threshold_infinity_inlines_everything(self) -> None:
        # threshold=999: all functions inlined regardless of size
        big_body: Term = Primitive(
            operator="*",
            left=Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x")),
            right=Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        )
        term: Term = Let(
            bindings=(("f", Abstract(parameters=("x",), body=big_body)),),
            body=Primitive(
                operator="+",
                left=Apply(target=Reference(name="f"), arguments=(Immediate(value=2),)),
                right=Apply(target=Reference(name="f"), arguments=(Immediate(value=3),))
            )
        )
        result = inline(term, size_threshold=999)
        assert isinstance(result, Let)
        assert not _contains_apply_to(result.body, "f")

    def test_inline_leaves_immediate_unchanged(self) -> None:
        term: Term = Immediate(value=42)
        assert inline(term) == Immediate(value=42)

    def test_inline_leaves_reference_unchanged(self) -> None:
        term: Term = Reference(name="x")
        assert inline(term) == Reference(name="x")

    def test_inline_leaves_allocate_unchanged(self) -> None:
        term: Term = Allocate(count=1)
        assert inline(term) == Allocate(count=1)

    def test_inline_primitive(self) -> None:
        term: Term = Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2))
        assert inline(term) == term

    def test_inline_branch(self) -> None:
        term: Term = Branch(
            operator="<",
            left=Immediate(value=1),
            right=Immediate(value=2),
            consequent=Immediate(value=10),
            otherwise=Immediate(value=20)
        )
        assert inline(term) == term

    def test_inline_begin(self) -> None:
        term: Term = Begin(
            effects=(Immediate(value=0),),
            value=Immediate(value=1)
        )
        assert inline(term) == term

    def test_inline_load(self) -> None:
        term: Term = Load(base=Reference(name="b"), index=0)
        assert inline(term) == term

    def test_inline_store(self) -> None:
        term: Term = Store(base=Reference(name="b"), index=0, value=Immediate(value=1))
        assert inline(term) == term

    def test_inline_abstract(self) -> None:
        # Abstract not inside a Let: just recurse, no inlining
        term: Term = Abstract(
            parameters=("x",),
            body=Apply(
                target=Reference(name="f"),
                arguments=(Reference(name="x"),)
            )
        )
        result = inline(term)
        assert isinstance(result, Abstract)


class TestInlineProgram:

    def test_no_capture_after_inline(self) -> None:
        # After inlining, all bound names must be unique
        f_body: Term = Primitive(operator="*", left=Reference(name="x"), right=Reference(name="x"))
        term: Term = Let(
            bindings=(("f", Abstract(parameters=("x",), body=f_body)),),
            body=Apply(target=Reference(name="f"), arguments=(Immediate(value=5),))
        )
        result = inline_program(term)
        assert _all_bindings_unique(result)

    def test_inline_program_proposal_example(self) -> None:
        # (let ([square (lambda (x) (* x x))])
        #   (let ([a (square 5)])
        #     (let ([b (square 6)])
        #       (+ a b))))
        square_body: Term = Primitive(
            operator="*", left=Reference(name="x"), right=Reference(name="x")
        )
        term: Term = Let(
            bindings=(("square", Abstract(parameters=("x",), body=square_body)),),
            body=Let(
                bindings=(("a", Apply(target=Reference(name="square"), arguments=(Immediate(value=5),))),),
                body=Let(
                    bindings=(("b", Apply(target=Reference(name="square"), arguments=(Immediate(value=6),))),),
                    body=Primitive(operator="+", left=Reference(name="a"), right=Reference(name="b"))
                )
            )
        )
        result = inline_program(term)
        # square should have been inlined (body size = 3 <= 5)
        assert not _contains_apply_to(result, "square")
        assert _all_bindings_unique(result)


class TestOptimizeProgram:

    def test_optimize_already_optimal(self) -> None:
        prog = Program(parameters=(), body=Immediate(value=42))
        result = optimize_program(prog)
        assert result.body == Immediate(value=42)

    def test_optimize_inlines_small_function(self) -> None:
        square_body: Term = Primitive(
            operator="*", left=Reference(name="x"), right=Reference(name="x")
        )
        prog = Program(
            parameters=("x",),
            body=Let(
                bindings=(("square", Abstract(parameters=("x",), body=square_body)),),
                body=Apply(target=Reference(name="square"), arguments=(Reference(name="x"),))
            )
        )
        result = optimize_program(prog)
        assert not _contains_apply_to(result.body, "square")

    def test_optimize_preserves_parameters(self) -> None:
        prog = Program(
            parameters=("a", "b"),
            body=Primitive(operator="+", left=Reference(name="a"), right=Reference(name="b"))
        )
        result = optimize_program(prog)
        assert tuple(result.parameters) == ("a", "b")

    def test_optimize_threshold_respected(self) -> None:
        # With threshold=0, multi-use functions are not inlined
        f_body: Term = Reference(name="x")  # size 1, but used twice
        prog = Program(
            parameters=(),
            body=Let(
                bindings=(("f", Abstract(parameters=("x",), body=f_body)),),
                body=Primitive(
                    operator="+",
                    left=Apply(target=Reference(name="f"), arguments=(Immediate(value=1),)),
                    right=Apply(target=Reference(name="f"), arguments=(Immediate(value=2),))
                )
            )
        )
        result = optimize_program(prog, size_threshold=0)
        assert _contains_any_apply(result.body)


def _contains_apply_to(term: Term, name: str) -> bool:
    """Return True if term contains Apply(Reference(name), ...) anywhere."""
    match term:
        case Apply(target=Reference(name=n)):
            if n == name:
                return True
            return any(_contains_apply_to(a, name) for a in term.arguments)
        case Apply(target=t, arguments=args):
            return _contains_apply_to(t, name) or any(_contains_apply_to(a, name) for a in args)
        case Let(bindings=bs, body=b):
            return any(_contains_apply_to(v, name) for _, v in bs) or _contains_apply_to(b, name)
        case Primitive(left=l, right=r):
            return _contains_apply_to(l, name) or _contains_apply_to(r, name)
        case Abstract(body=b):
            return _contains_apply_to(b, name)
        case Branch(left=l, right=r, consequent=c, otherwise=o):
            return (_contains_apply_to(l, name) or _contains_apply_to(r, name) or
                    _contains_apply_to(c, name) or _contains_apply_to(o, name))
        case Begin(effects=es, value=v):
            return any(_contains_apply_to(e, name) for e in es) or _contains_apply_to(v, name)
        case _:
            return False


def _collect_bound_names(term: Term) -> list[str]:
    """Collect all bound variable names in the term."""
    match term:
        case Let(bindings=bs, body=b):
            names = [n for n, _ in bs]
            for _, v in bs:
                names.extend(_collect_bound_names(v))
            names.extend(_collect_bound_names(b))
            return names
        case Abstract(parameters=ps, body=b):
            return list(ps) + _collect_bound_names(b)
        case Primitive(left=l, right=r):
            return _collect_bound_names(l) + _collect_bound_names(r)
        case Apply(target=t, arguments=args):
            return _collect_bound_names(t) + [n for a in args for n in _collect_bound_names(a)]
        case Branch(left=l, right=r, consequent=c, otherwise=o):
            return (_collect_bound_names(l) + _collect_bound_names(r) +
                    _collect_bound_names(c) + _collect_bound_names(o))
        case Begin(effects=es, value=v):
            return [n for e in es for n in _collect_bound_names(e)] + _collect_bound_names(v)
        case _:
            return []


def _all_bindings_unique(term: Term) -> bool:
    """Return True if all bound variable names in the term are globally unique."""
    names = _collect_bound_names(term)
    return len(names) == len(set(names))

def _contains_any_apply(term: Term) -> bool:
    """Return True if term contains any Apply node anywhere."""
    match term:
        case Apply():
            return True
        case Let(bindings=bs, body=b):
            return any(_contains_any_apply(v) for _, v in bs) or _contains_any_apply(b)
        case Primitive(left=l, right=r):
            return _contains_any_apply(l) or _contains_any_apply(r)
        case Abstract(body=b):
            return _contains_any_apply(b)
        case Branch(left=l, right=r, consequent=c, otherwise=o):
            return (_contains_any_apply(l) or _contains_any_apply(r) or
                    _contains_any_apply(c) or _contains_any_apply(o))
        case Begin(effects=es, value=v):
            return any(_contains_any_apply(e) for e in es) or _contains_any_apply(v)
        case _:
            return False


class TestCoverageGaps:

    def test_substitute_in_apply(self) -> None:
        # Cover line 196: Apply case in substitute
        term: Term = Apply(
            target=Reference(name="f"),
            arguments=(Reference(name="x"),)
        )
        result = substitute(term, {"x": Immediate(value=7)})
        assert isinstance(result, Apply)
        assert result.arguments[0] == Immediate(value=7)

    def test_apply_inline_env_traverses_let(self) -> None:
        # Cover line 362: Let case in _apply_inline_env
        # Build a situation where _apply_inline_env is called on a term
        # that contains a Let wrapping a call site.
        # (let ([f (lambda (x) x)])
        #   (let ([tmp 1])
        #     (f tmp)))
        # The inner let wraps the Apply, so _apply_inline_env must recurse into Let.
        term: Term = Let(
            bindings=(("f", Abstract(parameters=("x",), body=Reference(name="x"))),),
            body=Let(
                bindings=(("tmp", Immediate(value=1)),),
                body=Apply(target=Reference(name="f"), arguments=(Reference(name="tmp"),))
            )
        )
        result = inline(term)
        assert isinstance(result, Let)
        # The outer Let still holds f's binding
        # The inner body should have been inlined (no Apply to f)
        assert not _contains_apply_to(result.body, "f")


class TestApplyInlineEnvCoverage:

    def _make_inline_term(self, body: Term) -> Term:
        """
        Helper: wrap `body` in a single-use let binding so that
        _apply_inline_env is called on `body` directly.
        (let ([f (lambda () <body>)]) (f))
        """
        return Let(
            bindings=(("f", Abstract(parameters=(), body=body)),),
            body=Apply(target=Reference(name="f"), arguments=())
        )

    def test_apply_inline_env_abstract(self) -> None:
        # body contains an Abstract -> _apply_inline_env hits case Abstract
        inner: Term = Abstract(parameters=("y",), body=Reference(name="y"))
        term = self._make_inline_term(inner)
        result = inline(term)
        # f is single-use, so it gets inlined; result body is the Abstract
        assert isinstance(result, Let)
        assert isinstance(result.body, Abstract)

    def test_apply_inline_env_branch(self) -> None:
        # body contains a Branch -> _apply_inline_env hits case Branch
        branch: Term = Branch(
            operator="<",
            left=Immediate(value=1),
            right=Immediate(value=2),
            consequent=Immediate(value=10),
            otherwise=Immediate(value=20)
        )
        term = self._make_inline_term(branch)
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Branch)

    def test_apply_inline_env_begin(self) -> None:
        # body contains a Begin -> _apply_inline_env hits case Begin
        begin: Term = Begin(
            effects=(Immediate(value=0),),
            value=Immediate(value=1)
        )
        term = self._make_inline_term(begin)
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Begin)

    def test_apply_inline_env_load(self) -> None:
        # body contains a Load -> _apply_inline_env hits case Load
        load: Term = Load(base=Reference(name="b"), index=0)
        term = self._make_inline_term(load)
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Load)

    def test_apply_inline_env_store(self) -> None:
        # body contains a Store -> _apply_inline_env hits case Store
        store: Term = Store(
            base=Reference(name="b"),
            index=0,
            value=Immediate(value=1)
        )
        term = self._make_inline_term(store)
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Store)


class TestApplyInlineEnvCoverageV2:

    def _wrap(self, body_with_f: Term) -> Term:
        return Let(
            bindings=(("f", Abstract(parameters=("x",), body=Reference(name="x"))),),
            body=body_with_f
        )

    def test_abstract_in_body(self) -> None:
        # _apply_inline_env recurses into Abstract node in the outer body
        term = self._wrap(
            Abstract(
                parameters=("y",),
                body=Apply(target=Reference(name="f"), arguments=(Reference(name="y"),))
            )
        )
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Abstract)

    def test_branch_in_body(self) -> None:
        # _apply_inline_env recurses into Branch node in the outer body
        term = self._wrap(
            Branch(
                operator="<",
                left=Apply(target=Reference(name="f"), arguments=(Immediate(value=1),)),
                right=Immediate(value=0),
                consequent=Immediate(value=10),
                otherwise=Immediate(value=20)
            )
        )
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Branch)

    def test_begin_in_body(self) -> None:
        # _apply_inline_env recurses into Begin node in the outer body
        term = self._wrap(
            Begin(
                effects=(Apply(target=Reference(name="f"), arguments=(Immediate(value=0),)),),
                value=Immediate(value=1)
            )
        )
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Begin)

    def test_load_in_body(self) -> None:
        # _apply_inline_env recurses into Load node in the outer body
        # Load base is the call site so _apply_inline_env walks into it
        term = self._wrap(
            Load(
                base=Apply(target=Reference(name="f"), arguments=(Reference(name="b"),)),
                index=0
            )
        )
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Load)

    def test_store_in_body(self) -> None:
        # _apply_inline_env recurses into Store node in the outer body
        term = self._wrap(
            Store(
                base=Reference(name="b"),
                index=0,
                value=Apply(target=Reference(name="f"), arguments=(Immediate(value=1),))
            )
        )
        result = inline(term)
        assert isinstance(result, Let)
        assert isinstance(result.body, Store)