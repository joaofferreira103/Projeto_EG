"""Construção do AST elaborado a partir da árvore do Lark.

    texto --parser--> árvore Lark --semântica--> árvore Lark + resoluções --builder--> AST

A resolução de nomes e os tipos não são recalculados aqui: vêm do SemanticAnalyzer
(resolutions, decl_symbols), que é a implementação já testada da gramática de atributos.
O builder só converte a forma da árvore e copia esses resultados para os nós.

Uso: python -m domo.builder ficheiro.domo
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from lark import Token, Tree

from . import ast as A
from .parser import build_parser, describe_error, syntactic_analysis, terminal_names
from .semantic import SemanticAnalyzer, SemanticError

BINARY_OPS = {
    "or_": "or", "and_": "and",
    "eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">=",
    "add": "+", "sub": "-", "mul": "*", "div": "/", "mod": "%",
}
TYPES = {"t_int": "int", "t_real": "real", "t_bool": "bool", "t_string": "string", "t_time": "time"}
UNITS = {"u_sec": "sec", "u_min": "min", "u_hour": "hour"}


def _trees(node: Tree) -> List[Tree]:
    return [c for c in node.children if isinstance(c, Tree)]


def _pos(node) -> dict:
    """Linha e coluna de um nó ou token do Lark (0 se desconhecida)."""
    if isinstance(node, Token):
        return {"line": node.line or 0, "col": node.column or 0}
    meta = node.meta
    if meta.empty:
        return {"line": 0, "col": 0}
    return {"line": meta.line, "col": meta.column}


class ASTBuilder:
    def __init__(self, sem: Optional[SemanticAnalyzer] = None):
        self.sem = sem

    def _sym(self, node: Tree):
        return self.sem.decl_symbols.get(id(node)) if self.sem else None

    def _type(self, node: Tree, default: Optional[str] = None) -> Optional[str]:
        """Tipo calculado pela semântica (atributo type). Uma expressão que a semântica
        não chegou a avaliar (ex.: argumentos de um comando com aridade errada) fica
        com o tipo do literal, se for um literal, ou None."""
        if self.sem and id(node) in self.sem.expr_types:
            return self.sem.expr_types[id(node)]
        return default

    # ------------------------------------------------------------ programa e declarações

    def build(self, tree: Tree) -> A.Program:
        if tree.data == "start":
            tree = tree.children[0]
        name = str(tree.children[0])[1:-1]
        return A.Program(name, self.decls(tree.children[1:]), **_pos(tree))

    def decls(self, children) -> list:
        return [self.decl(c) for c in children if isinstance(c, Tree)]

    def decl(self, t: Tree):
        d = t.data
        if d == "zone_decl":
            return A.Zone(str(t.children[0]), self.decls(t.children[1:]), sym=self._sym(t), **_pos(t))
        if d == "device_decl":
            return A.Device(str(t.children[0]), str(t.children[1]), sym=self._sym(t), **_pos(t))
        if d in ("var_decl", "const_decl"):
            return self.var_decl(t)
        if d == "group_decl":
            members = [self.ref(r) for r in _trees(t)]
            return A.Group(str(t.children[0]), members, sym=self._sym(t), **_pos(t))
        if d == "scene_decl":
            return A.Scene(str(t.children[0]), self.block(t.children[1]), sym=self._sym(t), **_pos(t))
        if d == "rule_decl":
            return self.rule(t)
        raise ValueError(f"declaração desconhecida: {d}")

    def var_decl(self, t: Tree) -> A.VarDecl:
        name, type_node, init = t.children
        return A.VarDecl(str(name), TYPES[type_node.data], self.expr(init),
                         const=(t.data == "const_decl"), sym=self._sym(t), **_pos(t))

    def rule(self, t: Tree) -> A.Rule:
        priority = guard = event = body = None
        for c in _trees(t):
            if c.data == "priority":
                priority = int(c.children[0])
            elif c.data == "guard":
                guard = self.expr(c.children[0])
            elif c.data == "block":
                body = self.block(c)
            else:
                event = self.event(c)
        return A.Rule(str(t.children[0]), priority, event, guard, body, sym=self._sym(t), **_pos(t))

    def event(self, t: Tree) -> A.Event:
        d, c = t.data, t.children[0]
        if d == "ev_change":
            return A.OnChange(self.ref(c), **_pos(t))
        if d == "ev_signal":
            return A.OnSignal(self.ref(c), **_pos(t))
        if d == "ev_at":
            return A.At(self.time(c), **_pos(t))
        if d == "ev_every":
            return A.Every(self.duration(c), **_pos(t))
        raise ValueError(f"evento desconhecido: {d}")

    def duration(self, t: Tree) -> A.Duration:
        return A.Duration(int(t.children[0]), UNITS[t.children[1].data], **_pos(t))

    def time(self, tok: Token) -> A.TimeLit:
        hh, mm = str(tok).split(":")
        return A.TimeLit(int(hh), int(mm), type="time", **_pos(tok))

    # ------------------------------------------------------------ instruções

    def block(self, t: Tree) -> A.Block:
        return A.Block([self.stmt(c) for c in _trees(t)], **_pos(t))

    def stmt(self, t: Tree) -> A.Stmt:
        d = t.data
        if d in ("var_decl", "const_decl"):
            return self.var_decl(t)
        if d == "assign":
            return A.Assign(self.ref(t.children[0]), self.expr(t.children[1]), **_pos(t))
        if d == "command":
            args = [self.expr(a) for c in _trees(t)[1:] for a in _trees(c)]
            return A.Command(self.ref(t.children[0]), args, **_pos(t))
        if d == "if_stmt":
            return self.if_stmt(t)
        if d == "repeat_stmt":
            return A.Repeat(self.expr(t.children[0]), self.block(t.children[1]), **_pos(t))
        if d == "for_stmt":
            var, group, body = t.children
            return A.For(str(var), self.ref(group), self.block(body), sym=self._sym(t), **_pos(t))
        if d == "wait":
            return A.Wait(self.duration(t.children[0]), **_pos(t))
        if d == "notify":
            return A.Notify(str(t.children[0])[1:-1], **_pos(t))
        if d == "activate":
            return A.Activate(self.ref(t.children[0]), **_pos(t))
        raise ValueError(f"instrução desconhecida: {d}")

    def if_stmt(self, t: Tree) -> A.If:
        cond, then, *rest = t.children
        orelse = None
        if rest:
            body = rest[0].children[0]          # else_part -> block | if_stmt
            orelse = self.block(body) if body.data == "block" else self.if_stmt(body)
        return A.If(self.expr(cond), self.block(then), orelse, **_pos(t))

    # ------------------------------------------------------------ expressões

    def ref(self, t: Tree) -> A.Ref:
        res = self.sem.resolutions.get(id(t)) if self.sem else None
        default = res.type_name if res and res.kind in ("var", "const", "property") else None
        return A.Ref(tuple(str(tok) for tok in t.children), res=res, type=self._type(t, default), **_pos(t))

    def expr(self, t: Tree) -> A.Expr:
        d, pos = t.data, _pos(t)
        if d == "ref":
            return self.ref(t)
        if d == "int_lit":
            return A.IntLit(int(t.children[0]), type="int", **pos)
        if d == "real_lit":
            return A.RealLit(float(t.children[0]), type="real", **pos)
        if d == "str_lit":
            return A.StrLit(str(t.children[0])[1:-1], type="string", **pos)
        if d == "time_lit":
            return self.time(t.children[0])
        if d in ("true_lit", "false_lit"):
            return A.BoolLit(d == "true_lit", type="bool", **pos)
        if d == "now":
            return A.Now(type="time", **pos)
        if d == "neg":
            return A.Unary("-", self.expr(t.children[0]), type=self._type(t), **pos)
        if d == "not_":
            return A.Unary("not", self.expr(t.children[0]), type=self._type(t, "bool"), **pos)
        if d in BINARY_OPS:
            return A.Binary(BINARY_OPS[d], self.expr(t.children[0]), self.expr(t.children[1]),
                            type=self._type(t), **pos)
        raise ValueError(f"expressão desconhecida: {d}")


# ---------------------------------------------------------------- ponto de entrada

@dataclass
class Frontend:
    """Resultado de processar um programa: AST e erros (sintáticos ou semânticos)."""
    program: Optional[A.Program]
    syntax_error: Optional[str] = None
    errors: List[SemanticError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.program is not None and self.syntax_error is None and not self.errors


_PARSER = None


def load(src: str) -> Frontend:
    """Analisa src e devolve o AST elaborado. Com erros semânticos o AST existe na mesma,
    mas as referências que não se resolveram ficam com res = None."""
    global _PARSER
    if _PARSER is None:
        _PARSER = build_parser()
    tree, err = syntactic_analysis(_PARSER, src)
    if err is not None:
        return Frontend(None, describe_error(err, src, terminal_names(_PARSER)))
    sem = SemanticAnalyzer()
    errors = sem.analyze(tree)
    return Frontend(ASTBuilder(sem).build(tree), errors=errors)


def load_file(path) -> Frontend:
    return load(Path(path).read_text(encoding="utf-8"))


def dump(node, indent: int = 0) -> str:
    """Representação legível do AST, com as anotações semânticas."""
    pad = "  " * indent
    name = type(node).__name__
    fields, children = [], []
    for f in node.__dataclass_fields__.values():
        if f.name in ("line", "col"):
            continue
        v = getattr(node, f.name)
        if isinstance(v, A.Node):
            children.append((f.name, [v]))
        elif isinstance(v, list) and v and isinstance(v[0], A.Node):
            children.append((f.name, v))
        elif isinstance(v, list):
            continue
        elif v is not None and f.name != "res":
            fields.append(f"{f.name}={v!r}" if f.name != "path" else f"{'.'.join(v)}")
    if isinstance(node, A.Ref) and node.res:
        target = node.symbol.qualname + (f".{node.member}" if node.member else "")
        fields.append(f"→ {node.kind} {target}")
    out = [f"{pad}{name}({', '.join(fields)})  @{node.line}:{node.col}"]
    for label, items in children:
        out.append(f"{pad}  {label}:")
        out.extend(dump(c, indent + 2) for c in items)
    return "\n".join(out)


if __name__ == "__main__":
    r = load_file(sys.argv[1])
    if r.syntax_error:
        print(r.syntax_error)
        sys.exit(2)
    print(dump(r.program))
    for e in r.errors:
        print(e)
    sys.exit(3 if r.errors else 0)
