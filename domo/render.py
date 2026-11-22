"""Exportação de grafos para DOT (Graphviz) e Mermaid.

Os módulos cfg.py e interaction.py descrevem os seus grafos com Graph/GNode/GEdge;
este módulo só trata do formato de saída.
"""
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

SHAPES_DOT = {"box": "box", "diamond": "diamond", "oval": "ellipse", "hexagon": "hexagon",
              "rounded": "box", "note": "note"}
SHAPES_MERMAID = {"box": ('["', '"]'), "diamond": ('{"', '"}'), "oval": ('(["', '"])'),
                  "hexagon": ('{{"', '"}}'), "rounded": ('("', '")'), "note": ('>"', '"]')}


@dataclass
class GNode:
    id: str
    label: str
    shape: str = "box"          # box diamond oval hexagon rounded note
    style: str = ""             # "" ou bold


@dataclass
class GEdge:
    src: str
    dst: str
    label: str = ""
    style: str = ""             # "" dashed bold


@dataclass
class Graph:
    title: str = ""
    nodes: List[GNode] = field(default_factory=list)
    edges: List[GEdge] = field(default_factory=list)
    clusters: Dict[str, List[str]] = field(default_factory=dict)   # título -> ids dos nós


def _dot_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def to_dot(g: Graph) -> str:
    out = ["digraph G {", f"  label={_dot_str(g.title)}; labelloc=t;",
           '  node [fontname="Helvetica", fontsize=11]; edge [fontname="Helvetica", fontsize=10];']
    in_cluster = {n for ids in g.clusters.values() for n in ids}

    def node_line(n: GNode) -> str:
        attrs = [f"label={_dot_str(n.label)}", f"shape={SHAPES_DOT[n.shape]}"]
        styles = [s for s in (n.style, "rounded" if n.shape == "rounded" else "") if s]
        if styles:
            attrs.append(f'style="{",".join(styles)}"')
        return f"{n.id} [{', '.join(attrs)}];"

    by_id = {n.id: n for n in g.nodes}
    for i, (title, ids) in enumerate(g.clusters.items()):
        out.append(f"  subgraph cluster_{i} {{")
        out.append(f"    label={_dot_str(title)}; style=rounded; color=gray;")
        out.extend(f"    {node_line(by_id[n])}" for n in ids)
        out.append("  }")
    out.extend(f"  {node_line(n)}" for n in g.nodes if n.id not in in_cluster)
    for e in g.edges:
        attrs = []
        if e.label:
            attrs.append(f"label={_dot_str(e.label)}")
        if e.style:
            attrs.append(f"style={e.style}")
        if e.style == "dashed":
            attrs.append("color=gray40")
        out.append(f"  {e.src} -> {e.dst}" + (f" [{', '.join(attrs)}]" if attrs else "") + ";")
    out.append("}")
    return "\n".join(out) + "\n"


def _mm_str(s: str) -> str:
    return s.replace('"', "#quot;").replace("\n", "<br/>")


def to_mermaid(g: Graph) -> str:
    out = ["flowchart TD"]
    if g.title:
        out.insert(0, f"---\ntitle: {g.title}\n---")
    in_cluster = {n for ids in g.clusters.values() for n in ids}

    def node_line(n: GNode) -> str:
        a, b = SHAPES_MERMAID[n.shape]
        return f"{n.id}{a}{_mm_str(n.label)}{b}"

    by_id = {n.id: n for n in g.nodes}
    for i, (title, ids) in enumerate(g.clusters.items()):
        out.append(f'  subgraph c{i} ["{_mm_str(title)}"]')
        out.extend(f"    {node_line(by_id[n])}" for n in ids)
        out.append("  end")
    out.extend(f"  {node_line(n)}" for n in g.nodes if n.id not in in_cluster)
    for e in g.edges:
        arrow = {"dashed": "-.->", "bold": "==>"}.get(e.style, "-->")
        label = f'|"{_mm_str(e.label)}"|' if e.label else ""
        out.append(f"  {e.src} {arrow}{label} {e.dst}")
    bold = [n.id for n in g.nodes if n.style == "bold"]
    if bold:
        out.append("  classDef destaque stroke-width:3px;")
        out.append(f"  class {','.join(bold)} destaque;")
    return "\n".join(out) + "\n"


def to_svg(g: Graph) -> str:
    if not shutil.which("dot"):
        raise RuntimeError("o formato svg precisa do Graphviz (comando 'dot'); use --formato dot ou mermaid")
    return subprocess.run(["dot", "-Tsvg"], input=to_dot(g), capture_output=True, text=True, check=True).stdout


def emit(content, path: Optional[str], fmt: str = "texto") -> int:
    """Escreve texto ou um Graph no formato pedido, para um ficheiro ou para o ecrã."""
    if isinstance(content, Graph):
        content = {"dot": to_dot, "mermaid": to_mermaid, "svg": to_svg}[fmt](content)
    if path:
        Path(path).write_text(content, encoding="utf-8")
        print(f"escrito {path}", file=sys.stderr)
    else:
        sys.stdout.write(content)
    return 0
