from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                        Immediate, Let, Load, Primitive, Program,
                        Reference, Store, Term)


DEFAULT_SIZE_THRESHOLD = 5


def ast_size(term: Term) -> int:
    """Count the number of AST nodes in a term."""
    match term:
        case Immediate() | Reference() | Allocate():
            return 1
        case Primitive(left=l, right=r):
            return 1 + ast_size(l) + ast_size(r)
        case Abstract(body=b):
            return 1 + ast_size(b)
        case Apply(target=t, arguments=args):
            return 1 + ast_size(t) + sum(ast_size(a) for a in args)
        case Let(bindings=bs, body=b):
            return 1 + sum(ast_size(v) for _, v in bs) + ast_size(b)
        case Branch(left=l, right=r, consequent=c, otherwise=o):
            return 1 + ast_size(l) + ast_size(r) + ast_size(c) + ast_size(o)
        case Begin(effects=es, value=v):
            return 1 + sum(ast_size(e) for e in es) + ast_size(v)
        case Load(base=b):
            return 1 + ast_size(b)
        case Store(base=b, value=v):
            return 1 + ast_size(b) + ast_size(v)
        case _:  # pragma: no cover
            return 1


def count_uses(name: str, term: Term) -> int:
    match term:
        case Reference(name=n):
            return 1 if n == name else 0
        case Immediate() | Allocate():
            return 0
        case Primitive(left=l, right=r):
            return count_uses(name, l) + count_uses(name, r)
        case Abstract(parameters=ps, body=b):
            if name in ps:
                return 0
            return count_uses(name, b)
        case Apply(target=t, arguments=args):
            return count_uses(name, t) + sum(count_uses(name, a) for a in args)
        case Let(bindings=bs, body=b):
            total = 0
            for n, v in bs:
                total += count_uses(name, v)
                if n == name:
                    return total  # shadowed from here on
            return total + count_uses(name, b)
        case Branch(left=l, right=r, consequent=c, otherwise=o):
            return (count_uses(name, l) + count_uses(name, r) +
                    count_uses(name, c) + count_uses(name, o))
        case Begin(effects=es, value=v):
            return sum(count_uses(name, e) for e in es) + count_uses(name, v)
        case Load(base=b):
            return count_uses(name, b)
        case Store(base=b, value=v):
            return count_uses(name, b) + count_uses(name, v)
        case _:  # pragma: no cover
            return 0


def uniqify(term: Term, env: dict[str, str], counter: list[int]) -> Term:
    def fresh(name: str) -> str:
        idx = counter[0]
        counter[0] += 1
        return f"{name}_{idx}"

    match term:
        case Immediate() | Allocate():
            return term

        case Reference(name=n):
            return Reference(name=env.get(n, n))

        case Primitive(operator=op, left=l, right=r):
            return Primitive(
                operator=op,
                left=uniqify(l, env, counter),
                right=uniqify(r, env, counter)
            )

        case Abstract(parameters=ps, body=b):
            new_env = dict(env)
            new_ps: list[str] = []
            for p in ps:
                fp = fresh(p)
                new_env[p] = fp
                new_ps.append(fp)
            return Abstract(
                parameters=tuple(new_ps),
                body=uniqify(b, new_env, counter)
            )

        case Apply(target=t, arguments=args):
            return Apply(
                target=uniqify(t, env, counter),
                arguments=tuple(uniqify(a, env, counter) for a in args)
            )

        case Let(bindings=bs, body=b):
            new_env = dict(env)
            new_bs: list[tuple[Identifier, Term]] = []
            for n, v in bs:
                s_v = uniqify(v, new_env, counter)
                fn = fresh(n)
                new_env[n] = fn
                new_bs.append((fn, s_v))
            return Let(
                bindings=tuple(new_bs),
                body=uniqify(b, new_env, counter)
            )

        case Branch(operator=op, left=l, right=r, consequent=c, otherwise=o):
            return Branch(
                operator=op,
                left=uniqify(l, env, counter),
                right=uniqify(r, env, counter),
                consequent=uniqify(c, env, counter),
                otherwise=uniqify(o, env, counter)
            )

        case Begin(effects=es, value=v):
            return Begin(
                effects=tuple(uniqify(e, env, counter) for e in es),
                value=uniqify(v, env, counter)
            )

        case Load(base=b, index=i):
            return Load(base=uniqify(b, env, counter), index=i)

        case Store(base=b, index=i, value=v):
            return Store(
                base=uniqify(b, env, counter),
                index=i,
                value=uniqify(v, env, counter)
            )

        case _:  # pragma: no cover
            raise ValueError(f"Unhandled term in uniqify: {term!r}")

