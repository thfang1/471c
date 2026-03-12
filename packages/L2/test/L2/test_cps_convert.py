from L1 import syntax as L1
from L2 import syntax as L2
from L2.cps_convert import cps_convert_program, cps_convert_term
from util.sequential_name_generator import SequentialNameGenerator


def k(v: L1.Identifier) -> L1.Statement:
    return L1.Halt(value=v)


def test_cps_convert_term_name():
    term = L2.Reference(name="x")

    fresh = SequentialNameGenerator()

    actual = cps_convert_term(term, k, fresh)

    expected = L1.Halt(value="x")
    assert actual == expected


def test_cps_convert_term_immediate():
    term = L2.Immediate(value=42)

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Immediate(
        destination="t0",
        value=42,
        then=L1.Halt(value="t0"),
    )

    assert actual == expected


def test_cps_convert_term_primitive():
    term = L2.Primitive(
        operator="+",
        left=L2.Reference(name="x"),
        right=L2.Reference(name="y"),
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Primitive(
        destination="t0",
        operator="+",
        left="x",
        right="y",
        then=L1.Halt(value="t0"),
    )

    assert actual == expected


def test_cps_convert_term_let():
    term = L2.Let(
        bindings=[
            ("a", L2.Reference(name="x")),
            ("b", L2.Reference(name="y")),
        ],
        body=L2.Reference(name="b"),
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Copy(
        destination="a",
        source="x",
        then=L1.Copy(
            destination="b",
            source="y",
            then=L1.Halt(value="b"),
        ),
    )

    assert actual == expected


def test_cps_convert_term_abstract():
    term = L2.Abstract(
        parameters=["x"],
        body=L2.Reference(name="x"),
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Abstract(
        destination="t0",
        parameters=["x", "k0"],
        body=L1.Apply(target="k0", arguments=["x"]),
        then=L1.Halt(value="t0"),
    )

    assert actual == expected


def test_cps_convert_term_apply():
    term = L2.Apply(
        target=L2.Reference(name="f"),
        arguments=[
            L2.Reference(name="y"),
        ],
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Abstract(
        destination="k0",
        parameters=["t0"],
        body=L1.Halt(value="t0"),
        then=L1.Apply(
            target="f",
            arguments=["y", "k0"],
        ),
    )

    assert actual == expected


def test_cps_convert_term_branch():
    term = L2.Branch(
        operator="==",
        left=L2.Reference(name="x"),
        right=L2.Reference(name="y"),
        consequent=L2.Reference(name="a"),
        otherwise=L2.Reference(name="b"),
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Abstract(
        destination="j0",
        parameters=["t0"],
        body=L1.Halt(value="t0"),
        then=L1.Branch(
            operator="==",
            left="x",
            right="y",
            then=L1.Apply(
                target="j0",
                arguments=["a"],
            ),
            otherwise=L1.Apply(
                target="j0",
                arguments=["b"],
            ),
        ),
    )

    assert actual == expected


def test_cps_convert_term_allocate():
    term = L2.Allocate(count=0)

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Allocate(
        destination="t0",
        count=0,
        then=L1.Halt(value="t0"),
    )

    assert actual == expected


def test_cps_convert_term_load():
    term_load = L2.Load(
        base=L2.Reference(name="x"),
        index=0,
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term_load, k, fresh)

    expected = L1.Load(
        destination="t0",
        base="x",
        index=0,
        then=L1.Halt(value="t0"),
    )

    assert actual == expected


def test_cps_convert_term_store():
    term = L2.Store(
        base=L2.Reference(name="x"),
        index=0,
        value=L2.Reference(name="y"),
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Store(
        base="x",
        index=0,
        value="y",
        then=L1.Immediate(
            destination="t0",
            value=0,
            then=L1.Halt(value="t0"),
        ),
    )

    assert actual == expected


def test_cps_convert_term_begin():
    term = L2.Begin(
        effects=[
            L2.Reference(name="x"),
        ],
        value=L2.Reference(name="y"),
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_term(term, k, fresh)

    expected = L1.Halt(value="y")
    assert actual == expected


def test_cps_convert_program():
    program = L2.Program(
        parameters=["x"],
        body=L2.Reference(name="x"),
    )

    fresh = SequentialNameGenerator()
    actual = cps_convert_program(program, fresh)

    expected = L1.Program(
        parameters=["x"],
        body=L1.Halt(value="x"),
    )

    assert actual == expected
