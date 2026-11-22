"""Framework de análise de fluxo de dados sobre o CFG, e definições que chegam (reaching
definitions) com as cadeias definição-uso.

Uma análise diz, para cada nó do CFG, um "facto" (um valor de um reticulado) à entrada
(IN) e à saída (OUT). Define-se com:

- direção: forward (os factos seguem as setas) ou backward (vão contra as setas);
- boundary: o facto no início (ENTRY, se forward; EXIT, se backward);
- bottom: o facto inicial dos outros nós (o mais "otimista");
- join: como combinar os factos que chegam de vários caminhos;
- transfer: como um nó transforma o facto que lhe chega.

solve() aplica as equações até nada mudar (ponto fixo), com uma lista de trabalho.
Termina porque os factos só podem crescer no reticulado e este é finito.
"""
from typing import Dict, Generic, Iterable, List, Set, Tuple, TypeVar

from .cfg import CFG, CFGNode
from .locations import Loc

T = TypeVar("T")


class Analysis(Generic[T]):
    forward = True

    def boundary(self, cfg: CFG) -> T:
        raise NotImplementedError

    def bottom(self, cfg: CFG) -> T:
        raise NotImplementedError

    def join(self, facts: Iterable[T]) -> T:
        raise NotImplementedError

    def transfer(self, node: CFGNode, fact: T) -> T:
        raise NotImplementedError


def solve(cfg: CFG, analysis: Analysis[T]) -> Tuple[Dict[int, T], Dict[int, T]]:
    """Devolve (IN, OUT): o facto à entrada e à saída de cada nó.
    Para uma análise backward, IN é o facto antes do nó na ordem de execução e OUT depois."""
    fwd = analysis.forward
    start = cfg.entry if fwd else cfg.exit
    before = (lambda n: [p for p, _ in cfg.pred(n)]) if fwd else (lambda n: [s for s, _ in cfg.succ(n)])
    after = (lambda n: [s for s, _ in cfg.succ(n)]) if fwd else (lambda n: [p for p, _ in cfg.pred(n)])

    first = {n: analysis.bottom(cfg) for n in cfg.nodes}   # facto antes do nó (no sentido da análise)
    last = {n: analysis.bottom(cfg) for n in cfg.nodes}    # facto depois do nó
    first[start] = analysis.boundary(cfg)
    work = list(cfg.nodes)
    while work:
        n = work.pop(0)
        if n != start:
            first[n] = analysis.join(last[p] for p in before(n))
        new = analysis.transfer(cfg.nodes[n], first[n])
        if new != last[n]:
            last[n] = new
            work.extend(m for m in after(n) if m not in work)
    return (first, last) if fwd else (last, first)


# ---------------------------------------------------------------- definições que chegam

Definition = Tuple[int, Loc]     # (nó que escreve, localização); o nó ENTRY é o valor vindo de fora


class ReachingDefinitions(Analysis[frozenset]):
    """Que escritas podem ter dado o valor atual de cada localização.

    O ENTRY conta como uma definição de todas as localizações usadas: representa o valor
    que vem de fora da regra (inicialização, outras regras, sensores).
    Uma escrita forte apaga as definições anteriores da mesma localização; uma fraca
    (no corpo de um for sobre um grupo) só acrescenta."""

    def boundary(self, cfg):
        locs = set().union(*(n.uses | n.defs for n in cfg.nodes.values()))
        return frozenset((cfg.entry, l) for l in locs)

    def bottom(self, cfg):
        return frozenset()

    def join(self, facts):
        return frozenset().union(*facts)

    def transfer(self, node, fact):
        if not node.defs:
            return fact
        kept = {d for d in fact if not (node.strong and d[1] in node.defs)}
        return frozenset(kept | {(node.id, l) for l in node.defs})


def def_use_chains(cfg: CFG) -> List[Tuple[int, int, Loc]]:
    """(nó que define, nó que usa, localização) para cada leitura e cada definição que a
    pode alimentar. Uma definição no ENTRY significa 'valor vindo de fora desta unidade'."""
    rd_in, _ = solve(cfg, ReachingDefinitions())
    chains = []
    for n in cfg.nodes.values():
        for loc in n.uses:
            for d, l in rd_in[n.id]:
                if l == loc:
                    chains.append((d, n.id, loc))
    return sorted(chains, key=lambda c: (c[1], c[0], str(c[2])))
