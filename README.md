# Projeto_EG 26/27

Realizado por:
- João Pedro Ferreira e Ferreira PG63984
- Tiago Rodrigues Barros PG64035

## A linguagem

Domo é uma linguagem para configurar casas inteligentes. Um programa descreve os dispositivos de uma casa, organizados por zonas, e as regras Evento-Condição-Ação que definem como a casa reage. O objetivo é detetar erros de configuração antes de o programa chegar à casa.

```
home "Estudio" {
  zone Room {
    device lamp : light;
    device motion : motion_sensor;

    rule light_on on signal motion.motion_detected {
      lamp.turn_on();
    }
  }
}
```

## A gramática

A gramática está em [domo/domo.lark](domo/domo.lark), escrita em BNF para o Lark, e é analisada com LALR(1). Tem 65 terminais, 41 não-terminais e 97 produções, sem conflitos, pelo que não é ambígua.

### Estrutura do programa

Um programa é um único `home` com uma lista de declarações. As zonas podem conter as mesmas declarações que o `home`, por isso aninham-se.

```
program: "home" STRING "{" _decl_list "}"
?decl:   zone_decl | device_decl | var_decl | group_decl | scene_decl | rule_decl
```

### Regras e eventos

Uma regra tem uma prioridade opcional, um evento, uma condição opcional e um bloco de instruções:

```
rule_decl: "rule" ID _opt_priority "on" event _opt_guard block
```

Há quatro eventos: `change` (mudança de uma propriedade), `signal` (sinal de um dispositivo), `at` (hora fixa) e `every` (repetição periódica).

### Instruções

Os blocos contêm declarações locais, atribuições, comandos, `if`, `repeat`, `for`, `wait`, `notify` e `activate`. As chavetas são obrigatórias, o que elimina a ambiguidade do *dangling else*. Não existe `while`: `repeat` e `for` são sempre finitos.

### Referências

`ref` é um caminho genérico de identificadores, como `Hall.door.lock`. A gramática não distingue zonas, dispositivos e membros, nem conhece os tipos de dispositivo: isso é decidido na análise semântica, através de um catálogo. Assim, acrescentar um tipo de dispositivo não obriga a alterar a gramática.

### Expressões

A precedência e a associatividade estão definidas na própria gramática, com uma regra por nível, da menor para a maior precedência:

| Regra | Operadores | Associatividade |
|---|---|---|
| `expr` | `or` | esquerda |
| `and_expr` | `and` | esquerda |
| `not_expr` | `not` | prefixo |
| `rel_expr` | `==` `!=` `<` `<=` `>` `>=` | não associativos: `1 < 2 < 3` é erro de sintaxe |
| `add_expr` | `+` `-` | esquerda |
| `mul_expr` | `*` `/` `%` | esquerda |
| `unary` | `-` | prefixo |

A recursão à esquerda dá a associatividade pretendida, mas faz com que a gramática não seja LL(1), o que não é problema para LALR(1).

### Léxico

- **Palavras reservadas:** são 38 e nunca podem ser usadas como nomes, por isso `var min : int = 0;` é erro. O analisador usa o lexer `basic` para garantir isto.
- **Literais:** `INT`, `REAL`, `STRING` e `TIME` (`22:30`). Não há literais negativos: `-5` é o operador `-` aplicado a `5`.
- **Horas:** `25:99` é um token `TIME` válido. A hora impossível só é rejeitada na análise semântica.
- **Ignorados:** espaços e comentários de linha (`//`).

### Convenções do Lark

- `?regra`: o nó desaparece da árvore quando só tem um filho.
- `_regra`: o nó desaparece sempre e os filhos sobem para o nó de cima.
- `-> nome`: dá um nome próprio ao nó de uma alternativa, como `-> add`.

A árvore fica assim simples. Para ver a derivação completa, usa-se a opção `--derivacao`.

## Estrutura do repositório

```
domo/              código da ferramenta (pacote Python)
  domo.lark          gramática
  parser.py          análise léxica e sintática
  semantic.py        análise semântica e catálogo de dispositivos
  analisador.py      linha de comandos da Parte I (léxica → sintática → semântica)
testes/            verificação
  __main__.py        corre a bateria de testes (python -m testes)
  casos.py           programas de teste da Parte I
  test_gramatica.py  testes da Parte I
  qualidade.py       métricas e avaliação da gramática
docs/              documentação para o relatório
  GRAMATICA_ATRIBUTOS.md, QUALIDADE.md
  enunciados/        enunciados do TP1 e do TP2
examples/          programas Domo: valid/ e invalid_semantic/ (um por código de erro)
experimentos/      estudos pontuais (avaliação do LarkAG)
```

## Como executar

Na raiz do repositório:

```
pip install -r requirements.txt

python -m domo.analisador examples/valid/02_typical.domo               # análise completa
python -m domo.analisador examples/valid/02_typical.domo --tree        # árvore sintática
python -m domo.analisador examples/valid/02_typical.domo --derivacao   # árvore de derivação


python -m testes                  # bateria de testes
python -m testes.qualidade        # métricas da gramática
```


A avaliação da linguagem e da gramática está em [docs/QUALIDADE.md](docs/QUALIDADE.md) e a especificação de parte da semântica em [docs/GRAMATICA_ATRIBUTOS.md](docs/GRAMATICA_ATRIBUTOS.md).
