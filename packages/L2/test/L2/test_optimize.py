from L2.optimize import optimize_program
from L2.syntax import (
    Immediate,
    Primitive,
    Program,
)


def test_optimize_program():
    program = Program(
        parameters=[],
        body=Primitive(
            operator="+",
            left=Immediate(value=1),
            right=Immediate(value=1),
        ),
    )

    expected = Program(
        parameters=[],
        body=Immediate(value=2),
    )

    actual = optimize_program(program)

    assert actual == expected
