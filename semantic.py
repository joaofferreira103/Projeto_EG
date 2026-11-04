#!/usr/bin/env python3
"""
Módulo de Análise Semântica para a linguagem Domo.
"""

from typing import Dict, List, Optional, Set, Tuple
from lark import Tree, Token

DEVICE_CATALOG = {
    "light": {
        "props": {"power": ("bool", "ro")},
        "commands": {"turn_on": [], "turn_off": [], "toggle": []},
        "events": set(),
    },
    "dimmer": {
        "props": {"power": ("bool", "ro"), "brightness": ("int", "rw")},
        "commands": {"turn_on": [], "turn_off": [], "toggle": [], "fade_to": ["int"]},
        "events": set(),
        "ranges": {"brightness": (0, 100), "fade_to": (0, 100)},
    },
    "thermostat": {
        "props": {"target_temp": ("real", "rw"), "current_temp": ("real", "ro")},
        "commands": {},
        "events": set(),
    },
    "motion_sensor": {
        "props": {"active": ("bool", "ro")},
        "commands": {},
        "events": {"motion_detected", "motion_cleared"},
    },
    "temp_sensor": {
        "props": {"value": ("real", "ro")},
        "commands": {},
        "events": set(),
    },
    "door_lock": {
        "props": {"locked": ("bool", "ro")},
        "commands": {"lock": [], "unlock": []},
        "events": {"opened"},
    },
    "blind": {
        "props": {"position": ("int", "rw")},
        "commands": {},
        "events": set(),
        "ranges": {"position": (0, 100)},
    },
    "plug": {
        "props": {"power": ("bool", "ro"), "consumption": ("real", "ro")},
        "commands": {"turn_on": [], "turn_off": []},
        "events": set(),
    },
}

VALUE_TYPES = {"int", "real", "bool", "string", "time"}

class Symbol:
    def __init__(self, name: str, kind: str, type_name: str, rw: str = "rw", meta=None, init=None):
        self.name = name
        self.kind = kind
        self.type_name = type_name
        self.rw = rw
        self.meta = meta
        self.init = init

class Scope:
    def __init__(self, name: str, parent: Optional["Scope"] = None, is_block: bool = False):
        self.name = name
        self.parent = parent
        self.is_block = is_block
        self.symbols: Dict[str, Symbol] = {}
        self.children_zones: Dict[str, "Scope"] = {}

    def define(self, name: str, symbol: Symbol) -> bool:
        if name in self.symbols:
            return False
        self.symbols[name] = symbol
        return True

    def resolve_local(self, name: str) -> Optional[Symbol]:
        return self.symbols.get(name)

    def resolve(self, name: str) -> Optional[Symbol]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.resolve(name)
        return None

class SemanticError(Exception):
    def __init__(self, code: str, msg: str, line: int = 0, col: int = 0):
        super().__init__(f"linha {line}, coluna {col}: [{code}] {msg}")
        self.code = code
        self.msg = msg
        self.line = line
        self.col = col

