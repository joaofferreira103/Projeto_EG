# Gramática de atributos

Este documento especifica um subconjunto da semântica da linguagem Domo: âmbitos e declarações, membros de dispositivos e tipos das expressões. As produções são as de [domo.lark](../domo/domo.lark), sem o prefixo `_` nos nomes das regras e com as produções unitárias simplificadas.

A parte mais relevante é a ordem de avaliação: numa zona, a ordem das declarações é livre, e num bloco não é. A gramática exprime esta diferença só com as dependências entre atributos.

## 1. Domínios e funções auxiliares

| Nome | Definição |
|---|---|
| `Tipo` | `int`, `real`, `bool`, `string`, `time`, um tipo de dispositivo ou `⊥` (tipo desconhecido, após um erro) |
| `Sym` | `zone(Frame)`, `device(tipo)`, `var(Tipo)`, `const(Tipo)`, `group(id)`, `scene(id)` ou `rule` |
| `Frame` | Mapa de nomes para `Sym`: as declarações de um âmbito |
| `Env` | Lista de `Frame`, do âmbito mais externo para o mais interno |
| `Info` | Resultado de resolver uma referência: `(categoria, Tipo, acesso)`, ou `⊥` |

| Função | Resultado |
|---|---|
| `lookup(env, x)` | Procura `x` do `Frame` mais interno para o mais externo |
| `resolve(path, env, gtypes)` | `Info` do caminho e, se falhar, o erro correspondente (definida abaixo) |
| `compat(t, s)` | Verdadeiro se `t = s`, ou se `t = real` e `s = int` |
| `CAT` | Catálogo de dispositivos (Tabela 4 do relatório), incluindo os intervalos válidos |
| `val(E, env)` | Valor numérico de `E` se for conhecido antes da execução, senão `⊥` (definida abaixo) |

`resolve([x₁, ..., xₙ], env, gtypes)` funciona assim:

1. `s = lookup(env, x₁)`. Se não existir, o erro é `undeclared`.
2. Enquanto `s` for `zone(f)` e houver mais nomes, `s = f[xᵢ₊₁]`. Só se procura no próprio `Frame` da zona. Se não existir, o erro é `undeclared`.
3. Se não restarem nomes, o resultado é a categoria e o tipo de `s`. Para `group(id)`, o tipo é `gtypes[id]`.
4. Se restar exatamente um nome `m` e `s` for `device(t)`, o resultado vem de `CAT[t]`: `(property, tipo, acesso)`, `(command, ...)` ou `(event, ...)`. Caso contrário, o erro é `noSuchMember`.

`val(E, env)` funciona assim:

- Um literal `INT` ou `REAL` vale o seu valor. `-`, `+` e `*` aplicam-se aos valores dos operandos.
- Uma referência a uma constante vale `val` do seu inicializador, no ambiente onde a constante foi declarada.
- `/` e `%` valem `⊥` se o divisor for 0. Com inteiros negativos também valem `⊥`, porque a divisão inteira de negativos não está definida.
- Tudo o resto vale `⊥`: variáveis, propriedades, `now`, e constantes que dependem de si próprias.

`val` é uma função e não um atributo, porque precisa do `env` de outra parte da árvore, o da declaração da constante. Isso não altera a ordem da secção 4: só é chamada na fase 4, quando todos esses ambientes já são conhecidos.

## 2. Atributos

| Atributo | Tipo | Símbolos | Significado |
|---|---|---|---|
| `decls` | sintetizado | `decl_list`, `decl` | `Frame` com as declarações da lista |
| `env` | herdado | zonas, regras e expressões | Nomes visíveis |
| `envIn` | herdado | `stmt`, `stmt_list` | Nomes visíveis antes da instrução |
| `envOut` | sintetizado | `stmt` | Nomes visíveis depois da instrução |
| `elem` | sintetizado | `group_decl` | Tipo comum dos elementos do grupo |
| `gtypes` | herdado | todos, exceto dentro de `group_decl` | Mapa do `id` de cada grupo para `elem` |
| `path` | sintetizado | `ref`, `ref_ids` | Lista de nomes da referência |
| `info` | sintetizado | `ref` | `resolve(ref.path, ref.env, ref.gtypes)` |
| `type` | sintetizado | expressões | Tipo da expressão |
| `const` | sintetizado | expressões | Verdadeiro se a expressão for constante |
| `zoneLevel` | herdado | `var_decl` | Verdadeiro ao nível da zona, falso num bloco |
| `calls` | sintetizado | instruções, `scene_decl` | Cenas ativadas |
| `errors` | sintetizado | todos | Erros da subárvore |

