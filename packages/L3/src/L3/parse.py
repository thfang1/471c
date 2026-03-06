from collections.abc import Sequence
from pathlib import Path

from lark import Lark, Token, Transformer
from lark.visitors import v_args  # pyright: ignore[reportUnknownVariableType]

from .syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                     Immediate, Let, LetRec, Load, Primitive, Program,
                     Reference, Store, Term)


class AstTransformer(Transformer[Token, Program | Term | Identifier | int | tuple[Identifier, Term] | tuple[str, Term, Term]]):
    def IDENTIFIER(
        self,
        token: Token,
    ) -> Identifier:
        return str(token)

    def NAT(
        self,
        token: Token,
    ) -> int:
        return int(token)

    def INTEGER(
        self,
        token: Token,
    ) -> int:
        return int(token)
    
    @v_args(inline=True)
    def program(
        self,
        _program: Token,
        parameters: Sequence[Identifier],
        body: Term,
    ) -> Program:
        return Program(
            parameters=parameters,
            body=body,
        )

    def parameters(
        self,
        parameters: Sequence[Identifier],
    ) -> Sequence[Identifier]:
        return parameters

    @v_args(inline=True)
    def term(
        self,
        term: Term,
    ) -> Term:
        return term

    @v_args(inline=True)
    def let(
        self,
        _let: Token,
        bindings: Sequence[tuple[Identifier, Term]],
        body: Term,
    ) -> Term:
        return Let(
            bindings=bindings,
            body=body,
        )

    @v_args(inline=True)
    def letrec(
        self,
        _letrec: Token,
        bindings: Sequence[tuple[Identifier, Term]],
        body: Term,
    ) -> Term:
        return LetRec(
            bindings=bindings,
            body=body,
        )

    def bindings(
        self,
        bindings: Sequence[tuple[Identifier, Term]],
    ) -> Sequence[tuple[Identifier, Term]]:
        return bindings
    

    @v_args(inline=True)
    def binding(
        self,
        name: Identifier,
        value: Term,
    ) -> tuple[Identifier, Term]:
        return name, value
    
    @v_args(inline=True)
    def reference(
        self,
        name: Identifier,
    ) -> Term:
        return Reference(name=name)

    @v_args(inline=True)
    def abstract(
        self,
        _lambda: Token,
        parameters: Sequence[Identifier],
        body: Term,
    ) -> Term:
        return Abstract(
            parameters=parameters,
            body=body,
        )

    def apply(
        self,
        children: Sequence[Term],
    ) -> Term:
        target = children[0]
        arguments = children[1:]
        return Apply(
            target=target,
            arguments=arguments,
        )

    @v_args(inline=True)
    def immediate(
        self,
        value: int,
    ) -> Term:
        return Immediate(value=value)

    @v_args(inline=True)
    def primitive(
        self,
        operator: Token,
        left: Term,
        right: Term,
    ) -> Term:
        return Primitive(
            operator=str(operator),
            left=left,
            right=right,
        )

    @v_args(inline=True)
    def comparison(
        self,
        operator: Token,
        left: Term,
        right: Term,
    ) -> tuple[str, Term, Term]:
        return str(operator), left, right
    
    @v_args(inline=True)
    def branch(
        self,
        _if: Token,
        comparison: tuple[str, Term, Term],
        consequent: Term,
        otherwise: Term,
    ) -> Term:
        operator, left, right = comparison
        return Branch(
            operator=operator,
            left=left,
            right=right,
            consequent=consequent,
            otherwise=otherwise,
        )


    @v_args(inline=True)
    def allocate(
        self,
        _allocate: Token,
        count: int,
    ) -> Term:
        return Allocate(count=count)

    @v_args(inline=True)
    def load(
        self,
        _load: Token,
        base: Term,
        index: int,
    ) -> Term:
        return Load(
            base=base,
            index=index,
        )

    @v_args(inline=True)
    def store(
        self,
        _store: Token,
        base: Term,
        index: int,
        value: Term,
    ) -> Term:
        return Store(
            base=base,
            index=index,
            value=value,
        )

    def begin(
        self,
        children: Sequence[Token | Term],
    ) -> Term:
        _begin, *terms = children
        return Begin(
            effects=terms[:-1],
            value=terms[-1],
        )




def parse_term(source: str) -> Term:
    grammar = Path(__file__).with_name("L3.lark").read_text()
    parser = Lark(grammar, start="term")
    tree = parser.parse(source)  # pyright: ignore[reportUnknownMemberType]
    return AstTransformer().transform(tree)  # pyright: ignore[reportReturnType]


def parse_program(source: str) -> Program:
    grammar = Path(__file__).with_name("L3.lark").read_text()
    parser = Lark(grammar, start="program")
    tree = parser.parse(source)  # pyright: ignore[reportUnknownMemberType]
    return AstTransformer().transform(tree)  # pyright: ignore[reportReturnType]