def uniqify_program(term: Term) -> Term:
    return uniqify(term, {}, [0])

# ---------------------------------------------------------------------------
# Substitution
# ---------------------------------------------------------------------------

def substitute(term: Term, env: dict[str, Term]) -> Term:
    match term:
        case Immediate() | Allocate():
            return term

        case Reference(name=n):
            return env.get(n, term)

        case Primitive(operator=op, left=l, right=r):
            return Primitive(
                operator=op,
                left=substitute(l, env),
                right=substitute(r, env)
            )

        case Abstract(parameters=ps, body=b):
            inner_env = {k: v for k, v in env.items() if k not in ps}
            return Abstract(parameters=ps, body=substitute(b, inner_env))

        case Apply(target=t, arguments=args):
            return Apply(
                target=substitute(t, env),
                arguments=tuple(substitute(a, env) for a in args)
            )

        case Let(bindings=bs, body=b):
            new_env = dict(env)
            new_bs: list[tuple[Identifier, Term]] = []
            for n, v in bs:
                new_bs.append((n, substitute(v, new_env)))
                new_env.pop(n, None)
            return Let(
                bindings=tuple(new_bs),
                body=substitute(b, new_env)
            )

        case Branch(operator=op, left=l, right=r, consequent=c, otherwise=o):
            return Branch(
                operator=op,
                left=substitute(l, env),
                right=substitute(r, env),
                consequent=substitute(c, env),
                otherwise=substitute(o, env)
            )

        case Begin(effects=es, value=v):
            return Begin(
                effects=tuple(substitute(e, env) for e in es),
                value=substitute(v, env)
            )

        case Load(base=b, index=i):
            return Load(base=substitute(b, env), index=i)

        case Store(base=b, index=i, value=v):
            return Store(
                base=substitute(b, env),
                index=i,
                value=substitute(v, env)
            )

        case _:  # pragma: no cover
            raise ValueError(f"Unhandled term in substitute: {term!r}")


def inline(term: Term, size_threshold: int = DEFAULT_SIZE_THRESHOLD) -> Term:
    match term:
        case Immediate() | Reference() | Allocate():
            return term

        case Let(bindings=bs, body=b):
            new_bs: list[tuple[Identifier, Term]] = []
            for n, v in bs:
                new_bs.append((n, inline(v, size_threshold)))

            # Build environment of functions eligible for inlining
            inline_env: dict[str, Abstract] = {}
            for n, v in new_bs:
                if not isinstance(v, Abstract):
                    continue
                body_size = ast_size(v.body)
                uses = count_uses(n, b)
                if uses == 1 or body_size <= size_threshold:
                    inline_env[n] = v

            inlined_body = inline(b, size_threshold)
            inlined_body = _apply_inline_env(inlined_body, inline_env, size_threshold)

            return Let(bindings=tuple(new_bs), body=inlined_body)

        case Abstract(parameters=ps, body=b):
            return Abstract(parameters=ps, body=inline(b, size_threshold))

        case Apply(target=t, arguments=args):
            return Apply(
                target=inline(t, size_threshold),
                arguments=tuple(inline(a, size_threshold) for a in args)
            )

        case Primitive(operator=op, left=l, right=r):
            return Primitive(
                operator=op,
                left=inline(l, size_threshold),
                right=inline(r, size_threshold)
            )

        case Branch(operator=op, left=l, right=r, consequent=c, otherwise=o):
            return Branch(
                operator=op,
                left=inline(l, size_threshold),
                right=inline(r, size_threshold),
                consequent=inline(c, size_threshold),
                otherwise=inline(o, size_threshold)
            )

        case Begin(effects=es, value=v):
            return Begin(
                effects=tuple(inline(e, size_threshold) for e in es),
                value=inline(v, size_threshold)
            )

        case Load(base=b, index=i):
            return Load(base=inline(b, size_threshold), index=i)

        case Store(base=b, index=i, value=v):
            return Store(
                base=inline(b, size_threshold),
                index=i,
                value=inline(v, size_threshold)
            )

        case _:  # pragma: no cover
            raise ValueError(f"Unhandled term in inline: {term!r}")