**Convenções, para não repetir equações:**

- `env`, `gtypes` e `zoneLevel` copiam-se do pai para os filhos, salvo indicação em contrário.
- `errors` e `calls` são a união dos valores dos filhos. As equações abaixo só indicam o que se **acrescenta**, com `+=`.
- `A += código se C` acrescenta o erro `código` quando a condição `C` é verdadeira.
- Uma condição sobre um tipo `⊥` é falsa, para um erro não provocar outros em cascata.

## 3. Equações

### Programa e declarações

```
program → "home" STRING "{" decl_list "}"
    decl_list.env    = [ decl_list.decls ]
    decl_list.gtypes = união de todos os group_decl.elem da árvore
    program.errors  += cyclicActivation se o grafo das cenas tiver um ciclo

decl_list₀ → decl decl_list₁
    decl_list₀.decls   = decl_list₁.decls ∪ decl.decls
    decl_list₀.errors += duplicate se o nome de decl estiver em decl_list₁.decls

decl_list → ε
    decl_list.decls = ∅

zone_decl → "zone" ID "{" decl_list "}"
    zone_decl.decls = { ID ↦ zone(decl_list.decls) }
    decl_list.env   = zone_decl.env ++ [ decl_list.decls ]

device_decl → "device" ID₁ ":" ID₂ ";"
    device_decl.decls   = { ID₁ ↦ device(ID₂) }
    device_decl.errors += unknownDeviceType se ID₂ ∉ CAT

var_decl → "var" ID ":" type "=" expr ";"              (const_decl é análoga, com const(type))
    var_decl.decls   = { ID ↦ var(type) }
    var_decl.errors += notConstant  se var_decl.zoneLevel e não expr.const
    var_decl.errors += typeMismatch se não compat(type, expr.type)

decl → var_decl     var_decl.zoneLevel = verdadeiro
stmt → var_decl     var_decl.zoneLevel = falso

group_decl → "group" ID "=" "[" ref ref_list "]" ";"
    group_decl.decls   = { ID ↦ group(id do nó) }
    group_decl.elem    = tipo do primeiro elemento que seja um dispositivo
    group_decl.errors += typeMismatch       se algum elemento não for um dispositivo
    group_decl.errors += heterogeneousGroup se um elemento tiver tipo diferente de elem
```

### Regras e cenas

```
scene_decl → "scene" ID block
    scene_decl.decls = { ID ↦ scene(id do nó) }
    block.env        = scene_decl.env
    aresta do grafo das cenas: de ID para cada cena em block.calls

rule_decl → "rule" ID opt_priority "on" event opt_guard block
    rule_decl.decls = { ID ↦ rule }

guard → "when" expr
    guard.errors += condNotBool se expr.type ≠ bool

event → "change" ref     event.errors += notAProperty se ref.info não for uma propriedade
event → "signal" ref     event.errors += notAnEvent   se ref.info não for um evento
event → "at" TIME        event.errors += invalidTime  se HH ≥ 24 ou MM ≥ 60
event → "every" duration event.errors += zeroPeriod   se o valor de duration for 0
```

### Blocos e instruções

O ambiente atravessa as instruções da esquerda para a direita. É isto que faz com que uma variável local só exista depois de declarada.

