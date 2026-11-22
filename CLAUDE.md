# CLAUDE.md — Projeto Domo (Engenharia Gramatical 26/27, UMinho)

Projeto da UC de Engenharia Gramatical (Mestrado em Eng. Informática, UMinho). Grupo: João Pedro Ferreira (PG63984) e Tiago Barros (PG64035). Toda a documentação, mensagens de erro e comentários estão em **português de Portugal** — manter esse registo.

Enunciados em [docs/enunciados/](docs/enunciados/) (não versionados): `TP1 2627.pdf` (Parte I, entregue a 4 nov) e `TP2 2627.pdf` (Parte II, **entrega 14 jan 2027 via GitHub, apresentação 15 jan**, 10 min + demo).

## A linguagem Domo

DSL para configurar casas inteligentes. Um programa = um único `home "nome" { ... }` com declarações; o objetivo é detetar erros de configuração antes de chegar à casa.

- **Declarações** (em `home` e em `zone`, que se aninham): `zone`, `device nome : tipo;`, `var`/`const nome : tipo = expr;`, `group g = [refs];`, `scene nome { ... }`, `rule nome [priority N] on <evento> [when expr] { ... }`.
- **Eventos**: `change ref` (propriedade), `signal ref` (evento de dispositivo), `at HH:MM`, `every N sec|min|hour`.
- **Instruções** (em blocos): declaração local, atribuição `ref = expr;`, comando `ref(args);`, `if/else if/else` (chavetas obrigatórias), `repeat expr times {}`, `for x in grupo {}`, `wait duração;`, `notify "txt";`, `activate cena;`. Não há `while` — tudo termina.
- **Tipos**: `int`, `real`, `bool`, `string`, `time` (+ tipos de dispositivo). `int → real` é a única coerção.
- **Referências** `ref` são caminhos genéricos (`Floor1.Hall.door.lock`); a gramática não distingue zona/dispositivo/membro — isso é feito pela semântica via catálogo.
- **Âmbitos**: nas zonas a ordem das declarações é livre (pode usar-se antes de declarar); nos blocos é sequencial. Variáveis ao nível da zona/home exigem inicializador constante.

## Estrutura

`domo/` = pacote da toolchain (tudo o que corre); `testes/` = verificação (testes + métricas da gramática); `docs/` = capítulos do relatório em Markdown + enunciados; `examples/` = programas Domo; `experimentos/` = estudos pontuais. **Não deixar scripts soltos na raiz**: código novo vai para `domo/` (executável com `python -m domo.<módulo>`), testes novos para `testes/test_<fase>.py` (registar em `testes/__main__.py`), documentação para `docs/`.

