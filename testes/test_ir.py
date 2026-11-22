"""Fase 1: representações intermédias (CFG, cadeias definição-uso, grafo de interação, exportação)."""
import shutil
import subprocess

from domo.builder import load
from domo.cfg import DECISIONS, basic_blocks, build_cfgs, program_graph, to_graph
from domo.dataflow import def_use_chains
from domo.interaction import build_interaction
from domo.render import to_dot, to_mermaid

from .comum import Relatorio, exemplo, prog, stm
from .test_ast import programas_sintaticamente_validos

CASCATA = prog("""zone Sala {
    device lamp : dimmer; device motion : motion_sensor; device shade : blind;
    rule acende on signal motion.motion_detected { lamp.turn_on(); }
    rule apaga  on signal motion.motion_detected { lamp.turn_off(); }
    rule segue_luz on change lamp.power { shade.position = 0; }
    rule segue_estore on change shade.position { lamp.toggle(); }
  }""")

FULL = "valid/03_full.domo"

# (nome, programa, unidade, nº de nós, arestas como (tipo origem, tipo destino, etiqueta))
CASOS_CFG = [
    ("regra vazia", prog("rule R on at 10:00 { }"), "R",
     2, [("entry", "exit", "")]),
    ("guarda when", prog('var a : bool = true; rule R on at 10:00 when a { notify "x"; }'), "R",
     4, [("entry", "guard", ""), ("guard", "exit", "F"), ("guard", "notify", "V"), ("notify", "exit", "")]),
    ("if sem else", stm('if true { notify "a"; } notify "b";'), "S",
     5, [("branch", "notify", "F"), ("branch", "notify", "V"), ("entry", "branch", ""), ("notify", "exit", ""),
         ("notify", "notify", "")]),
    ("repeat com corpo vazio", stm("repeat 2 times { }"), "S",
     4, [("entry", "loop_init", ""), ("loop_init", "loop_test", ""), ("loop_test", "exit", "F"),
         ("loop_test", "loop_test", "V")]),
    ("keep_warm (if/else if/else)", FULL, "keep_warm",
     8, [("entry", "decl", ""), ("decl", "branch", ""), ("branch", "assign", "V"), ("branch", "branch", "F"),
         ("branch", "assign", "V"), ("branch", "assign", "F"), ("assign", "exit", ""), ("assign", "exit", ""),
         ("assign", "exit", "")]),
    ("bedtime (repeat + activate)", FULL, "bedtime",
     7, [("entry", "loop_init", ""), ("loop_init", "loop_test", ""), ("loop_test", "notify", "V"),
         ("notify", "wait", ""), ("wait", "loop_test", ""), ("loop_test", "call", "F"), ("call", "exit", "")]),
]

KEEP_WARM_GAP = "var gap : real = comfort - heater.current_temp"

# (nome, programa, unidade, cadeias como (rótulo de quem define, rótulo de quem usa, localização))
DEF_USE = [
    ("keep_warm: gap alimenta os dois if", FULL, "keep_warm",
     [("rule keep_warm", KEEP_WARM_GAP, "Floor1.Living.heater.current_temp"),
      (KEEP_WARM_GAP, "if gap > 0.5", "gap"), (KEEP_WARM_GAP, "if gap > 2.0", "gap")]),
    ("escrita forte apaga a anterior", stm("var x : int = 1; x = 2; var y : int = x;"), "S",
     [("x = 2", "var y : int = x", "x")]),
    ("escrita num if não apaga", prog("var c : bool = true; scene S { var x : int = 1; if c { x = 2; } var y : int = x; }"), "S",
     [("scene S", "if c", "c"), ("var x : int = 1", "var y : int = x", "x"), ("x = 2", "var y : int = x", "x")]),
    ("escrita via for é fraca",
     prog("zone Z { device a : dimmer; device b : dimmer; } group g = [Z.a, Z.b]; "
          "scene S { Z.a.brightness = 1; for l in g { l.brightness = 2; } var y : int = Z.a.brightness; }"), "S",
     [("Z.a.brightness = 1", "var y : int = Z.a.brightness", "Z.a.brightness"),
      ("l.brightness = 2", "var y : int = Z.a.brightness", "Z.a.brightness")]),
]


def fonte(src_ou_exemplo: str) -> str:
    return exemplo(src_ou_exemplo) if src_ou_exemplo.endswith(".domo") else src_ou_exemplo


