#!/usr/bin/env python3
"""
Analisador léxico e sintático da linguagem de domótica (Lark).

Uso:
    python analisador.py casa.domo              # resumo
    python analisador.py casa.domo --tokens     # lista de tokens
    python analisador.py casa.domo --tree       # árvore sintática
    python analisador.py casa.domo --stats      # estatísticas

Código de saída: 0 = OK, 1 = erro léxico, 2 = erro sintático.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from lark import Lark
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedToken
from lark.lexer import PatternStr

GRAMMAR = Path(__file__).with_name("domo.lark")


# ------------------------------------------------------------------
#  Construção do parser
# ------------------------------------------------------------------
def build_parser(lexer: str = "basic", debug: bool = False) -> Lark:
    """LALR(1) com lexer 'basic': palavras reservadas são sempre reservadas,
    tal como a tabela A.7 do relatório."""
    return Lark.open(
        str(GRAMMAR), parser="lalr", lexer=lexer, start="start",
        propagate_positions=True, debug=debug,
    )


def terminal_names(parser: Lark) -> dict:
    """Nome de terminal -> texto legível ('{', 'home', ...)."""
    names = {"$END": "fim de ficheiro"}
    for t in parser.terminals:
        if isinstance(t.pattern, PatternStr):
            names[t.name] = f"'{t.pattern.value}'"
        else:
            names[t.name] = t.name
    return names


# ------------------------------------------------------------------
#  Análise léxica
# ------------------------------------------------------------------
def lexical_analysis(parser: Lark, src: str):
    """Devolve (tokens, erros). Recupera de erros substituindo o carácter
    ilegal por espaço, para listar todos os erros léxicos de uma vez."""
    errors, text = [], src
    for _ in range(200):                       # limite de segurança
        try:
            tokens = list(parser.lex(text))
            return tokens, errors
        except UnexpectedCharacters as e:
            errors.append(e)
            i = e.pos_in_stream
            text = text[:i] + " " + text[i + 1:]
    return [], errors


# ------------------------------------------------------------------
#  Análise sintática
# ------------------------------------------------------------------
def syntactic_analysis(parser: Lark, src: str):
    """Devolve (árvore, None) ou (None, erro)."""
    try:
        return parser.parse(src), None
    except (UnexpectedToken, UnexpectedCharacters, UnexpectedEOF) as e:
        return None, e


def describe_error(e, src: str, names: dict) -> str:
    lines = src.splitlines() or [""]
    if isinstance(e, UnexpectedEOF):
        line, col = len(lines), len(lines[-1]) + 1
        found = "fim de ficheiro"
    elif isinstance(e, UnexpectedToken):
        line, col = e.line, e.column
        found = "fim de ficheiro" if e.token.type == "$END" else f"'{e.token.value}' ({e.token.type})"
    else:                                      # UnexpectedCharacters
        line, col = e.line, e.column
        found = f"carácter {src[e.pos_in_stream]!r}"
    expected = sorted(names.get(t, t) for t in (getattr(e, "expected", None) or getattr(e, "accepts", None) or []))
    text = lines[line - 1] if 0 < line <= len(lines) else ""
    msg = [f"linha {line}, coluna {col}: encontrei {found}"]
    if expected:
        shown = ", ".join(expected[:8]) + (" ..." if len(expected) > 8 else "")
        msg.append(f"    esperava: {shown}")
    msg.append(f"    {text}")
    msg.append(f"    {' ' * (col - 1)}^")
    return "\n".join(msg)


# ------------------------------------------------------------------
#  Relatórios
# ------------------------------------------------------------------
def print_tokens(tokens):
    print(f"{'pos':>8}  {'tipo':<14} valor")
    print("-" * 44)
    for t in tokens:
        print(f"{t.line:>4}:{t.column:<3}  {t.type:<14} {t.value}")


def tree_depth(tree) -> int:
    from lark import Tree
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


def analyse(src: str, show_tokens=False, show_tree=False, show_stats=False, lexer="basic", out=print) -> int:
    parser = build_parser(lexer)
    names = terminal_names(parser)

    # 1) léxica
    tokens, lex_errors = lexical_analysis(parser, src)
    out(f"[léxica]    {len(tokens)} tokens, {len(lex_errors)} erro(s) léxico(s)")
    for e in lex_errors:
        out("  " + describe_error(e, src, names).replace("\n", "\n  "))
    if show_tokens:
        print_tokens(tokens)
    if lex_errors:
        return 1

    # 2) sintática
    tree, err = syntactic_analysis(parser, src)
    if err is not None:
        out("[sintática] ERRO")
        out("  " + describe_error(err, src, names).replace("\n", "\n  "))
        return 2
    out("[sintática] OK, árvore construída")
    if show_tree:
        print(tree.pretty())
    if show_stats:
        print_stats(tokens, tree)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ficheiro")
    ap.add_argument("--tokens", action="store_true")
    ap.add_argument("--tree", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--lexer", choices=["basic", "contextual"], default="basic")
    a = ap.parse_args()
    src = Path(a.ficheiro).read_text(encoding="utf-8")
    sys.exit(analyse(src, a.tokens, a.tree, a.stats, a.lexer))


if __name__ == "__main__":
    main()