| Ficheiro | Papel |
|---|---|
| [domo/domo.lark](domo/domo.lark) | Gramática em **BNF puro** para Lark, LALR(1), lexer `basic`, 0 conflitos. 65 terminais / 41 não-terminais / 97 produções. Precedência codificada em níveis (`expr` → `and_expr` → `not_expr` → `rel_expr` → `add_expr` → `mul_expr` → `unary` → `primary`); relacionais não associativos. 38 palavras reservadas. |
| [domo/analisador.py](domo/analisador.py) | CLI da Parte I (`python -m domo.analisador`): léxica → sintática → semântica. Flags `--tokens --tree --derivacao --stats --skip-sem`. Exit codes: 0 OK, 1 léxico, 2 sintático, 3 semântico. |
| [domo/parser.py](domo/parser.py) | `build_parser()` (LALR, lexer `basic`, posições), `build_derivation_parser()` (reescreve o .lark sem `?`/`_` para mostrar a derivação completa), `lexical_analysis`, `syntactic_analysis`, `describe_error`. |
| [domo/ast.py](domo/ast.py) | AST elaborado em dataclasses (`Program`, `Zone`, `Device`, `VarDecl`, `Group`, `Scene`, `Rule`, eventos `OnChange/OnSignal/At/Every`, instruções `Assign/Command/If/Repeat/For/Wait/Notify/Activate`, expressões `Binary/Unary/Ref/...Lit`). Anotações semânticas (`Ref.res` → `Resolution` com símbolo + membro, `Expr.type`, `.sym` nas declarações) e posições **não entram no `==`**. `walk(node)` percorre em pré-ordem. |
| [domo/builder.py](domo/builder.py) | Árvore Lark → AST. Não recalcula nada: copia `resolutions`, `expr_types` e `decl_symbols` que o `SemanticAnalyzer` regista (chave = `id` do nó Lark). `load(src)`/`load_file(path)` → `Frontend(program, syntax_error, errors)`. `python -m domo.builder f.domo` mostra o AST anotado. |
| [domo/pretty.py](domo/pretty.py) | AST → código Domo; parênteses só onde a precedência/associatividade obriga. `python -m domo.pretty f.domo`. Perde comentários. |
| [domo/locations.py](domo/locations.py) | `Loc(símbolo, membro)`: variáveis e propriedades de dispositivos (constantes excluídas). `Locator`: leituras/escritas por expressão/instrução; comandos escrevem via `DEVICE_CATALOG[...]["effects"]`; escritas via variável de `for` são fracas (expande para os membros do grupo). |
| [domo/cfg.py](domo/cfg.py) | CFG por regra/cena (`build_cfgs` → `ProgramCFG` com `units`, `by_symbol`, `call_edges`). Nós: entry exit guard branch loop_init loop_test assign command decl wait notify call; decisões com arestas V/F. `basic_blocks`, `to_graph`, `program_graph` (interprocedimental), `python -m domo.cfg`. |
| [domo/dataflow.py](domo/dataflow.py) | Framework `Analysis` + `solve` (worklist até ponto fixo, forward/backward). `ReachingDefinitions` (ENTRY = valor vindo de fora), `def_use_chains`. Base das análises da Fase 2. |
| [domo/interaction.py](domo/interaction.py) | Grafo de interação de regras (IR de domínio): `triggers`, `effects`, `activates`, `reads`, `all_effects` (segue activate), `triggers_between_rules`. `python -m domo.interaction`. |
| [domo/render.py](domo/render.py) | `Graph/GNode/GEdge` → DOT, Mermaid, SVG (via `dot`). |
| [docs/REPRESENTACOES.md](docs/REPRESENTACOES.md) | Capítulo das IR para o relatório (decisões, exemplos Mermaid, verificação, limitações). |
| [domo/semantic.py](domo/semantic.py) | `SemanticAnalyzer` sobre a árvore Lark. Regista para o AST: `resolutions`, `expr_types`, `decl_symbols`; `Symbol.qualname` (`Floor1.Living.lamp`). `DEVICE_CATALOG` (light, dimmer, thermostat, motion_sensor, temp_sensor, door_lock, blind, plug — props com tipo/ro-rw, comandos com tipos de argumentos, eventos, ranges). Fases: `pass1_collect` (símbolos/zonas) → `check_groups` (tipo comum dos grupos) → `pass2_check` (tipos, acessos, eventos) → `check_cycles` (ciclos em `activate` entre cenas e em inicializações de constantes). `const_value` faz avaliação constante (usada em `outOfRange`, `divisionByZero`). |
| [testes/](testes/) | `python -m testes [gramatica ast ir]`. `comum.py`: `Relatorio` (cada `verifica()` = 1 teste, conta sozinho), `prog`/`stm`, `exemplo()`, leitura de `examples/` (inválidos declaram `// expect: <codigo>`). `casos.py`: `CASOS` (OK/LEX/SYN/SEM) e `CASOS_CODIGOS`. `test_gramatica.py` (Parte I + 0 conflitos LALR), `test_ast.py` (ida e volta `parse(pretty(p)) == p`, 500 expressões aleatórias, AST anotado), `test_ir.py` (invariantes do CFG, formas, def-use, interação, DOT/Mermaid). |
| [testes/qualidade.py](testes/qualidade.py) | `python -m testes.qualidade`. Métricas da gramática (Power & Malloy), deteção de conflitos, cobertura de produções, mutação por remoção de tokens. Alimenta [docs/QUALIDADE.md](docs/QUALIDADE.md). |
| [docs/GRAMATICA_ATRIBUTOS.md](docs/GRAMATICA_ATRIBUTOS.md) | Gramática de atributos (subconjunto): `decls`, `env`, `envIn/envOut`, `gtypes`, `type`, `const`, `calls`, `errors`; ordem de avaliação em 4 fases e mapeamento para `semantic.py`. |
| [examples/](examples/) | `valid/01_minimal`, `02_typical`, `03_full` (casa completa com 2 pisos, cenas, grupos, regras — o exemplo de referência) e 20 inválidos semânticos, um por código de erro. |

