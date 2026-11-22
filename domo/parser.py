"""Análise léxica e sintática da linguagem Domo (Lark, LALR(1))."""
import re
from pathlib import Path

from lark import Lark
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedToken
from lark.lexer import PatternStr

GRAMMAR = Path(__file__).with_name("domo.lark")


def build_parser(debug: bool = False) -> Lark:
    """LALR(1) com lexer 'basic': palavras reservadas são sempre reservadas,
    tal como a tabela A.7 do relatório."""
    return Lark.open(
        str(GRAMMAR), parser="lalr", lexer="basic", start="start",
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


def build_derivation_parser() -> Lark:
    """Segundo analisador, construído a partir do MESMO domo.lark, mas sem as
    simplificações da árvore: '?regra' e '_regra' passam a regras normais e todos
    os tokens são mantidos. O resultado é a árvore de derivação (um nó por regra
    usada). Os aliases (-> add, -> assign...) mantêm-se: identificam a produção."""
    text = GRAMMAR.read_text(encoding="utf-8")
    text = re.sub(r"^\?(\w+)", r"\1", text, flags=re.M)
    text = re.sub(r"\b_([a-z]\w*)", r"\1", text)
    return Lark(text, parser="lalr", lexer="basic", start="start", keep_all_tokens=True)


def lexical_analysis(parser: Lark, src: str):
    """Devolve (tokens, erros). Recupera de erros substituindo o carácter
    ilegal por espaço, para listar todos os erros léxicos de uma vez."""
    errors, text = [], src
    for _ in range(200):
        try:
            tokens = list(parser.lex(text))
            return tokens, errors
        except UnexpectedCharacters as e:
            errors.append(e)
            i = e.pos_in_stream
            text = text[:i] + " " + text[i + 1:]
    return [], errors


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
    else:
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