class SemanticAnalyzer:
    def __init__(self):
        self.errors: List[SemanticError] = []
        self.global_scope: Optional[Scope] = None
        self.scene_calls: Dict[Symbol, Set[Symbol]] = {}
        self.const_deps: Dict[Symbol, Set[Symbol]] = {}
        self.groups: List[Tuple[Tree, Scope, Symbol]] = []

    def add_error(self, code: str, msg: str, token_or_tree):
        where = getattr(token_or_tree, "meta", token_or_tree)
        line = getattr(where, "line", 0)
        col = getattr(where, "column", 0)
        self.errors.append(SemanticError(code, msg, line, col))

    def is_type_compatible(self, target_type: str, expr_type: str) -> bool:
        if target_type == expr_type:
            return True
        if target_type == "real" and expr_type == "int":
            return True
        return False

    def get_declared_type_name(self, type_node: Tree) -> str:
        return type_node.data.replace("t_", "")

    def pass1_collect(self, node: Tree, current_scope: Scope):
        if not isinstance(node, Tree):
            return

        if node.data == "program":
            self.global_scope = Scope("home")
            for child in node.children:
                if isinstance(child, Tree):
                    self.pass1_collect(child, self.global_scope)
            return

        if node.data == "zone_decl":
            name_token = node.children[0]
            zone_name = str(name_token)
            if not current_scope.define(zone_name, Symbol(zone_name, "zone", "zone", meta=name_token)):
                self.add_error("duplicate", f"Identificador duplicado no mesmo âmbito: '{zone_name}'", name_token)

            zone_scope = Scope(zone_name, parent=current_scope)
            current_scope.children_zones[zone_name] = zone_scope
            for child in node.children[1:]:
                if isinstance(child, Tree):
                    self.pass1_collect(child, zone_scope)
            return

        if node.data == "device_decl":
            name_token = node.children[0]
            dev_type_token = node.children[1]
            dev_name = str(name_token)
            dev_type = str(dev_type_token)

            if dev_type not in DEVICE_CATALOG:
                self.add_error("unknownDeviceType", f"O tipo de dispositivo '{dev_type}' não existe no catálogo.", dev_type_token)

            if not current_scope.define(dev_name, Symbol(dev_name, "device", dev_type, meta=name_token)):
                self.add_error("duplicate", f"Identificador duplicado no mesmo âmbito: '{dev_name}'", name_token)
            return

        if node.data in ("var_decl", "const_decl"):
            is_const = (node.data == "const_decl")
            name_token = node.children[0]
            var_name = str(name_token)
            type_name = self.get_declared_type_name(node.children[1])
            rw = "ro" if is_const else "rw"

            init = (node.children[2], current_scope) if is_const else None
            if not current_scope.define(var_name, Symbol(var_name, "const" if is_const else "var", type_name, rw=rw, meta=name_token, init=init)):
                self.add_error("duplicate", f"Identificador duplicado no mesmo âmbito: '{var_name}'", name_token)
            return

        if node.data == "group_decl":
            name_token = node.children[0]
            grp_name = str(name_token)
            grp_sym = Symbol(grp_name, "group", "group", meta=name_token)
            if not current_scope.define(grp_name, grp_sym):
                self.add_error("duplicate", f"Identificador duplicado no mesmo âmbito: '{grp_name}'", name_token)
            self.groups.append((node, current_scope, grp_sym))
            return

        if node.data == "scene_decl":
            name_token = node.children[0]
            scene_name = str(name_token)
            if not current_scope.define(scene_name, Symbol(scene_name, "scene", "scene", meta=name_token)):
                self.add_error("duplicate", f"Identificador duplicado no mesmo âmbito: '{scene_name}'", name_token)
            return

        if node.data == "rule_decl":
            name_token = node.children[0]
            rule_name = str(name_token)
            if not current_scope.define(rule_name, Symbol(rule_name, "rule", "rule", meta=name_token)):
                self.add_error("duplicate", f"Identificador duplicado no mesmo âmbito: '{rule_name}'", name_token)
            return

        for child in node.children:
            if isinstance(child, Tree):
                self.pass1_collect(child, current_scope)

    def extract_ref_tokens(self, ref_node: Tree) -> List[Token]:
        tokens: List[Token] = []

        def collect(node):
            if isinstance(node, Token):
                tokens.append(node)
            elif isinstance(node, Tree):
                for child in node.children:
                    collect(child)

        collect(ref_node)
        return tokens

    def find_zone_scope(self, zone_name: str, start_scope: Scope) -> Optional[Scope]:
        s = start_scope
        while s:
            if zone_name in s.children_zones:
                return s.children_zones[zone_name]
            s = s.parent
        return None

    def lookup_symbol(self, tokens: List[Token], scope: Scope) -> Optional[Symbol]:
        """Símbolo designado por um caminho de zonas (sem reportar erros)."""
        sym = scope.resolve(str(tokens[0]))
        curr_scope, i = scope, 1
        while sym and sym.kind == "zone" and i < len(tokens):
            curr_scope = self.find_zone_scope(sym.name, curr_scope)
            sym = curr_scope.resolve_local(str(tokens[i])) if curr_scope else None
            i += 1
        return sym if i == len(tokens) else None

    def resolve_ref_path(self, ref_node: Tree, scope: Scope) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        tokens = self.extract_ref_tokens(ref_node)
        first_token = tokens[0]
        first_id = str(first_token)

        sym = scope.resolve(first_id)
        if not sym:
            self.add_error("undeclared", f"Símbolo '{first_id}' não foi declarado.", first_token)
            return None, None, None

        if len(tokens) == 1:
            return sym.type_name, sym.rw, sym.kind

        curr_scope = scope
        curr_sym = sym
        i = 1

        while i < len(tokens) and curr_sym.kind == "zone":
            zone_scope = self.find_zone_scope(curr_sym.name, curr_scope)
            if not zone_scope:
                break
            nxt_token = tokens[i]
            nxt_sym = zone_scope.resolve_local(str(nxt_token))
            if not nxt_sym:
                self.add_error("undeclared", f"Símbolo '{nxt_token}' não existe na zona '{curr_sym.name}'.", nxt_token)
                return None, None, None
            curr_sym = nxt_sym
            curr_scope = zone_scope
            i += 1

        if i == len(tokens):
            return curr_sym.type_name, curr_sym.rw, curr_sym.kind

        if curr_sym.kind != "device":
            self.add_error("noSuchMember", f"'{curr_sym.name}' não permite acesso a membros.", tokens[i])
            return None, None, None

        dev_type = curr_sym.type_name
        dev_info = DEVICE_CATALOG.get(dev_type)
        if not dev_info:
            return None, None, None

        member_token = tokens[i]
        member_name = str(member_token)

        if member_name in dev_info["props"]:
            prop_type, prop_rw = dev_info["props"][member_name]
            if i + 1 < len(tokens):
                self.add_error("noSuchMember", f"Propriedade '{member_name}' não permite acesso a membros.", tokens[i + 1])
                return None, None, None
            return prop_type, prop_rw, "property"

        if member_name in dev_info["commands"]:
            if i + 1 < len(tokens):
                self.add_error("noSuchMember", f"Comando '{member_name}' não permite acesso a membros.", tokens[i + 1])
                return None, None, None
            return "command", "ro", "command"

        if member_name in dev_info["events"]:
            if i + 1 < len(tokens):
                self.add_error("noSuchMember", f"Evento '{member_name}' não permite acesso a membros.", tokens[i + 1])
                return None, None, None
            return "event", "ro", "event"

        self.add_error("noSuchMember", f"Dispositivo '{curr_sym.name}' do tipo '{dev_type}' não tem o membro '{member_name}'.", member_token)
        return None, None, None

    def eval_expr_type(self, node: Tree, scope: Scope) -> Optional[str]:
        data = node.data
        if data == "int_lit": return "int"
        if data == "real_lit": return "real"
        if data == "str_lit": return "string"
        if data == "time_lit":
            time_token = node.children[0]
            hh, mm = map(int, str(time_token).split(":"))
            if hh >= 24 or mm >= 60:
                self.add_error("invalidTime", f"Hora inválida '{time_token}'.", time_token)
            return "time"
        if data in ("true_lit", "false_lit"): return "bool"
        if data == "now": return "time"

        if data == "ref":
            t, _, _ = self.resolve_ref_path(node, scope)
            return t

        if data == "neg":
            t = self.eval_expr_type(node.children[0], scope)
            if t is None:
                return None
            if t not in ("int", "real"):
                self.add_error("typeMismatch", "Operador '-' unário requer int ou real.", node)
                return None
            return t

        if data == "not_":
            t = self.eval_expr_type(node.children[0], scope)
            if t and t != "bool":
                self.add_error("typeMismatch", "Operador 'not' requer booleano.", node)
            return "bool"

        if data in ("and_", "or_"):
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 and t2 and (t1 != "bool" or t2 != "bool"):
                self.add_error("typeMismatch", "Operadores 'and'/'or' requerem booleanos.", node)
            return "bool"

        if data in ("eq", "ne"):
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            comparable = t1 in VALUE_TYPES and t2 in VALUE_TYPES and (
                self.is_type_compatible(t1, t2) or self.is_type_compatible(t2, t1))
            if t1 and t2 and not comparable:
                self.add_error("typeMismatch", "Comparação incompatível.", node)
            return "bool"

        if data in ("lt", "le", "gt", "ge"):
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            valid = (
                (t1 in ("int", "real") and t2 in ("int", "real")) or
                (t1 == "time" and t2 == "time")
            )
            if t1 and t2 and not valid:
                self.add_error("typeMismatch", "Comparação relacional inválida.", node)
            return "bool"

        if data in ("add", "sub", "mul"):
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 is None or t2 is None:
                return None
            if t1 == "string" and t2 == "string" and data == "add":
                return "string"
            if t1 in ("int", "real") and t2 in ("int", "real"):
                return "real" if "real" in (t1, t2) else "int"
            self.add_error("typeMismatch", "Operação aritmética inválida.", node)
            return None

        if data == "div":
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 is None or t2 is None:
                return None
            if t1 in ("int", "real") and t2 in ("int", "real"):
                self.check_zero_divisor(node, scope)
                return "int" if t1 == "int" and t2 == "int" else "real"
            self.add_error("typeMismatch", "Divisão requer valores numéricos.", node)
            return None

        if data == "mod":
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 and t2 and (t1 != "int" or t2 != "int"):
                self.add_error("typeMismatch", "Operador '%' requer inteiros.", node)
            elif t1 and t2:
                self.check_zero_divisor(node, scope)
            return "int"

        return None

    def const_value(self, node: Tree, scope: Scope, seen: frozenset = frozenset()):
        """Valor numérico de uma expressão, se for conhecido antes da execução; senão None.
        Os ciclos entre constantes dão None: já são reportados como cyclicInit."""
        data = node.data
        if data == "int_lit":
            return int(node.children[0])
        if data == "real_lit":
            return float(node.children[0])
        if data == "ref":
            sym = self.lookup_symbol(self.extract_ref_tokens(node), scope)
            if sym is None or sym.init is None or sym in seen:
                return None
            expr, expr_scope = sym.init
            return self.const_value(expr, expr_scope, seen | {sym})
        if data == "neg":
            v = self.const_value(node.children[0], scope, seen)
            return None if v is None else -v
        if data not in ("add", "sub", "mul", "div", "mod"):
            return None

        a = self.const_value(node.children[0], scope, seen)
        b = self.const_value(node.children[1], scope, seen)
        if a is None or b is None:
            return None
        try:
            if data == "add": return a + b
            if data == "sub": return a - b
            if data == "mul": return a * b
            if b == 0: return None
            both_int = isinstance(a, int) and isinstance(b, int)
            if data == "mod" or both_int:
                if not both_int or a < 0 or b < 0: return None
                return a % b if data == "mod" else a // b
            return a / b
        except OverflowError:
            return None

    def check_zero_divisor(self, node: Tree, scope: Scope):
        if self.const_value(node.children[1], scope) == 0:
            self.add_error("divisionByZero", "Divisão por zero.", node)

    def check_range(self, device_type: str, member: str, expr_node: Tree, scope: Scope):
        limits = DEVICE_CATALOG.get(device_type, {}).get("ranges", {}).get(member)
        value = self.const_value(expr_node, scope)
        if limits and value is not None and not limits[0] <= value <= limits[1]:
            self.add_error("outOfRange", f"'{member}' aceita valores de {limits[0]} a {limits[1]}, mas recebeu {value}.", expr_node)

    def is_constant_expr(self, node: Tree, scope: Scope) -> bool:
        if not isinstance(node, Tree):
            return False

        if node.data in ("int_lit", "real_lit", "str_lit", "time_lit",
                         "true_lit", "false_lit"):
            return True
        if node.data == "now":
            return False
        if node.data == "ref":
            n_errors = len(self.errors)
            _, _, kind = self.resolve_ref_path(node, scope)
            del self.errors[n_errors:]
            return kind in ("const", None)

        if node.data in ("neg", "not_"):
            return self.is_constant_expr(node.children[0], scope)
        if node.data in ("and_", "or_", "eq", "ne", "lt", "le", "gt", "ge",
                         "add", "sub", "mul", "div", "mod"):
            return all(self.is_constant_expr(child, scope)
                       for child in node.children
                       if isinstance(child, Tree))

        return False

    def collect_args(self, node: Tree) -> List[Tree]:
        items = []
        if not isinstance(node, Tree):
            return items
        if node.data == "args":
            for child in node.children:
                if isinstance(child, Tree):
                    items.append(child)
        else:
            for child in node.children:
                if isinstance(child, Tree):
                    items.extend(self.collect_args(child))
        return items

    def check_groups(self):
        """Calcula o tipo comum de cada grupo. Corre antes da verificação dos corpos
        porque a ordem das declarações na zona é livre e o `for` precisa deste tipo."""
        for node, scope, sym in self.groups:
            group_dev_type = None
            for r in (c for c in node.children if isinstance(c, Tree) and c.data == "ref"):
                t, _, kind = self.resolve_ref_path(r, scope)
                if kind and kind != "device":
                    self.add_error("typeMismatch", "Elementos de grupo têm de ser dispositivos.", r)
                elif kind == "device":
                    if group_dev_type is None:
                        group_dev_type = t
                    elif group_dev_type != t:
                        self.add_error("heterogeneousGroup", "Grupo heterogéneo.", r)
            if group_dev_type:
                sym.type_name = group_dev_type

    def pass2_check(self, node: Tree, current_scope: Scope, current_scene: Optional[str] = None):
        if not isinstance(node, Tree):
            return

        if node.data == "zone_decl":
            zone_name = str(node.children[0])
            zone_scope = current_scope.children_zones.get(zone_name, current_scope)
            for child in node.children[1:]:
                if isinstance(child, Tree):
                    self.pass2_check(child, zone_scope, current_scene)
            return

        if node.data == "scene_decl":
            scene_name = str(node.children[0])
            for child in node.children[1:]:
                if isinstance(child, Tree):
                    self.pass2_check(child, current_scope, current_scene=current_scope.resolve_local(scene_name))
            return

        if node.data == "rule_decl":
            for child in node.children:
                if isinstance(child, Tree):
                    self.pass2_check(child, current_scope, current_scene)
            return

        if node.data == "block":
            block_scope = Scope("block", parent=current_scope, is_block=True)
            for child in node.children:
                if isinstance(child, Tree):
                    self.pass2_check(child, block_scope, current_scene)
            return

        if node.data in ("var_decl", "const_decl"):
            is_const = (node.data == "const_decl")
            name_token = node.children[0]
            var_name = str(name_token)
            type_name = self.get_declared_type_name(node.children[1])
            expr_node = node.children[2]

            if not current_scope.is_block:
                if not self.is_constant_expr(expr_node, current_scope):
                    self.add_error("notConstant", f"Inicializador de '{var_name}' tem de ser uma expressão constante.", expr_node)
                elif is_const:
                    refs = (self.extract_ref_tokens(r) for r in expr_node.find_data("ref"))
                    deps = {self.lookup_symbol(t, current_scope) for t in refs}
                    self.const_deps.setdefault(current_scope.resolve_local(var_name), set()).update(deps - {None})

            expr_type = self.eval_expr_type(expr_node, current_scope)
            if expr_type and not self.is_type_compatible(type_name, expr_type):
                self.add_error("typeMismatch", f"Tipo incompatível na declaração de '{var_name}'.", expr_node)

            if current_scope.is_block:
                rw = "ro" if is_const else "rw"
                init = (expr_node, current_scope) if is_const else None
                if not current_scope.define(var_name, Symbol(var_name, "const" if is_const else "var", type_name, rw=rw, meta=name_token, init=init)):
                    self.add_error("duplicate", f"Identificador local duplicado: '{var_name}'", name_token)
            return

        if node.data == "assign":
            ref_node = node.children[0]
            expr_node = node.children[1]
            target_type, target_rw, kind = self.resolve_ref_path(ref_node, current_scope)
            expr_type = self.eval_expr_type(expr_node, current_scope)

            if kind == "const":
                self.add_error("assignToConst", "Não é permitido alterar constantes.", ref_node)
            elif kind == "property" and target_rw == "ro":
                self.add_error("readOnly", "Propriedade só de leitura.", ref_node)
            elif kind and kind not in ("var", "property"):
                self.add_error("notAssignable", "Só se pode atribuir a variáveis e propriedades.", ref_node)
                return

            if target_type and expr_type and not self.is_type_compatible(target_type, expr_type):
                self.add_error("typeMismatch", "Tipo incompatível na atribuição.", node)
            elif kind == "property":
                tokens = self.extract_ref_tokens(ref_node)
                device = self.lookup_symbol(tokens[:-1], current_scope)
                if device:
                    self.check_range(device.type_name, str(tokens[-1]), expr_node, current_scope)
            return

        if node.data == "command":
            ref_node = node.children[0]
            tokens = self.extract_ref_tokens(ref_node)
            _, _, kind = self.resolve_ref_path(ref_node, current_scope)
            cmd_token = tokens[-1]
            cmd_name = str(cmd_token)

            if kind and kind != "command":
                self.add_error("noSuchMember", f"'{cmd_name}' não é um comando.", cmd_token)
            elif kind == "command":
                dev_sym = self.lookup_symbol(tokens[:-1], current_scope)
                if dev_sym and dev_sym.kind == "device":
                    dev_info = DEVICE_CATALOG.get(dev_sym.type_name, {})
                    expected_args = dev_info.get("commands", {}).get(cmd_name, [])
                    args = []
                    for c in node.children[1:]:
                        if isinstance(c, Tree):
                            args.extend(self.collect_args(c))

                    if len(args) != len(expected_args):
                        self.add_error("typeMismatch", f"Comando '{cmd_name}' espera {len(expected_args)} argumentos.", node)
                    else:
                        for arg_expr, exp_t in zip(args, expected_args):
                            act_t = self.eval_expr_type(arg_expr, current_scope)
                            if act_t and not self.is_type_compatible(exp_t, act_t):
                                self.add_error("typeMismatch", f"Argumento inválido em '{cmd_name}': esperava {exp_t}, obteve {act_t}.", arg_expr)
                            elif act_t:
                                self.check_range(dev_sym.type_name, cmd_name, arg_expr, current_scope)
            return

        if node.data == "activate":
            ref_node = node.children[0]
            tokens = self.extract_ref_tokens(ref_node)
            _, _, kind = self.resolve_ref_path(ref_node, current_scope)
            if kind and kind != "scene":
                self.add_error("notAScene", f"'{tokens[-1]}' não é uma cena.", ref_node)
            elif kind == "scene" and current_scene:
                self.scene_calls.setdefault(current_scene, set()).add(self.lookup_symbol(tokens, current_scope))
            return

        if node.data == "if_stmt":
            cond_type = self.eval_expr_type(node.children[0], current_scope)
            if cond_type and cond_type != "bool":
                self.add_error("condNotBool", "Condição do if tem de ser bool.", node.children[0])

        if node.data == "repeat_stmt":
            c_type = self.eval_expr_type(node.children[0], current_scope)
            if c_type and c_type != "int":
                self.add_error("typeMismatch", "Repeat requer int.", node.children[0])

        if node.data == "for_stmt":
            var_token = node.children[0]
            ref_node = node.children[1]
            t, _, kind = self.resolve_ref_path(ref_node, current_scope)
            if kind and kind != "group":
                self.add_error("typeMismatch", "For requer grupo.", node.children[1])
            if len(node.children) > 2 and isinstance(node.children[2], Tree):
                for_block = node.children[2]
                for_scope = Scope("block", parent=current_scope, is_block=True)
                for_scope.define(str(var_token), Symbol(str(var_token), "device", t if kind == "group" else "device"))
                for child in for_block.children:
                    if isinstance(child, Tree):
                        self.pass2_check(child, for_scope, current_scene)
                return

        if node.data == "guard":
            cond_type = self.eval_expr_type(node.children[0], current_scope)
            if cond_type and cond_type != "bool":
                self.add_error("condNotBool", "Condição do when tem de ser bool.", node.children[0])

        if node.data == "ev_change":
            _, _, kind = self.resolve_ref_path(node.children[0], current_scope)
            if kind and kind != "property":
                self.add_error("notAProperty", "Change requer propriedade.", node.children[0])

        if node.data == "ev_signal":
            _, _, kind = self.resolve_ref_path(node.children[0], current_scope)
            if kind and kind != "event":
                self.add_error("notAnEvent", "Signal requer evento.", node.children[0])

        if node.data == "ev_at":
            time_token = node.children[0]
            hh, mm = map(int, str(time_token).split(":"))
            if hh >= 24 or mm >= 60:
                self.add_error("invalidTime", f"Hora inválida '{time_token}'.", time_token)

        if node.data == "ev_every":
            duration_node = node.children[0]
            count = int(duration_node.children[0])
            if count <= 0:
                self.add_error("zeroPeriod", "Periodo zero.", duration_node)

        for child in node.children:
            if isinstance(child, Tree):
                self.pass2_check(child, current_scope, current_scene)

    def find_cycle(self, graph: Dict[Symbol, Set[Symbol]]) -> Optional[Symbol]:
        """Devolve um símbolo que pertence a um ciclo do grafo, ou None."""
        visited = set()
        stack = set()

        def dfs(sym):
            visited.add(sym)
            stack.add(sym)
            for neighbor in graph.get(sym, set()):
                if neighbor in stack:
                    return neighbor
                if neighbor not in visited:
                    found = dfs(neighbor)
                    if found:
                        return found
            stack.remove(sym)
            return None

        for sym in list(graph):
            if sym not in visited:
                found = dfs(sym)
                if found:
                    return found
        return None

    def check_cycles(self):
        scene = self.find_cycle(self.scene_calls)
        if scene:
            self.add_error("cyclicActivation", f"Ativação cíclica envolvendo a cena '{scene.name}'.", scene.meta)
        const = self.find_cycle(self.const_deps)
        if const:
            self.add_error("cyclicInit", f"Inicialização circular envolvendo a constante '{const.name}'.", const.meta)

    def analyze(self, tree: Tree) -> List[SemanticError]:
        self.errors.clear()
        self.scene_calls.clear()
        self.const_deps.clear()
        self.groups.clear()
        self.pass1_collect(tree, Scope("root"))
        self.check_groups()
        self.pass2_check(tree, self.global_scope)
        self.check_cycles()
        self.errors.sort(key=lambda e: (e.line, e.col))
        return self.errors