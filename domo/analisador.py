#!/usr/bin/env python3
"""
Analisador léxico, sintático e semântico da linguagem Domo (CLI da Parte I).

Uso:
    python -m domo.analisador examples/valid/02_typical.domo               # resumo
    python -m domo.analisador examples/valid/02_typical.domo --tokens      # lista de tokens
    python -m domo.analisador examples/valid/02_typical.domo --tree        # árvore simplificada (a do Lark)
    python -m domo.analisador examples/valid/02_typical.domo --derivacao   # árvore de derivação completa
    python -m domo.analisador examples/valid/02_typical.domo --stats       # estatísticas

Código de saída: 0 = OK, 1 = erro léxico, 2 = erro sintático, 3 = erro semântico. 
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from lark import Tree

from domo.parser import (GRAMMAR, build_derivation_parser, build_parser, describe_error,
                         lexical_analysis, syntactic_analysis, terminal_names)
from domo.semantic import SemanticAnalyzer


def print_tokens(tokens):
    print(f"{'pos':>8}  {'tipo':<14} valor")
    print("-" * 44)
    for t in tokens:
        print(f"{t.line:>4}:{t.column:<3}  {t.type:<14} {t.value}")


def tree_depth(tree) -> int:
    if not isinstance(tree, Tree):
        return 0
    return 1 + max((tree_depth(c) for c in tree.children), default=0)


def print_stats(tokens, tree):
    print("Tokens por tipo:")
    for k, v in sorted(Counter(t.type for t in tokens).items(), key=lambda kv: -kv[1]):
        print(f"  {k:<14} {v}")
    if tree is not None:
        counts = Counter(st.data for st in tree.iter_subtrees())
        print("\nNós da árvore (construções):")
        for k in ("zone_decl", "device_decl", "var_decl", "const_decl", "group_decl",
                  "scene_decl", "rule_decl", "if_stmt", "for_stmt", "repeat_stmt",
                  "assign", "command", "wait", "notify", "activate"):
            if counts[k]:
                print(f"  {k:<14} {counts[k]}")
        print(f"\nProfundidade da árvore: {tree_depth(tree)}")


def analyse(src: str, show_tokens=False, show_tree=False, show_stats=False, out=print,
            show_derivation=False, skip_semantic=False) -> int:
    parser = build_parser()
    names = terminal_names(parser)

    tokens, lex_errors = lexical_analysis(parser, src)
    out(f"[léxica]    {len(tokens)} tokens, {len(lex_errors)} erro(s) léxico(s)")
    for e in lex_errors:
        out("  " + describe_error(e, src, names).replace("\n", "\n  "))
    if show_tokens:
        print_tokens(tokens)
    if lex_errors:
        return 1

    tree, err = syntactic_analysis(parser, src)
    if err is not None:
        out("[sintática] ERRO")
        out("  " + describe_error(err, src, names).replace("\n", "\n  "))
        return 2
    out("[sintática] OK, árvore construída")
    if show_tree:
        print(tree.pretty())
    if show_derivation:
        print(build_derivation_parser().parse(src).pretty())
    if show_stats:
        print_stats(tokens, tree)

    if not skip_semantic:
        sem = SemanticAnalyzer()
        sem_errors = sem.analyze(tree)
        if sem_errors:
            out(f"[semântica] ERRO ({len(sem_errors)} erro(s) encontrado(s))")
            for se in sem_errors:
                out(f"  {se}")
            return 3
        out("[semântica] OK, verificação concluída sem erros")

    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ficheiro")
    ap.add_argument("--tokens", action="store_true")
    ap.add_argument("--tree", action="store_true")
    ap.add_argument("--derivacao", action="store_true", help="árvore de derivação completa")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--skip-sem", action="store_true", help="ignora a verificação semântica")
    a = ap.parse_args()
    src = Path(a.ficheiro).read_text(encoding="utf-8")
    sys.exit(analyse(src, a.tokens, a.tree, a.stats, show_derivation=a.derivacao, skip_semantic=a.skip_sem))


if __name__ == "__main__":
    main()