```
block → "{" stmt_list "}"
    stmt_list.envIn = block.env ++ [ ∅ ]

stmt_list₀ → stmt stmt_list₁
    stmt.envIn       = stmt_list₀.envIn
    stmt_list₁.envIn = stmt.envOut

stmt → var_decl
    var_decl.env = stmt.envIn
    stmt.envOut  = stmt.envIn com var_decl.decls acrescentado ao Frame mais interno
    stmt.errors += duplicate se o nome já estiver no Frame mais interno

stmt → ref "=" expr ";"
    stmt.envOut  = stmt.envIn
    stmt.errors += assignToConst se ref.info for uma constante
    stmt.errors += readOnly      se ref.info for uma propriedade só de leitura
    stmt.errors += notAssignable se ref.info não for variável, constante nem propriedade
    stmt.errors += typeMismatch  se não houve notAssignable e não compat(ref.type, expr.type)
    stmt.errors += outOfRange    se ref for uma propriedade com intervalo em CAT e
                                 val(expr, stmt.envIn) estiver fora dele

stmt → ref "(" opt_args ")" ";"
    stmt.envOut  = stmt.envIn
    stmt.errors += noSuchMember se ref.info não for um comando
    stmt.errors += typeMismatch se os argumentos não coincidirem em número ou tipo com CAT
    stmt.errors += outOfRange   se o comando tiver intervalo em CAT e val(arg, stmt.envIn) estiver fora dele

stmt → "activate" ref ";"
    stmt.envOut  = stmt.envIn
    stmt.calls   = { cena designada por ref }
    stmt.errors += notAScene se ref.info não for uma cena

if_stmt → "if" expr block opt_else
    if_stmt.errors += condNotBool se expr.type ≠ bool

repeat_stmt → "repeat" expr "times" block
    repeat_stmt.errors += typeMismatch se expr.type ≠ int

for_stmt → "for" ID "in" ref block
    block.env = for_stmt.envIn ++ [ { ID ↦ device(ref.type) } ]
    for_stmt.errors += typeMismatch se ref.info não for um grupo
```

Em todas as instruções sem declaração, `stmt.envOut = stmt.envIn`, e as instruções compostas passam `envIn` aos seus blocos como `env`. Assim, o que é declarado dentro de um bloco não é visível fora dele.

### Referências e expressões

```
ref → ID ref_ids          ref.path = [ID] ++ ref_ids.path
ref_ids₀ → "." ID ref_ids₁    ref_ids₀.path = [ID] ++ ref_ids₁.path
ref_ids → ε               ref_ids.path = []
```

Em todas as produções binárias, `E₀.const = E₁.const ∧ E₂.const`.

| Produção | `type` | `const` | Erro acrescentado |
|---|---|---|---|
| `INT`, `REAL`, `STRING`, `true`, `false` | o do literal | verdadeiro | |
| `TIME` | `time` | verdadeiro | `invalidTime` se a hora for impossível |
| `now` | `time` | falso | |
| `ref` | tipo de `ref.info` | `ref.info` é constante ou `⊥` | os de `resolve` |
| `- E` | `E.type`, se numérico | `E.const` | `typeMismatch` se não for numérico |
| `not E` | `bool` | `E.const` | `typeMismatch` se `E.type ≠ bool` |
| `E₁ and E₂`, `E₁ or E₂` | `bool` | | `typeMismatch` se algum não for `bool` |
| `E₁ == E₂`, `E₁ != E₂` | `bool` | | `typeMismatch` se não forem valores compatíveis num dos sentidos |
| `E₁ < E₂`, `<=`, `>`, `>=` | `bool` | | `typeMismatch` se não forem ambos numéricos ou ambos `time` |
| `E₁ + E₂`, `-`, `*` | `real` se algum for `real`, senão `int` | | `typeMismatch` se algum não for numérico |
| `E₁ + E₂`, ambos `string` | `string` | | |
| `E₁ / E₂` | `int` se ambos forem `int`, senão `real` | | `typeMismatch` se algum não for numérico; senão, `divisionByZero` se `val(E₂, env) = 0` |
| `E₁ % E₂` | `int` | | `typeMismatch` se algum não for `int`; senão, `divisionByZero` se `val(E₂, env) = 0` |
| `( E )` | `E.type` | `E.const` | |

