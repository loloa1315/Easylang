import re
from dataclasses import dataclass, field
from typing import List, Optional

from .lexer import strip_comment, is_number, is_valid_name


class EasyLangError(Exception):
    def __init__(self, line: int, message: str, suggestion: Optional[str] = None):
        super().__init__(message)
        self.line = line
        self.message = message
        self.suggestion = suggestion

    def friendly(self) -> str:
        if self.suggestion:
            return f"Line {self.line}: {self.message}\nHint: {self.suggestion}"
        return f"Line {self.line}: {self.message}"


@dataclass
class Operand:
    raw: str
    is_number: bool


@dataclass
class Expression:
    left: Operand
    op: Optional[str] = None
    right: Optional[Operand] = None


@dataclass
class Condition:
    left: Operand
    op: str
    right: Operand


@dataclass
class PrintText:
    text: str
    line: int


@dataclass
class PrintVar:
    expr: Expression
    line: int


@dataclass
class AssignNumber:
    name: str
    expr: Expression
    line: int


@dataclass
class AssignText:
    name: str
    text: str
    line: int


@dataclass
class IfBlock:
    condition: Condition
    body: List
    line: int


@dataclass
class RepeatBlock:
    count_expr: Expression
    body: List
    line: int


@dataclass
class FunctionDef:
    name: str
    param: Optional[str]
    body: List
    line: int


@dataclass
class RunFunction:
    name: str
    arg_text: Optional[str]
    line: int


@dataclass
class InputStatement:
    name: str
    prompt: str
    line: int


@dataclass
class CloseWindow:
    line: int


@dataclass
class WindowBlock:
    settings: dict
    body: List
    draw: List
    line: int


@dataclass
class Program:
    statements: List = field(default_factory=list)