def unidade(src: str, nome: str):
    """CFG da regra ou cena com este nome simples."""
    cfgs = build_cfgs(load(fonte(src)).program)
    return next(c for c in cfgs.units.values() if c.name.split(".")[-1] == nome)


def problemas_cfg(cfg):
    """Invariantes que qualquer CFG construído tem de cumprir."""
    erros = []
    if cfg.pred(cfg.entry):
        erros.append("ENTRY tem predecessores")
    if cfg.succ(cfg.exit):
        erros.append("EXIT tem sucessores")
    if cfg.reachable(cfg.entry) != set(cfg.nodes):
        erros.append("há nós inalcançáveis a partir do ENTRY")
    if cfg.reachable(cfg.exit, forward=False) != set(cfg.nodes):
        erros.append("há nós que não chegam ao EXIT")
    for n in cfg.nodes.values():
        labels = sorted(l for _, l in cfg.succ(n.id))
        if n.kind in DECISIONS and labels != ["F", "V"]:
            erros.append(f"decisão {n.id} com saídas {labels}")
        if n.kind not in DECISIONS and n.kind != "exit" and labels != [""]:
            erros.append(f"nó {n.id} ({n.kind}) com saídas {labels}")
    if sorted(n for b in basic_blocks(cfg) for n in b) != sorted(cfg.nodes):
        erros.append("os blocos básicos não particionam os nós")
    return [f"{cfg.name}: {e}" for e in erros]


def forma(cfg):
    return len(cfg.nodes), sorted((cfg.nodes[a].kind, cfg.nodes[b].kind, l) for a, b, l in cfg.edges)


def cadeias(cfg):
    return sorted((cfg.nodes[d].label.split("\n")[0], cfg.nodes[u].label, str(l)) for d, u, l in def_use_chains(cfg))


def correr(r: Relatorio):
    r.secao("Representações intermédias")
    sem_erros = [s for _, s in programas_sintaticamente_validos() if load(s).ok]
    invariantes = [e for s in sem_erros for c in build_cfgs(load(s).program).units.values() for e in problemas_cfg(c)]
    r.verifica(not invariantes, f"invariantes do CFG em {len(sem_erros)} programas válidos", invariantes[:3])

    for nome, src, uni, n_nos, arestas in CASOS_CFG:
        obtido = forma(unidade(src, uni))
        r.verifica(obtido == (n_nos, sorted(arestas)), f"CFG: {nome}", f"obtido: {obtido}")

    for nome, src, uni, esperado in DEF_USE:
        obtido = cadeias(unidade(src, uni))
        r.verifica(obtido == sorted(esperado), f"def-use: {nome}", f"obtido: {obtido}")

    ig = build_interaction(load(CASCATA).program)
    disparos = {a.split(".")[-1]: sorted(b.split(".")[-1] for b in v) for a, v in ig.triggers_between_rules().items()}
    r.verifica(disparos == {"acende": ["segue_luz"], "apaga": ["segue_luz"],
                            "segue_luz": ["segue_estore"], "segue_estore": ["segue_luz"]},
               "interação: cascata lamp.power -> shade.position -> lamp.power", f"obtido: {disparos}")
    efeitos = {str(e.loc) for e in build_interaction(load(exemplo(FULL)).program).all_effects("bedtime")}
    r.verifica({"Floor1.Hall.door.locked", "Floor2.Bedroom.heater.target_temp"} <= efeitos,
               "interação: bedtime escreve o que goodnight e eco_mode escrevem (activate encadeado)")

    grafos = []
    for s in sem_erros:
        program = load(s).program
        pc = build_cfgs(program)
        grafos += [program_graph(pc), program_graph(pc, blocks=True), build_interaction(program, pc).to_graph()]
        grafos += [to_graph(c, defuse=True) for c in pc.units.values()]
    if shutil.which("dot"):
        rejeitados = [g.title for g in grafos
                      if subprocess.run(["dot", "-Tsvg"], input=to_dot(g), capture_output=True, text=True).returncode]
        r.verifica(not rejeitados, f"{len(grafos)} grafos DOT aceites pelo Graphviz", rejeitados[:3])
    else:
        r.nota("Graphviz não instalado: DOT não verificado")
    r.verifica(all(to_mermaid(g).startswith("---") for g in grafos), f"{len(grafos)} grafos Mermaid gerados")