Códigos de erro semântico: `typeMismatch readOnly noSuchMember undeclared duplicate assignToConst unknownDeviceType heterogeneousGroup invalidTime zeroPeriod notAnEvent notAProperty notAScene condNotBool cyclicActivation cyclicInit notConstant notAssignable outOfRange divisionByZero`.

O relatório da Parte I **não está no repositório** (refere "Tabela 4/8/9/11 do relatório"); a Parte II exige continuá-lo e estendê-lo.

## Como correr

```
.venv/bin/python ...                   # venv em .venv (Python 3.14, lark 1.3.1, lark-ag só para o experimento); o python3 do sistema não tem lark
pip install -r requirements.txt
python -m domo.analisador examples/valid/03_full.domo [--tree|--derivacao|--tokens|--stats]
python -m domo.builder|pretty|cfg|interaction examples/valid/03_full.domo
python -m testes
python -m testes.qualidade
```

Correr sempre a partir da raiz do repositório. Depois de alterar a gramática: correr `python -m testes` e `python -m testes.qualidade` e atualizar números no README e em docs/QUALIDADE.md.

## Convenções e decisões de design

- Lark: `?regra` colapsa nós unitários, `_regra` funde filhos no pai, `-> alias` nomeia alternativas. Os nós da árvore usam os aliases (`assign`, `command`, `ev_signal`, `add`, `int_lit`, ...).
- A gramática é permissiva de propósito (tipos de dispositivo são `ID`); acrescentar dispositivos = mexer só em `DEVICE_CATALOG`.
- Erros semânticos não cascateiam: tipo `None` (⊥) suprime erros dependentes.
- Estilo do código: Python simples, sem dependências além de Lark, funções curtas, mensagens em PT.
- Git: trabalho em branches (`musk`, `danran1`, `danran2`) com merge para `main` via PR.

## Parte II (TP2) — o que é pedido

Toolchain sobre a linguagem: (1) **CFG** obrigatório + outras IR opcionais (DFG/PDG/específicas do domínio); (2) ≥1 **análise estática** relevante para o domínio (propósito, abordagem, pressupostos, resultados, limitações); (3) ≥1 **transformação** com evidência de preservação de significado; (4) **integração/front-end** (CLI, notebook, visualizações ou IDE) com arquitetura explicada. Entregáveis: relatório da Parte I estendido, código + instruções, apresentação de 10 min com demo. Alterações à gramática/AST/semântica são permitidas mas têm de ser justificadas no relatório.

### Plano aprovado (22 nov 2026)

Pacote `domo/`; ainda faltam `analyses`, `interp`, `transform`, `cli` (`python -m domo`).

0. **Fundação** (→ 30 nov): ~~teste do LarkAG~~ **feito, rejeitado** (ver [experimentos/larkag/README.md](experimentos/larkag/README.md): só Earley, não aceita `?`/`_`/aliases nem nomes com `_`, avaliador de uma visita não suporta o `env` das zonas, para no 1.º erro e sem posições). A semântica fica em Python. AST elaborado + pretty-printer **feitos** (`domo/ast.py`, `builder.py`, `pretty.py`).
1. **IR** (→ 10 dez, **feita**): CFG por regra/cena (`when`, `if`, `repeat`, `for`, `activate` como chamada), def-use sobre variáveis e propriedades de dispositivos, **grafo de interação de regras** (evento → regra → propriedade → `change`). Exportação DOT + Mermaid.
2. **Análises** (→ 20 dez): núcleo = conflitos entre regras (comandos/escritas opostas no mesmo evento, sem `priority`) e cascatas cíclicas; extra = framework de fluxo de dados com propagação de constantes (ramos mortos, guardas impossíveis) e liveness (atribuições mortas, declarações não usadas). Saem como avisos.
3. **Interpretador + transformação** (→ 31 dez): simulador por traces de eventos; simplificador fonte-a-fonte (dobragem de constantes, ramos mortos, inlining de cenas, desenrolar `for`/`repeat`); correção por testes diferenciais no interpretador + idempotência. Opcional: Domo → Home Assistant YAML.
4. **Toolchain** (→ 7 jan): `python -m domo {check,ast,cfg,graph,analyze,transform,simulate,report}`, relatório HTML com grafos, extensão VS Code com realce de sintaxe e diagnósticos.
5. **Testes, relatório, apresentação** (→ 14 jan): `examples/warnings/` com `// expect:`, capítulos novos no relatório e secção "alterações à Parte I".
