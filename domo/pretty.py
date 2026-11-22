"""Pretty-printer: AST -> código Domo.

O AST não guarda parênteses. São postos só onde a gramática os exige, segundo os
níveis de precedência de domo.lark (do menos para o mais prioritário):

    1 or   2 and   3 not   4 == != < <= > >=   5 + -   6 * / %   7 - unário   8 primário

- Operadores associativos à esquerda (or, and, + - * / %): o operando esquerdo pode ter
  o mesmo nível; o direito tem de ter um nível acima. Assim a - (b - c) mantém os parênteses.
- Relacionais (não associativos): os dois operandos têm de ser de nível 5 ou mais.
- not aceita um operando de nível 3 ou mais; o - unário, de nível 7 ou mais.

Os comentários do texto original perdem-se, porque o lexer os ignora.

Garantia (verificada nos testes): parse(pretty(p)) == p e pretty(parse(pretty(p))) == pretty(p).

Uso: python -m domo.pretty ficheiro.domo
"""
import sys

from . import ast as A

INDENT = "  "

PREC = {"or": 1, "and": 2, "==": 4, "!=": 4, "<": 4, "<=": 4, ">": 4, ">=": 4,
        "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}
REL = {"==", "!=", "<", "<=", ">", ">="}
UNARY_PREC = {"not": 3, "-": 7}
ATOM = 8


def pretty(node) -> str:
    """Código Domo de um programa, declaração, instrução ou expressão."""
    if isinstance(node, A.Program):
        return program(node)
    if isinstance(node, A.Expr):
        return expr(node)
    if isinstance(node, (A.Decl, A.Stmt)):
        return "\n".join(decl_or_stmt(node, 0))
    if isinstance(node, A.Event):
        return event(node)
    if isinstance(node, A.Block):
        return block(node, 0)
    raise TypeError(f"não sei imprimir {type(node).__name__}")


# ---------------------------------------------------------------- expressões

def prec(e: A.Expr) -> int:
    if isinstance(e, A.Binary):
        return PREC[e.op]
    if isinstance(e, A.Unary):
        return UNARY_PREC[e.op]
    if isinstance(e, (A.IntLit, A.RealLit)) and e.value < 0:
        return UNARY_PREC["-"]          # um literal negativo escreve-se com - unário
    return ATOM


def expr(e: A.Expr, min_prec: int = 0) -> str:
    """Escreve e, com parênteses se o seu nível for menor que min_prec."""
    text = _expr(e)
    return f"({text})" if prec(e) < min_prec else text


def _expr(e: A.Expr) -> str:
    if isinstance(e, A.Binary):
        p = PREC[e.op]
        if e.op in REL:
            return f"{expr(e.left, p + 1)} {e.op} {expr(e.right, p + 1)}"
        return f"{expr(e.left, p)} {e.op} {expr(e.right, p + 1)}"
    if isinstance(e, A.Unary):
        if e.op == "not":
            return f"not {expr(e.operand, UNARY_PREC['not'])}"
        inner = expr(e.operand, UNARY_PREC["-"])
        return f"- {inner}" if inner.startswith("-") else f"-{inner}"
    if isinstance(e, A.IntLit):
        return str(e.value) if e.value >= 0 else f"-{-e.value}"
    if isinstance(e, A.RealLit):
        return real(e.value)
    if isinstance(e, A.StrLit):
        return string(e.value)
    if isinstance(e, A.TimeLit):
        return time(e)
    if isinstance(e, A.BoolLit):
        return "true" if e.value else "false"
    if isinstance(e, A.Now):
        return "now"
    if isinstance(e, A.Ref):
        return ".".join(e.path)
    raise TypeError(f"expressão desconhecida: {type(e).__name__}")


def real(v: float) -> str:
    """Um REAL tem de ter a forma dígitos.dígitos (sem expoente)."""
    if v < 0:
        return f"-{real(-v)}"
    text = repr(float(v))
    if "e" in text or "E" in text:
        text = f"{v:.15f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    if "." not in text or not text.replace(".", "").isdigit():
        raise ValueError(f"valor real sem representação em Domo: {v!r}")
    return text


def string(s: str) -> str:
    if '"' in s or "\n" in s:
        raise ValueError(f"string sem representação em Domo (aspas ou mudança de linha): {s!r}")
    return f'"{s}"'


def time(t: A.TimeLit) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def duration(d: A.Duration) -> str:
    return f"{d.amount} {d.unit}"


def event(ev: A.Event) -> str:
    if isinstance(ev, A.OnChange):
        return f"change {ev.target}"
    if isinstance(ev, A.OnSignal):
        return f"signal {ev.target}"
    if isinstance(ev, A.At):
        return f"at {time(ev.time)}"
    if isinstance(ev, A.Every):
        return f"every {duration(ev.period)}"
    raise TypeError(f"evento desconhecido: {type(ev).__name__}")


# ---------------------------------------------------------------- instruções e declarações

def block(b: A.Block, level: int) -> str:
    if not b.stmts:
        return "{ }"
    lines = [line for s in b.stmts for line in decl_or_stmt(s, level + 1)]
    return "{\n" + "\n".join(lines) + "\n" + INDENT * level + "}"


def decl_or_stmt(n, level: int) -> list:
    """Linhas de uma declaração ou instrução, já indentadas."""
    pad = INDENT * level
    if isinstance(n, A.VarDecl):
        kw = "const" if n.const else "var"
        return [f"{pad}{kw} {n.name} : {n.var_type} = {expr(n.init)};"]
    if isinstance(n, A.Device):
        return [f"{pad}device {n.name} : {n.device_type};"]
    if isinstance(n, A.Group):
        return [f"{pad}group {n.name} = [{', '.join(str(m) for m in n.members)}];"]
    if isinstance(n, A.Scene):
        return [f"{pad}scene {n.name} {block(n.body, level)}"]
    if isinstance(n, A.Rule):
        head = f"rule {n.name}"
        if n.priority is not None:
            head += f" priority {n.priority}"
        head += f" on {event(n.event)}"
        if n.guard is not None:
            head += f" when {expr(n.guard)}"
        return [f"{pad}{head} {block(n.body, level)}"]
    if isinstance(n, A.Zone):
        return [f"{pad}zone {n.name} {decls_block(n.decls, level)}"]
    if isinstance(n, A.Assign):
        return [f"{pad}{n.target} = {expr(n.value)};"]
    if isinstance(n, A.Command):
        return [f"{pad}{n.target}({', '.join(expr(a) for a in n.args)});"]
    if isinstance(n, A.If):
        return [pad + if_chain(n, level)]
    if isinstance(n, A.Repeat):
        return [f"{pad}repeat {expr(n.count)} times {block(n.body, level)}"]
    if isinstance(n, A.For):
        return [f"{pad}for {n.var} in {n.group} {block(n.body, level)}"]
    if isinstance(n, A.Wait):
        return [f"{pad}wait {duration(n.duration)};"]
    if isinstance(n, A.Notify):
        return [f"{pad}notify {string(n.message)};"]
    if isinstance(n, A.Activate):
        return [f"{pad}activate {n.scene};"]
    raise TypeError(f"nó desconhecido: {type(n).__name__}")


def if_chain(n: A.If, level: int) -> str:
    text = f"if {expr(n.cond)} {block(n.then, level)}"
    if isinstance(n.orelse, A.If):
        text += " else " + if_chain(n.orelse, level)
    elif isinstance(n.orelse, A.Block):
        text += " else " + block(n.orelse, level)
    return text


def _has_block(n) -> bool:
    return isinstance(n, (A.Zone, A.Scene, A.Rule))


def decls_block(decls: list, level: int) -> str:
    """Corpo de home/zone. Zonas, cenas e regras ficam separadas por uma linha em branco."""
    if not decls:
        return "{ }"
    lines = []
    for i, d in enumerate(decls):
        if i > 0 and (_has_block(d) or _has_block(decls[i - 1])):
            lines.append("")
        lines.extend(decl_or_stmt(d, level + 1))
    return "{\n" + "\n".join(lines) + "\n" + INDENT * level + "}"


def program(p: A.Program) -> str:
    return f"home {string(p.name)} {decls_block(p.decls, 0)}\n"


if __name__ == "__main__":
    from .builder import load_file
    r = load_file(sys.argv[1])
    if r.program is None:
        print(r.syntax_error)
        sys.exit(2)
    sys.stdout.write(pretty(r.program))
