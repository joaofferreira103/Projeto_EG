"""Grafo de fluxo de controlo (CFG) de cada regra e cena.

Um CFG por unidade (regra ou cena). Cada instrução é um nó; as setas dizem que
instrução se pode executar a seguir. A construção segue a estrutura do AST:

    sequência  s1; s2         s1 -> s2
    when c (regra)            ENTRY -> [when c] -V-> corpo -> EXIT,   [when c] -F-> EXIT
    if c {A} else {B}         [if c] -V-> A,  [if c] -F-> B,  A e B -> seguinte
    repeat n times {A}        [repeat n] -> [teste] -V-> A -> [teste],  [teste] -F-> seguinte
    for x in g {A}            [for x in g] -> [x ← próximo] -V-> A -> [x ← próximo],  -F-> seguinte
    activate S                nó de chamada; continua na instrução seguinte

Não há while, por isso todos os ciclos terminam: o teste do repeat/for acaba sempre por dar F.
`activate` liga ao CFG da cena num grafo interprocedimental (ProgramCFG.call_edges),
sem distinguir os vários sítios de onde a cena é chamada.

Uso: python -m domo.cfg ficheiro.domo [--unidade NOME] [--formato texto|dot|mermaid|svg]
                                       [--blocos] [--defuse] [-o saida]
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from . import ast as A
from .locations import Loc, Locator
from .pretty import duration, event as event_text, expr as expr_text, pretty

Pred = Tuple[int, str]          # (nó de onde se sai, etiqueta da seta)

DECISIONS = {"guard", "branch", "loop_test"}


@dataclass
class CFGNode:
    id: int
    kind: str                   # entry exit guard branch loop_init loop_test assign command decl wait notify call
    label: str
    ast: Optional[A.Node] = None
    uses: Set[Loc] = field(default_factory=set)
    defs: Set[Loc] = field(default_factory=set)
    strong: bool = True         # as escritas em defs são fortes?
    callee: object = None       # símbolo da cena, num nó de chamada

    @property
    def line(self) -> int:
        return self.ast.line if self.ast else 0


@dataclass
class CFG:
    name: str                   # nome qualificado (Floor1.Living.welcome)
    kind: str                   # rule ou scene
    decl: A.Node
    nodes: Dict[int, CFGNode] = field(default_factory=dict)
    edges: List[Tuple[int, int, str]] = field(default_factory=list)
    entry: int = 0
    exit: int = 1

    def succ(self, n: int) -> List[Tuple[int, str]]:
        return [(d, l) for s, d, l in self.edges if s == n]

    def pred(self, n: int) -> List[Tuple[int, str]]:
        return [(s, l) for s, d, l in self.edges if d == n]

    def reachable(self, start: int, forward: bool = True) -> Set[int]:
        seen, todo = {start}, [start]
        while todo:
            n = todo.pop()
            for m, _ in (self.succ(n) if forward else self.pred(n)):
                if m not in seen:
                    seen.add(m)
                    todo.append(m)
        return seen


class CFGBuilder:
    def __init__(self, locator: Locator):
        self.loc = locator

    def build(self, decl) -> CFG:
        sym = decl.sym
        name = sym.qualname if sym else decl.name
        if isinstance(decl, A.Rule):
            self.cfg = CFG(name, "rule", decl)
            self.new("entry", f"rule {decl.name}\non {event_text(decl.event)}", decl)
        else:
            self.cfg = CFG(name, "scene", decl)
            self.new("entry", f"scene {decl.name}", decl)
        self.new("exit", "EXIT")

        preds: List[Pred] = [(self.cfg.entry, "")]
        if isinstance(decl, A.Rule) and decl.guard is not None:
            g = self.new("guard", f"when {expr_text(decl.guard)}", decl.guard, uses=self.loc.uses(decl.guard))
            self.connect(preds, g)
            self.cfg.edges.append((g, self.cfg.exit, "F"))
            preds = [(g, "V")]
        self.connect(self.seq(decl.body.stmts, preds), self.cfg.exit)
        return self.cfg

    # ------------------------------------------------------------ auxiliares

    def new(self, kind, label, ast=None, uses=None, defs=None, strong=True, callee=None) -> int:
        n = len(self.cfg.nodes)
        self.cfg.nodes[n] = CFGNode(n, kind, label, ast, uses or set(), defs or set(), strong, callee)
        return n

    def connect(self, preds: List[Pred], node: int):
        for p, label in preds:
            self.cfg.edges.append((p, node, label))

    def seq(self, stmts, preds: List[Pred]) -> List[Pred]:
        for s in stmts:
            preds = self.stmt(s, preds)
        return preds

    # ------------------------------------------------------------ instruções

    def stmt(self, s, preds: List[Pred]) -> List[Pred]:
        if isinstance(s, A.If):
            b = self.new("branch", f"if {expr_text(s.cond)}", s, uses=self.loc.uses(s.cond))
            self.connect(preds, b)
            out = self.seq(s.then.stmts, [(b, "V")])
            if isinstance(s.orelse, A.If):
                out += self.stmt(s.orelse, [(b, "F")])
            elif isinstance(s.orelse, A.Block):
                out += self.seq(s.orelse.stmts, [(b, "F")])
            else:
                out.append((b, "F"))
            return out

        if isinstance(s, (A.Repeat, A.For)):
            if isinstance(s, A.Repeat):
                init = self.new("loop_init", f"repeat {expr_text(s.count)} times", s, uses=self.loc.uses(s.count))
                test = self.new("loop_test", "mais uma iteração?", s)
            else:
                # a variável do for designa um dispositivo, não um valor: não entra no def-use
                init = self.new("loop_init", f"for {s.var} in {s.group}", s)
                test = self.new("loop_test", f"{s.var} ← próximo de {s.group}", s)
            self.connect(preds, init)
            self.connect([(init, "")], test)
            self.connect(self.seq(s.body.stmts, [(test, "V")]), test)
            return [(test, "F")]

        if isinstance(s, A.Activate):
            n = self.new("call", f"activate {s.scene}", s, callee=s.scene.symbol)
        elif isinstance(s, A.Wait):
            n = self.new("wait", f"wait {duration(s.duration)}", s)
        elif isinstance(s, A.Notify):
            n = self.new("notify", pretty(s).rstrip(";"), s)
        else:
            kind = {A.VarDecl: "decl", A.Assign: "assign", A.Command: "command"}[type(s)]
            defs, strong = self.loc.stmt_defs(s)
            n = self.new(kind, pretty(s).rstrip(";"), s, uses=self.loc.stmt_uses(s), defs=defs, strong=strong)
        self.connect(preds, n)
        return [(n, "")]


# ---------------------------------------------------------------- programa inteiro

@dataclass
class ProgramCFG:
    units: Dict[str, CFG]                       # nome qualificado -> CFG
    by_symbol: Dict[object, CFG]

    def call_edges(self) -> List[Tuple[CFG, int, CFG]]:
        """(unidade que chama, nó de chamada, cena chamada)."""
        out = []
        for cfg in self.units.values():
            for n in cfg.nodes.values():
                if n.kind == "call" and n.callee in self.by_symbol:
                    out.append((cfg, n.id, self.by_symbol[n.callee]))
        return out


def build_cfgs(program: A.Program, locator: Optional[Locator] = None) -> ProgramCFG:
    builder = CFGBuilder(locator or Locator(program))
    units, by_symbol = {}, {}
    for n in program.walk():
        if isinstance(n, (A.Rule, A.Scene)):
            cfg = builder.build(n)
            units[cfg.name] = cfg
            by_symbol[n.sym] = cfg
    return ProgramCFG(units, by_symbol)


# ---------------------------------------------------------------- blocos básicos

def basic_blocks(cfg: CFG) -> List[List[int]]:
    """Agrupa os nós em blocos básicos: sequências máximas sem ramificações, em que só
    se entra pelo primeiro nó e só se sai pelo último. ENTRY e EXIT ficam sozinhos."""
    def leader(n):
        node = cfg.nodes[n]
        if node.kind in ("entry", "exit"):
            return True
        preds = cfg.pred(n)
        if len(preds) != 1:
            return True
        p = preds[0][0]
        return cfg.nodes[p].kind == "entry" or len(cfg.succ(p)) != 1
    blocks = []
    for n in sorted(cfg.nodes):
        if not leader(n):
            continue
        block = [n]
        while cfg.nodes[block[-1]].kind not in ("entry", "exit"):
            succ = cfg.succ(block[-1])
            if len(succ) != 1 or leader(succ[0][0]):
                break
            block.append(succ[0][0])
        blocks.append(block)
    return blocks


# ---------------------------------------------------------------- visualização

def to_graph(cfg: CFG, blocks: bool = False, defuse: bool = False, prefix: str = ""):
    """Descrição do CFG para render.py. Com blocks, um nó por bloco básico; com defuse,
    acrescenta as cadeias definição-uso (setas tracejadas)."""
    from .render import Graph, GNode, GEdge
    g = Graph(title=f"CFG de {cfg.name}")

    def shape(node):
        if node.kind in ("entry", "exit"):
            return "oval"
        return "diamond" if node.kind in DECISIONS else "box"

    if blocks:
        owner, all_blocks = {}, basic_blocks(cfg)
        leaders = {b[0] for b in all_blocks}
        for i, block in enumerate(all_blocks):
            for n in block:
                owner[n] = f"{prefix}B{i}"
            first = cfg.nodes[block[0]]
            label = "\n".join(cfg.nodes[n].label for n in block)
            if first.kind not in ("entry", "exit"):
                label = f"B{i}\n{label}"
            g.nodes.append(GNode(owner[block[0]], label, shape(cfg.nodes[block[-1]]),
                                 "bold" if any(cfg.nodes[n].kind == "call" for n in block) else ""))
        for s, d, l in cfg.edges:
            if d in leaders:            # as outras arestas são internas a um bloco
                g.edges.append(GEdge(owner[s], owner[d], l))
    else:
        for n in cfg.nodes.values():
            g.nodes.append(GNode(f"{prefix}n{n.id}", n.label, shape(n), "bold" if n.kind == "call" else ""))
        for s, d, l in cfg.edges:
            g.edges.append(GEdge(f"{prefix}n{s}", f"{prefix}n{d}", l))

    if defuse and not blocks:
        from .dataflow import def_use_chains
        for d, u, loc in def_use_chains(cfg):
            g.edges.append(GEdge(f"{prefix}n{d}", f"{prefix}n{u}", str(loc), "dashed"))
    return g


def program_graph(pcfg: ProgramCFG, blocks: bool = False):
    """Todos os CFG num só grafo (um grupo por unidade), com as chamadas de activate."""
    from .render import Graph, GEdge
    g = Graph(title="CFG interprocedimental")
    for i, cfg in enumerate(pcfg.units.values()):
        sub = to_graph(cfg, blocks=blocks, prefix=f"u{i}_")
        g.nodes += sub.nodes
        g.edges += sub.edges
        g.clusters[cfg.name] = [n.id for n in sub.nodes]
    index = {cfg.name: i for i, cfg in enumerate(pcfg.units.values())}
    for caller, node, callee in pcfg.call_edges():
        src = f"u{index[caller.name]}_" + (_block_of(caller, node) if blocks else f"n{node}")
        g.edges.append(GEdge(src, f"u{index[callee.name]}_" + ("B0" if blocks else f"n{callee.entry}"),
                             "activate", "dashed"))
    return g


def _block_of(cfg: CFG, node: int) -> str:
    for i, block in enumerate(basic_blocks(cfg)):
        if node in block:
            return f"B{i}"
    raise KeyError(node)


def to_text(cfg: CFG) -> str:
    """Listagem dos nós com sucessores, leituras e escritas."""
    out = [f"CFG de {cfg.kind} {cfg.name}: {len(cfg.nodes)} nós, {len(cfg.edges)} arestas"]
    for n in cfg.nodes.values():
        succ = ", ".join(f"{d}" + (f"[{l}]" if l else "") for d, l in cfg.succ(n.id)) or "-"
        line = f"  {n.id:>3} {n.kind:<9} {n.label.replace(chr(10), ' / '):<50} -> {succ}"
        if n.uses:
            line += f"   lê {{{', '.join(sorted(map(str, n.uses)))}}}"
        if n.defs:
            line += f"   escreve {'' if n.strong else 'um de '}{{{', '.join(sorted(map(str, n.defs)))}}}"
        out.append(line)
    return "\n".join(out)


def main(argv=None):
    import argparse
    import sys
    from .builder import load_file
    from .render import emit
    ap = argparse.ArgumentParser(description="Grafo de fluxo de controlo das regras e cenas.")
    ap.add_argument("ficheiro")
    ap.add_argument("--unidade", help="regra ou cena (nome simples ou qualificado); omisso = todas")
    ap.add_argument("--formato", choices=["texto", "dot", "mermaid", "svg"], default="texto")
    ap.add_argument("--blocos", action="store_true", help="agrupa em blocos básicos")
    ap.add_argument("--defuse", action="store_true", help="mostra as cadeias definição-uso")
    ap.add_argument("-o", "--saida", help="ficheiro de saída (obrigatório para svg)")
    a = ap.parse_args(argv)
    r = load_file(a.ficheiro)
    if not r.ok:
        print(r.syntax_error or "\n".join(map(str, r.errors)), file=sys.stderr)
        return 2 if r.syntax_error else 3
    pcfg = build_cfgs(r.program)
    units = list(pcfg.units.values())
    if a.unidade:
        units = [c for c in units if c.name == a.unidade or c.name.split(".")[-1] == a.unidade]
        if not units:
            print(f"não existe a regra ou cena '{a.unidade}'", file=sys.stderr)
            return 1
    if a.formato == "texto":
        out = "\n\n".join(to_text(c) for c in units) + "\n"
        if a.defuse:
            from .dataflow import def_use_chains
            for c in units:
                out += f"\nCadeias definição-uso de {c.name}:\n"
                out += "".join(f"  {d:>3} -> {u:<3} {loc}\n" for d, u, loc in def_use_chains(c))
        return emit(out, a.saida)
    g = to_graph(units[0], a.blocos, a.defuse) if len(units) == 1 else program_graph(pcfg, a.blocos)
    return emit(g, a.saida, a.formato)


if __name__ == "__main__":
    raise SystemExit(main())