class Parser:
    def parse(self, source: str) -> Program:
        lines = source.splitlines()
        program = Program()
        current_list = program.statements
        stack = []

        def current_window():
            for block_type, node, _prev in reversed(stack):
                if block_type == "window":
                    return node
            return None

        for idx, raw in enumerate(lines, start=1):
            line = strip_comment(raw).rstrip("\n")
            if not line.strip():
                continue

            stripped = line.strip()

            if stripped == "end":
                if not stack:
                    raise EasyLangError(idx, "You have an 'end' without a matching block.",
                                       "Remove the extra 'end' or add a matching 'if', 'repeat', or 'make function'.")
                _block_type, _node, prev_list = stack.pop()
                current_list = prev_list if prev_list is not None else program.statements
                continue

            if stripped == "draw:":
                window = current_window()
                if not window or current_list is not window.body:
                    raise EasyLangError(idx, "Draw can only be used inside 'draw window:'.",
                                       "Example: draw window: ... draw: print: hi end")
                current_list = window.draw
                continue

            window = current_window()
            if window and current_list is window.body:
                if "=" in stripped and not stripped.startswith(("number ", "text ", "input ")):
                    left, right = stripped.split("=", 1)
                    key = left.strip()
                    value = right.strip()
                    if key in ("window_size", "windows_size", "title", "background"):
                        window.settings[key] = value
                        continue

            if stripped.startswith("print:"):
                text = stripped[len("print:"):].strip()
                if not text:
                    raise EasyLangError(idx, "Print needs text after 'print:'.", "Example: print: Hello world")
                current_list.append(PrintText(text=text, line=idx))
                continue

            if stripped.startswith("printvar:"):
                expr_text = stripped[len("printvar:"):].strip()
                if not expr_text:
                    raise EasyLangError(idx, "Printvar needs a variable or math after 'printvar:'.",
                                       "Example: printvar: apple + orange")
                expr = self._parse_expression(expr_text, idx)
                current_list.append(PrintVar(expr=expr, line=idx))
                continue

            if stripped.startswith("number "):
                rest = stripped[len("number "):]  # name = expr
                name, value = self._split_assignment(rest, idx)
                if not is_valid_name(name):
                    raise EasyLangError(idx, f"'{name}' is not a valid variable name.",
                                       "Use letters, numbers, and underscores. Start with a letter.")
                expr = self._parse_expression(value, idx)
                current_list.append(AssignNumber(name=name, expr=expr, line=idx))
                continue

            if stripped.startswith("text "):
                rest = stripped[len("text "):]  # name = text
                name, value = self._split_assignment(rest, idx)
                if not is_valid_name(name):
                    raise EasyLangError(idx, f"'{name}' is not a valid variable name.",
                                       "Use letters, numbers, and underscores. Start with a letter.")
                if not value:
                    raise EasyLangError(idx, "Text needs a value after '='.", "Example: text name = John")
                current_list.append(AssignText(name=name, text=value, line=idx))
                continue

            if stripped.startswith("input "):
                rest = stripped[len("input "):]
                if "=" in rest:
                    name, prompt = self._split_assignment(rest, idx)
                else:
                    name = rest.strip()
                    prompt = ""
                if not is_valid_name(name):
                    raise EasyLangError(idx, f"'{name}' is not a valid variable name.",
                                       "Use letters, numbers, and underscores. Start with a letter.")
                current_list.append(InputStatement(name=name, prompt=prompt, line=idx))
                continue

            if stripped.startswith("if "):
                cond_text = stripped[len("if "):]
                condition = self._parse_condition(cond_text, idx)
                node = IfBlock(condition=condition, body=[], line=idx)
                current_list.append(node)
                stack.append(("if", node, current_list))
                current_list = node.body
                continue

            if stripped.startswith("repeat "):
                rest = stripped[len("repeat "):]
                if not rest.endswith(" times"):
                    raise EasyLangError(idx, "Repeat must end with 'times'.",
                                       "Example: repeat 5 times")
                count_text = rest[:-len(" times")].strip()
                if not count_text:
                    raise EasyLangError(idx, "Repeat needs a number before 'times'.",
                                       "Example: repeat 5 times")
                count_expr = self._parse_expression(count_text, idx)
                node = RepeatBlock(count_expr=count_expr, body=[], line=idx)
                current_list.append(node)
                stack.append(("repeat", node, current_list))
                current_list = node.body
                continue

            if stripped.startswith("make function "):
                rest = stripped[len("make function "):].strip()
                if not rest:
                    raise EasyLangError(idx, "Function needs a name.",
                                       "Example: make function greet name")
                parts = rest.split()
                name = parts[0]
                param = parts[1] if len(parts) > 1 else None
                if len(parts) > 2:
                    raise EasyLangError(idx, "Functions can only have one parameter.",
                                       "Example: make function greet name")
                if not is_valid_name(name):
                    raise EasyLangError(idx, f"'{name}' is not a valid function name.",
                                       "Use letters, numbers, and underscores. Start with a letter.")
                if param and not is_valid_name(param):
                    raise EasyLangError(idx, f"'{param}' is not a valid parameter name.",
                                       "Use letters, numbers, and underscores. Start with a letter.")
                node = FunctionDef(name=name, param=param, body=[], line=idx)
                current_list.append(node)
                stack.append(("function", node, current_list))
                current_list = node.body
                continue

            if stripped == "draw window:":
                node = WindowBlock(settings={}, body=[], draw=[], line=idx)
                current_list.append(node)
                stack.append(("window", node, current_list))
                current_list = node.body
                continue

            if stripped == "close window":
                current_list.append(CloseWindow(line=idx))
                continue

            if stripped.startswith("run "):
                rest = stripped[len("run "):].strip()
                if not rest:
                    raise EasyLangError(idx, "Run needs a function name.",
                                       "Example: run greet Alex")
                parts = rest.split(maxsplit=1)
                name = parts[0]
                arg_text = parts[1].strip() if len(parts) > 1 else None
                if not is_valid_name(name):
                    raise EasyLangError(idx, f"'{name}' is not a valid function name.",
                                       "Use letters, numbers, and underscores. Start with a letter.")
                current_list.append(RunFunction(name=name, arg_text=arg_text, line=idx))
                continue

            raise EasyLangError(idx, f"I don't understand this command: '{stripped}'.",
                               "Try: print:, printvar:, number, text, input, if, repeat, draw window:, run, end")

        if stack:
            block_type, node, _prev = stack[-1]
            raise EasyLangError(node.line, f"You forgot to close the {block_type.upper()} block with 'end'.",
                               "Add an 'end' line after the block.")

        return program

    def _split_assignment(self, rest: str, line: int):
        if "=" not in rest:
            raise EasyLangError(line, "Assignments need '='.", "Example: number apples = 5")
        left, right = rest.split("=", 1)
        name = left.strip()
        value = right.strip()
        if not name:
            raise EasyLangError(line, "Assignments need a variable name before '='.",
                               "Example: number apples = 5")
        if value == "":
            raise EasyLangError(line, "Assignments need a value after '='.",
                               "Example: number apples = 5")
        return name, value

    def _parse_expression(self, text: str, line: int) -> Expression:
        match = re.match(r"^(.+?)\s*([+\-*/])\s*(.+)$", text)
        if match:
            left = match.group(1).strip()
            op = match.group(2)
            right = match.group(3).strip()
            return Expression(left=self._parse_operand(left, line), op=op, right=self._parse_operand(right, line))
        return Expression(left=self._parse_operand(text.strip(), line))

    def _parse_condition(self, text: str, line: int) -> Condition:
        match = re.match(r"^(.+?)\s*(==|<|>)\s*(.+)$", text)
        if not match:
            raise EasyLangError(line, "If needs a condition with <, >, or ==.",
                               "Example: if apple < orange")
        left = match.group(1).strip()
        op = match.group(2)
        right = match.group(3).strip()
        return Condition(left=self._parse_operand(left, line), op=op, right=self._parse_operand(right, line))

    def _parse_operand(self, text: str, line: int) -> Operand:
        if not text:
            raise EasyLangError(line, "Missing value.", "Check your math or condition.")
        if is_number(text):
            return Operand(raw=text, is_number=True)
        return Operand(raw=text, is_number=False)
