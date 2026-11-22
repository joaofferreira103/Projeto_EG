"""Localizações: o estado que um programa Domo lê e escreve.

Há dois tipos:
- variáveis (globais da casa/zona, ou locais de um bloco): Loc(símbolo);
- propriedades de dispositivos, que são o estado da casa: Loc(dispositivo, "brightness").

As constantes ficam de fora, porque nunca mudam.

Dentro de `for l in grupo`, `l.brightness = 0` pode escrever em qualquer elemento do
grupo. É por isso uma escrita fraca ("may"): acrescenta uma definição sem apagar as outras.
Uma escrita num dispositivo concreto é forte ("must") e substitui a anterior.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from . import ast as A
from .semantic import DEVICE_CATALOG, Symbol


@dataclass(frozen=True)
class Loc:
    symbol: Symbol                      # variável ou dispositivo (comparado por identidade)
    member: Optional[str] = None        # propriedade, se for um dispositivo

    @property
    def is_property(self) -> bool:
        return self.member is not None

    def __str__(self) -> str:
        return self.symbol.qualname + (f".{self.member}" if self.member else "")


class Locator:
    """Calcula as localizações lidas e escritas por expressões e instruções."""

    def __init__(self, program: A.Program):
        # grupo -> dispositivos; variável de um for -> dispositivos do grupo percorrido
        self.members: Dict[Symbol, List[Symbol]] = {}
        for n in program.walk():
            if isinstance(n, A.Group) and n.sym:
                self.members[n.sym] = [m.symbol for m in n.members if m.symbol]
        for n in program.walk():
            if isinstance(n, A.For) and n.sym and n.group.symbol in self.members:
                self.members[n.sym] = self.members[n.group.symbol]

    def devices(self, sym: Symbol) -> Tuple[List[Symbol], bool]:
        """Dispositivos designados por sym e se a designação é exata (não é uma variável de ciclo)."""
        if sym in self.members:
            return self.members[sym], False
        return [sym], True

    # ------------------------------------------------------------ leituras

    def uses(self, expr: Optional[A.Expr]) -> Set[Loc]:
        """Localizações lidas por uma expressão."""
        out: Set[Loc] = set()
        if expr is None:
            return out
        for n in A.walk(expr):
            if not isinstance(n, A.Ref) or n.res is None:
                continue
            if n.kind == "var":
                out.add(Loc(n.symbol))
            elif n.kind == "property":
                devs, _ = self.devices(n.symbol)
                out.update(Loc(d, n.member) for d in devs)
        return out

    def stmt_uses(self, s) -> Set[Loc]:
        if isinstance(s, A.VarDecl):
            return self.uses(s.init)
        if isinstance(s, A.Assign):
            return self.uses(s.value)
        if isinstance(s, A.Command):
            return set().union(*(self.uses(a) for a in s.args))
        return set()

    # ------------------------------------------------------------ escritas

    def stmt_defs(self, s) -> Tuple[Set[Loc], bool]:
        """(localizações escritas, se a escrita é forte)."""
        if isinstance(s, A.VarDecl) and s.sym:
            return {Loc(s.sym)}, True
        if isinstance(s, A.Assign) and s.target.res:
            t = s.target
            if t.kind == "var":
                return {Loc(t.symbol)}, True
            if t.kind == "property":
                devs, exact = self.devices(t.symbol)
                return {Loc(d, t.member) for d in devs}, exact
        if isinstance(s, A.Command) and s.target.res and s.target.kind == "command":
            devs, exact = self.devices(s.target.symbol)
            locs = set()
            for d in devs:
                effects = DEVICE_CATALOG.get(d.type_name, {}).get("effects", {})
                locs.update(Loc(d, p) for p in effects.get(s.target.member, []))
            return locs, exact
        return set(), True