def _apply_inline_env(
    term: Term,
    inline_env: dict[str, Abstract],
    size_threshold: int,
) -> Term:
    match term:
        case Immediate() | Reference() | Allocate():
            return term

        case Apply(target=Reference(name=n), arguments=args) if n in inline_env:
            func = inline_env[n]
            result: Term = func.body
            for param, arg in reversed(list(zip(func.parameters, args))):
                result = Let(
                    bindings=((param, _apply_inline_env(arg, inline_env, size_threshold)),),
                    body=result
                )
            return result

        case Apply(target=t, arguments=args):
            return Apply(
                target=_apply_inline_env(t, inline_env, size_threshold),
                arguments=tuple(_apply_inline_env(a, inline_env, size_threshold) for a in args)
            )

        case Primitive(operator=op, left=l, right=r):
            return Primitive(
                operator=op,
                left=_apply_inline_env(l, inline_env, size_threshold),
                right=_apply_inline_env(r, inline_env, size_threshold)
            )

        case Let(bindings=bs, body=b): # pragma: no branch
            return Let(
                bindings=tuple((n, _apply_inline_env(v, inline_env, size_threshold)) for n, v in bs),
                body=_apply_inline_env(b, inline_env, size_threshold)
            )

        case Abstract(parameters=ps, body=b):
            return Abstract(
                parameters=ps,
                body=_apply_inline_env(b, inline_env, size_threshold)
            )

        case Branch(operator=op, left=l, right=r, consequent=c, otherwise=o):
            return Branch(
                operator=op,
                left=_apply_inline_env(l, inline_env, size_threshold),
                right=_apply_inline_env(r, inline_env, size_threshold),
                consequent=_apply_inline_env(c, inline_env, size_threshold),
                otherwise=_apply_inline_env(o, inline_env, size_threshold)
            )

        case Begin(effects=es, value=v):
            return Begin(
                effects=tuple(_apply_inline_env(e, inline_env, size_threshold) for e in es),
                value=_apply_inline_env(v, inline_env, size_threshold)
            )

        case Load(base=b, index=i):
            return Load(base=_apply_inline_env(b, inline_env, size_threshold), index=i)

        case Store(base=b, index=i, value=v):
            return Store(
                base=_apply_inline_env(b, inline_env, size_threshold),
                index=i,
                value=_apply_inline_env(v, inline_env, size_threshold)
            )

        case _:  # pragma: no cover
            raise ValueError(f"Unhandled term in _apply_inline_env: {term!r}")

# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def inline_program(
    term: Term,
    size_threshold: int = DEFAULT_SIZE_THRESHOLD,
) -> Term:
    return uniqify_program(inline(term, size_threshold))


def optimize_program(
    program: Program,
    size_threshold: int = DEFAULT_SIZE_THRESHOLD,
) -> Program:
    current = program.body
    while True:
        after = inline(current, size_threshold)
        if after == current:
            break
        current = after
    return Program(parameters=program.parameters, body=uniqify_program(current))