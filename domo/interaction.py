"""Grafo de interação de regras: a representação intermédia específica do domínio.

O CFG mostra o que acontece dentro de uma regra. Numa linguagem Evento-Condição-Ação
o comportamento importante está entre regras: uma regra muda uma propriedade, e essa
mudança dispara outra regra. Este grafo torna isso explícito.

Nós:
    evento      signal motion.motion_detected, at 23:00, every 5 min
    regra       Floor1.Living.welcome
    cena        goodnight
    propriedade Floor1.Living.lamp.power (só as que são escritas ou observadas)

Arestas:
    evento -> regra          "dispara":  a regra reage a este evento
    propriedade -> regra     "change":   a regra reage a mudanças desta propriedade
    regra/cena -> propriedade a regra escreve-a (atribuição ou efeito de um comando)
    regra/cena -> cena       "activate"

Um caminho regra A -> propriedade P -> regra B quer dizer que A pode disparar B.
Um ciclo quer dizer que as regras se podem disparar umas às outras indefinidamente.
É a base das análises de conflitos e de cascatas (Fase 2).

As escritas vêm dos nós do CFG (CFGNode.defs), por isso incluem as que estão dentro de
if e de ciclos: o grafo diz o que *pode* acontecer, não o que acontece sempre.

Uso: python -m domo.interaction ficheiro.domo [--formato texto|dot|mermaid|svg] [-o saida]
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from . import ast as A
from .cfg import CFG, ProgramCFG, build_cfgs
from .locations import Loc
from .pretty import event as event_text, expr as expr_text, time as time_text


@dataclass(frozen=True)
class Trigger:
    """Evento que dispara regras. key identifica eventos iguais (duas regras 'at 07:00')."""
    kind: str                   # signal change at every
    key: object                 # Loc (signal/change), minutos (at) ou segundos (every)
    text: str

    def __str__(self):
        return self.text


@dataclass
class Effect:
    """Uma escrita feita por uma regra ou cena."""
    unit: str                   # nome qualificado da regra/cena
    loc: Loc
    node: int                   # nó do CFG
    stmt: A.Stmt
    via_group: bool             # feita através da variável de um for (um elemento do grupo por iteração)

    @property
    def how(self) -> str:
        if isinstance(self.stmt, A.Command):
            return f"{self.stmt.target.member}()"
        return f"= {expr_text(self.stmt.value)}"


@dataclass
class InteractionGraph:
    cfgs: ProgramCFG
    triggers: Dict[str, Trigger] = field(default_factory=dict)          # regra -> evento
    effects: Dict[str, List[Effect]] = field(default_factory=dict)      # regra/cena -> escritas diretas
    activates: Dict[str, Set[str]] = field(default_factory=dict)        # regra/cena -> cenas
    reads: Dict[str, Set[Loc]] = field(default_factory=dict)            # regra/cena -> leituras (incl. guarda)

    @property
    def rules(self) -> List[str]:
        return [n for n, c in self.cfgs.units.items() if c.kind == "rule"]

    def all_effects(self, unit: str, _seen=None) -> List[Effect]:
        """Escritas de unit e das cenas que ativa, direta ou indiretamente."""
        seen = _seen if _seen is not None else set()
        if unit in seen:
            return []
        seen.add(unit)
        out = list(self.effects.get(unit, []))
        for scene in sorted(self.activates.get(unit, ())):
            out += self.all_effects(scene, seen)
        return out

    def rules_triggered_by(self, loc: Loc) -> List[str]:
        """Regras 'on change loc'."""
        return [r for r, t in self.triggers.items() if t.kind == "change" and t.key == loc]

    def triggers_between_rules(self) -> Dict[str, Set[str]]:
        """Regra -> regras que pode disparar (por mudar uma propriedade que elas observam)."""
        out = {}
        for r in self.rules:
            out[r] = {r2 for e in self.all_effects(r) for r2 in self.rules_triggered_by(e.loc)}
        return out

    # ------------------------------------------------------------ visualização

    def to_graph(self):
        from .render import Graph, GNode, GEdge
        g = Graph(title="Grafo de interação de regras")
        ids: Dict[object, str] = {}

        def node(key, label, shape, style=""):
            if key not in ids:
                ids[key] = f"x{len(ids)}"
                g.nodes.append(GNode(ids[key], label, shape, style))
            return ids[key]

        prop_ids: Dict[Loc, str] = {}

        def prop(loc: Loc):
            if loc not in prop_ids:
                prop_ids[loc] = node(("prop", loc), str(loc), "hexagon")
            return prop_ids[loc]

        for name, cfg in self.cfgs.units.items():
            node(("unit", name), name, "box" if cfg.kind == "rule" else "rounded", "bold" if cfg.kind == "rule" else "")
        for rule, t in self.triggers.items():
            r = ids[("unit", rule)]
            if t.kind == "change":
                g.edges.append(GEdge(prop(t.key), r, "change", "bold"))
            else:
                g.edges.append(GEdge(node(("ev", t.kind, t.key), t.text, "oval"), r, "dispara"))
        for unit, effects in self.effects.items():
            seen = set()
            for e in effects:
                if (e.loc, e.how) in seen:
                    continue
                seen.add((e.loc, e.how))
                g.edges.append(GEdge(ids[("unit", unit)], prop(e.loc), e.how + (" (for)" if e.via_group else "")))
        for unit, scenes in self.activates.items():
            for s in sorted(scenes):
                g.edges.append(GEdge(ids[("unit", unit)], ids[("unit", s)], "activate", "dashed"))
        return g

    def to_text(self) -> str:
        out = ["Regras e eventos:"]
        for r in self.rules:
            out.append(f"  {r:<32} on {self.triggers[r]}")
        out.append("\nEscritas (diretas e através das cenas ativadas):")
        for unit in self.cfgs.units:
            effects = self.all_effects(unit)
            if effects:
                items = sorted({f"{e.loc} {e.how}" + (" (via for)" if e.via_group else "") for e in effects})
                out.append(f"  {unit}:")
                out.extend(f"    {i}" for i in items)
        out.append("\nRegras que uma regra pode disparar:")
        chains = {r: s for r, s in self.triggers_between_rules().items() if s}
        out.extend(f"  {r} -> {', '.join(sorted(s))}" for r, s in chains.items())
        if not chains:
            out.append("  nenhuma")
        return "\n".join(out) + "\n"


def trigger_of(rule: A.Rule) -> Trigger:
    ev = rule.event
    if isinstance(ev, (A.OnChange, A.OnSignal)):
        ref = ev.target
        key = Loc(ref.symbol, ref.member) if ref.res else str(ref)
        return Trigger("change" if isinstance(ev, A.OnChange) else "signal", key,
                       f"{'change' if isinstance(ev, A.OnChange) else 'signal'} {key}")
    if isinstance(ev, A.At):
        return Trigger("at", ev.time.minutes, f"at {time_text(ev.time)}")
    return Trigger("every", ev.period.seconds, event_text(ev))


def build_interaction(program: A.Program, cfgs: Optional[ProgramCFG] = None) -> InteractionGraph:
    cfgs = cfgs or build_cfgs(program)
    ig = InteractionGraph(cfgs)
    for name, cfg in cfgs.units.items():
        if cfg.kind == "rule":
            ig.triggers[name] = trigger_of(cfg.decl)
        ig.effects[name] = [Effect(name, loc, n.id, n.ast, not n.strong)
                            for n in cfg.nodes.values() for loc in sorted(n.defs, key=str)
                            if loc.is_property]
        ig.activates[name] = {cfgs.by_symbol[n.callee].name for n in cfg.nodes.values()
                              if n.kind == "call" and n.callee in cfgs.by_symbol}
        ig.reads[name] = set().union(*(n.uses for n in cfg.nodes.values()))
    return ig


def main(argv=None):
    import argparse
    import sys
    from .builder import load_file
    from .render import emit
    ap = argparse.ArgumentParser(description="Grafo de interação de regras.")
    ap.add_argument("ficheiro")
    ap.add_argument("--formato", choices=["texto", "dot", "mermaid", "svg"], default="texto")
    ap.add_argument("-o", "--saida")
    a = ap.parse_args(argv)
    r = load_file(a.ficheiro)
    if not r.ok:
        print(r.syntax_error or "\n".join(map(str, r.errors)), file=sys.stderr)
        return 2 if r.syntax_error else 3
    ig = build_interaction(r.program)
    if a.formato == "texto":
        return emit(ig.to_text(), a.saida)
    return emit(ig.to_graph(), a.saida, a.formato)


if __name__ == "__main__":
    raise SystemExit(main())
