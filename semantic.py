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
    },
    "plug": {
        "props": {"power": ("bool", "ro"), "consumption": ("real", "ro")},
        "commands": {"turn_on": [], "turn_off": []},
        "events": set(),
    },
}

class Symbol:
    def __init__(self, name: str, kind: str, type_name: str, is_const: bool = False, rw: str = "rw", meta=None):
        self.name = name
        self.kind = kind          # 'zone', 'device', 'var', 'const', 'group', 'scene', 'rule'
        self.type_name = type_name
        self.is_const = is_const
        self.rw = rw
        self.meta = meta

class Scope:
    def __init__(self, name: str, parent: Optional["Scope"] = None):
        self.name = name
        self.parent = parent
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

    def get_root(self) -> "Scope":
        curr = self
        while curr.parent:
            curr = curr.parent
        return curr

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
        self.scene_calls: Dict[str, Set[str]] = {}

    def add_error(self, code: str, msg: str, token_or_tree):
        line = getattr(token_or_tree, "line", 0)
        col = getattr(token_or_tree, "column", 0)
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

            if not current_scope.define(var_name, Symbol(var_name, "const" if is_const else "var", type_name, is_const=is_const, rw=rw, meta=name_token)):
                self.add_error("duplicate", f"Identificador duplicado no mesmo âmbito: '{var_name}'", name_token)
            return

        if node.data == "group_decl":
            name_token = node.children[0]
            grp_name = str(name_token)
            if not current_scope.define(grp_name, Symbol(grp_name, "group", "group", meta=name_token)):
                self.add_error("duplicate", f"Identificador duplicado no mesmo âmbito: '{grp_name}'", name_token)
            return

        if node.data == "scene_decl":
            name_token = node.children[0]
            scene_name = str(name_token)
            self.scene_calls[scene_name] = set()
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
        # `_ref_ids` is inlined by Lark, so the simplified AST contains all
        # components as direct token children of `ref` rather than a linked
        # recursive tree.
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
        root = start_scope.get_root()
        if zone_name in root.children_zones:
            return root.children_zones[zone_name]
        return None

    def resolve_ref_path(self, ref_node: Tree, scope: Scope) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        tokens = self.extract_ref_tokens(ref_node)
        first_token = tokens[0]
        first_id = str(first_token)

        sym = scope.resolve(first_id)
        if not sym:
            # Tentar na raiz da casa
            sym = scope.get_root().resolve_local(first_id)
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
        if isinstance(node, Token):
            if node.type == "INT": return "int"
            if node.type == "REAL": return "real"
            if node.type == "STRING": return "string"
            if node.type == "TIME":
                hh, mm = map(int, str(node).split(":"))
                if hh >= 24 or mm >= 60:
                    self.add_error("invalidTime", f"Hora inválida '{node}'.", node)
                return "time"
            return None

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
            if t not in ("int", "real"):
                self.add_error("typeMismatch", f"Operador '-' unário requer int ou real.", node)
                return None
            return t

        if data == "not_":
            t = self.eval_expr_type(node.children[0], scope)
            if t != "bool":
                self.add_error("typeMismatch", f"Operador 'not' requer booleano.", node)
            return "bool"

        if data in ("and_", "or_"):
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 != "bool" or t2 != "bool":
                self.add_error("typeMismatch", f"Operadores 'and'/'or' requerem booleanos.", node)
            return "bool"

        if data in ("eq", "ne"):
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 and t2 and not (self.is_type_compatible(t1, t2) or self.is_type_compatible(t2, t1)):
                self.add_error("typeMismatch", f"Comparação incompatível.", node)
            return "bool"

        if data in ("lt", "le", "gt", "ge"):
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            valid = (
                (t1 in ("int", "real") and t2 in ("int", "real")) or
                (t1 == "time" and t2 == "time")
            )
            if not valid:
                self.add_error("typeMismatch", f"Comparação relacional inválida.", node)
            return "bool"

        if data in ("add", "sub", "mul"):
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 == "string" and t2 == "string" and data == "add":
                return "string"
            if t1 in ("int", "real") and t2 in ("int", "real"):
                return "real" if "real" in (t1, t2) else "int"
            self.add_error("typeMismatch", f"Operação aritmética inválida.", node)
            return None

        if data == "div":
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 == "int" and t2 == "int":
                return "int"
            if t1 in ("int", "real") and t2 in ("int", "real"):
                return "real"
            self.add_error("typeMismatch", f"Divisão requer valores numéricos.", node)
            return None

        if data == "mod":
            t1 = self.eval_expr_type(node.children[0], scope)
            t2 = self.eval_expr_type(node.children[1], scope)
            if t1 != "int" or t2 != "int":
                self.add_error("typeMismatch", f"Operador '%' requer inteiros.", node)
            return "int"

        for child in node.children:
            if isinstance(child, Tree):
                res = self.eval_expr_type(child, scope)
                if res: return res
        return None

    def is_constant_expr(self, node: Tree, scope: Scope) -> bool:
        if not isinstance(node, Tree):
            return False

        if node.data in ("int_lit", "real_lit", "str_lit", "time_lit",
                         "true_lit", "false_lit"):
            return True
        if node.data == "now":
            return False
        if node.data == "ref":
            _, _, kind = self.resolve_ref_path(node, scope)
            return kind == "const"

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
                    self.pass2_check(child, current_scope, current_scene=scene_name)
            return

        if node.data == "rule_decl":
            for child in node.children:
                if isinstance(child, Tree):
                    self.pass2_check(child, current_scope, current_scene)
            return

        if node.data == "block":
            block_scope = Scope("block", parent=current_scope)
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

            if current_scope.name != "block" and not self.is_constant_expr(expr_node, current_scope):
                self.add_error("typeMismatch", f"Inicializador de '{var_name}' tem de ser uma expressão constante.", expr_node)

            expr_type = self.eval_expr_type(expr_node, current_scope)
            if expr_type and not self.is_type_compatible(type_name, expr_type):
                self.add_error("typeMismatch", f"Tipo incompatível na declaração de '{var_name}'.", expr_node)

            if current_scope.name == "block":
                rw = "ro" if is_const else "rw"
                if not current_scope.define(var_name, Symbol(var_name, "const" if is_const else "var", type_name, is_const=is_const, rw=rw, meta=name_token)):
                    self.add_error("duplicate", f"Identificador local duplicado: '{var_name}'", name_token)
            return

        if node.data == "group_decl":
            refs = [c for c in node.children if isinstance(c, Tree) and c.data == "ref"]
            group_dev_type = None
            for r in refs:
                t, _, kind = self.resolve_ref_path(r, current_scope)
                if kind and kind != "device":
                    self.add_error("typeMismatch", f"Elementos de grupo têm de ser dispositivos.", r)
                elif kind == "device":
                    if group_dev_type is None:
                        group_dev_type = t
                    elif group_dev_type != t:
                        self.add_error("heterogeneousGroup", f"Grupo heterogéneo.", r)
            return

        if node.data == "assign":
            ref_node = node.children[0]
            expr_node = node.children[1]
            target_type, target_rw, kind = self.resolve_ref_path(ref_node, current_scope)
            expr_type = self.eval_expr_type(expr_node, current_scope)

            if kind == "const" or (kind == "var" and target_rw == "ro"):
                self.add_error("assignToConst", f"Não é permitido alterar constantes.", ref_node)
            elif target_rw == "ro":
                self.add_error("readOnly", f"Propriedade só de leitura.", ref_node)

            if target_type and expr_type and not self.is_type_compatible(target_type, expr_type):
                self.add_error("typeMismatch", f"Tipo incompatível na atribuição.", node)
            return

        if node.data == "command":
            ref_node = node.children[0]
            tokens = self.extract_ref_tokens(ref_node)
            target_type, _, kind = self.resolve_ref_path(ref_node, current_scope)
            cmd_token = tokens[-1]
            cmd_name = str(cmd_token)

            if kind == "command":
                dev_tokens = tokens[:-1]
                if len(dev_tokens) == 1:
                    dev_sym = current_scope.resolve(str(dev_tokens[0]))
                    if not dev_sym:
                        dev_sym = current_scope.get_root().resolve_local(str(dev_tokens[0]))
                else:
                    curr_s = current_scope
                    dev_sym = curr_s.resolve(str(dev_tokens[0]))
                    if not dev_sym:
                        dev_sym = current_scope.get_root().resolve_local(str(dev_tokens[0]))
                    idx = 1
                    while dev_sym and dev_sym.kind == "zone" and idx < len(dev_tokens):
                        z_scope = self.find_zone_scope(dev_sym.name, curr_s)
                        if not z_scope: break
                        dev_sym = z_scope.resolve_local(str(dev_tokens[idx]))
                        curr_s = z_scope
                        idx += 1

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
            return

        if node.data == "activate":
            ref_node = node.children[0]
            tokens = self.extract_ref_tokens(ref_node)
            ref_name = str(tokens[0])
            sym = current_scope.resolve(ref_name)
            if not sym:
                sym = current_scope.get_root().resolve_local(ref_name)
            if sym and sym.kind != "scene":
                self.add_error("notAScene", f"'{ref_name}' não é uma cena.", ref_node)
            elif current_scene and sym and sym.kind == "scene":
                self.scene_calls.setdefault(current_scene, set()).add(ref_name)
            return

        if node.data == "if_stmt":
            cond_type = self.eval_expr_type(node.children[0], current_scope)
            if cond_type and cond_type != "bool":
                self.add_error("condNotBool", f"Condição do if tem de ser bool.", node.children[0])

        if node.data == "repeat_stmt":
            c_type = self.eval_expr_type(node.children[0], current_scope)
            if c_type and c_type != "int":
                self.add_error("typeMismatch", f"Repeat requer int.", node.children[0])

        if node.data == "for_stmt":
            var_token = node.children[0]
            ref_node = node.children[1]
            t, _, kind = self.resolve_ref_path(ref_node, current_scope)
            if kind != "group":
                self.add_error("typeMismatch", f"For requer grupo.", node.children[1])
            if len(node.children) > 2 and isinstance(node.children[2], Tree):
                for_block = node.children[2]
                for_scope = Scope("block", parent=current_scope)
                for_scope.define(str(var_token), Symbol(str(var_token), "device", t if t else "device"))
                for child in for_block.children:
                    if isinstance(child, Tree):
                        self.pass2_check(child, for_scope, current_scene)
                return

        if node.data == "guard":
            cond_type = self.eval_expr_type(node.children[0], current_scope)
            if cond_type and cond_type != "bool":
                self.add_error("condNotBool", f"Condição do when tem de ser bool.", node.children[0])

        if node.data == "ev_change":
            _, _, kind = self.resolve_ref_path(node.children[0], current_scope)
            if kind and kind != "property":
                self.add_error("notAProperty", f"Change requer propriedade.", node.children[0])

        if node.data == "ev_signal":
            _, _, kind = self.resolve_ref_path(node.children[0], current_scope)
            if kind and kind != "event":
                self.add_error("notAnEvent", f"Signal requer evento.", node.children[0])

        if node.data == "ev_at":
            time_token = node.children[0]
            hh, mm = map(int, str(time_token).split(":"))
            if hh >= 24 or mm >= 60:
                self.add_error("invalidTime", f"Hora inválida '{time_token}'.", time_token)

        if node.data == "ev_every":
            duration_node = node.children[0]
            count = int(duration_node.children[0])
            if count <= 0:
                self.add_error("zeroPeriod", f"Periodo zero.", duration_node)

        for child in node.children:
            if isinstance(child, Tree):
                self.pass2_check(child, current_scope, current_scene)

    def check_cyclic_scenes(self):
        visited = set()
        stack = set()

        def dfs(scene):
            visited.add(scene)
            stack.add(scene)
            for neighbor in self.scene_calls.get(scene, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in stack:
                    return True
            stack.remove(scene)
            return False

        for scene in list(self.scene_calls.keys()):
            if scene not in visited:
                if dfs(scene):
                    self.add_error("cyclicActivation", f"Ativação cíclica detetada.", Token("ID", scene, line=1, column=1))
                    break

    def analyze(self, tree: Tree) -> List[SemanticError]:
        self.errors.clear()
        self.scene_calls.clear()
        self.pass1_collect(tree, Scope("root"))
        if not self.errors:
            self.pass2_check(tree, self.global_scope)
            self.check_cyclic_scenes()
        return self.errors