## 4. Dependências e ordem de avaliação

Os atributos podem calcular-se em quatro fases, cada uma dependendo apenas das anteriores:

```
1. decls, path        só dependem da subárvore
        ↓
2. env (nas zonas)    decl_list.env = zone_decl.env ++ [ decl_list.decls ]
        ↓
3. elem → gtypes      o tipo de cada grupo só precisa de env
        ↓
4. envIn, envOut, info, type, const, errors, calls
```

Três dependências mostram porque é que a gramática não é circular:

- **Ordem livre nas zonas.** `decl_list.env` depende de `decl_list.decls`, ou seja, um atributo herdado depende de um sintetizado do mesmo nó. Não há ciclo porque `decls` não depende de `env`. Por isso uma regra pode usar um dispositivo declarado mais abaixo.
- **Ordem sequencial nos blocos.** `stmt_list₁.envIn` depende de `stmt.envOut`, da esquerda para a direita. Esta parte da gramática é L-atribuída, enquanto a das zonas não é.
- **Tipo dos grupos.** O tipo de um grupo depende de `env`, que contém o próprio grupo. Para não criar um ciclo, `decls` guarda apenas `group(id)` e o tipo fica em `gtypes`, calculado depois. Isto funciona porque os elementos de um grupo têm de ser dispositivos, cujo tipo já está em `decls`.

## 5. Exemplo de avaliação

```
home "t" {
  scene S {
    var n : int = 40;
    lamp.brightness = n + 0.5;
  }
  device lamp : dimmer;
}
```

`lamp` é usado antes de ser declarado, o que é válido. O erro está no tipo da atribuição.

| Passo | Atributo | Valor |
|---|---|---|
| 1 | `decl_list.decls` | `{ S ↦ scene, lamp ↦ device(dimmer) }` |
| 2 | `decl_list.env` | `[ { S, lamp } ]` |
| 3 | `gtypes` | `∅`, porque não há grupos |
| 4 | `stmt_list.envIn` (início do bloco) | `[ { S, lamp }, ∅ ]` |
| 5 | `expr.type` em `40` | `int`, e `compat(int, int)` é verdadeiro |
| 6 | `stmt.envOut` da declaração | `[ { S, lamp }, { n ↦ var(int) } ]` |
| 7 | `ref.path` | `[lamp, brightness]` |
| 8 | `ref.info` | `(property, int, rw)`, de `CAT[dimmer]` |
| 9 | `n.type`, `0.5.type` | `int`, `real` |
| 10 | `(n + 0.5).type` | `real` |
| 11 | `stmt.errors` | `compat(int, real)` é falso, logo `{ typeMismatch }` |
| 12 | `program.errors` | `{ typeMismatch }` |

O passo 6 tem de vir antes do passo 9, porque `n` só existe no `envIn` da segunda instrução. O passo 1 tem de vir antes do passo 8, porque `lamp` é declarado depois da cena.

O analisador dá o mesmo resultado:

```
linha 4, coluna 5: [typeMismatch] Tipo incompatível na atribuição.
```

## 6. Relação com a implementação

[semantic.py](../domo/semantic.py) é um percurso da árvore que calcula os mesmos valores, pela ordem da secção 4:

| Fase | Atributos | Implementação |
|---|---|---|
| 1 e 2 | `decls`, `env` nas zonas | `pass1_collect` |
| 3 | `elem`, `gtypes` | `check_groups` |
| 4 | Restantes | `pass2_check`, `eval_expr_type`, `resolve_ref_path` |
| Raiz | Grafo das cenas | `check_cycles` |

**Fora deste subconjunto:** a deteção de constantes circulares (`cyclicInit`), que usa um grafo como o das cenas, e a posição dos erros no texto.

**Verificação.** As equações foram avaliadas por um programa à parte, que as segue diretamente, e os resultados foram comparados com os de `semantic.py` em 108 programas (os testes, os exemplos e casos adicionais). Os códigos de erro coincidiram em todos, excluindo `cyclicInit`. Esta comparação aumenta a confiança na especificação, mas não é uma prova de equivalência.
