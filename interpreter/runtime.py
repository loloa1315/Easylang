import os
import re
from typing import Any, Callable, Dict, List, Optional

from .parser import (
    EasyLangError,
    Program,
    PrintText,
    PrintVar,
    AssignNumber,
    AssignText,
    IfBlock,
    RepeatBlock,
    FunctionDef,
    RunFunction,
    Expression,
    Condition,
    Operand,
    InputStatement,
    WindowBlock,
    CloseWindow,
)


class StopExecution(Exception):
    pass


class Environment:
    def __init__(self):
        self.scopes: List[Dict[str, Any]] = [{}]

    def push(self):
        self.scopes.append({})

    def pop(self):
        if len(self.scopes) > 1:
            self.scopes.pop()

    def set(self, name: str, value: Any):
        self.scopes[-1][name] = value

    def get(self, name: str):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise KeyError(name)

    def has(self, name: str) -> bool:
        return any(name in scope for scope in self.scopes)


class Runtime:
    def __init__(self, output_callback: Optional[Callable[[str], None]] = None, stop_event=None):
        self.output = output_callback or (lambda text: print(text))
        self.stop_event = stop_event
        self.env = Environment()
        self.functions: Dict[str, FunctionDef] = {}
        self.window_should_close = False
        self.draw_cursor_y = 20

    def execute(self, program: Program):
        self._execute_statements(program.statements)

    def _check_stop(self):
        if self.stop_event and self.stop_event.is_set():
            raise StopExecution()

    def _execute_statements(self, statements: List):
        for stmt in statements:
            self._check_stop()
            if isinstance(stmt, PrintText):
                self.output(stmt.text)
            elif isinstance(stmt, PrintVar):
                value = self._eval_expression(stmt.expr, stmt.line)
                self.output(self._format_value(value))
            elif isinstance(stmt, AssignNumber):
                value = self._eval_expression(stmt.expr, stmt.line)
                if not isinstance(value, (int, float)):
                    raise EasyLangError(stmt.line, "Number variables can only store numbers.",
                                       "Use 'text' for words and names.")
                self.env.set(stmt.name, value)
            elif isinstance(stmt, AssignText):
                self.env.set(stmt.name, stmt.text)
            elif isinstance(stmt, InputStatement):
                self._handle_input(stmt)
            elif isinstance(stmt, IfBlock):
                if self._eval_condition(stmt.condition, stmt.line):
                    self._execute_statements(stmt.body)
            elif isinstance(stmt, RepeatBlock):
                count = self._eval_expression(stmt.count_expr, stmt.line)
                if not isinstance(count, (int, float)):
                    raise EasyLangError(stmt.line, "Repeat needs a number.",
                                       "Example: repeat 5 times")
                count_int = int(count)
                if count_int < 0:
                    raise EasyLangError(stmt.line, "Repeat cannot be negative.",
                                       "Use a positive number.")
                for _ in range(count_int):
                    self._check_stop()
                    self._execute_statements(stmt.body)
            elif isinstance(stmt, FunctionDef):
                self.functions[stmt.name] = stmt
            elif isinstance(stmt, RunFunction):
                self._run_function(stmt)
            elif isinstance(stmt, WindowBlock):
                self._run_window_block(stmt)
            elif isinstance(stmt, CloseWindow):
                self.window_should_close = True
            else:
                raise EasyLangError(0, "Unknown statement type.")

    def _handle_input(self, stmt: InputStatement):
        prompt = stmt.prompt.strip()
        if prompt:
            prompt = prompt + " "
        else:
            prompt = f"{stmt.name}: "
        if os.environ.get("EASYLANG_INPUT_MODE") == "marker":
            self.output(f"__EASY_INPUT__ {prompt}".rstrip())
            user_text = input()
        else:
            user_text = input(prompt)
        if self._looks_number(user_text):
            value = self._number_value(user_text)
        else:
            value = user_text
        self.env.set(stmt.name, value)

    def _run_window_block(self, stmt: WindowBlock):
        pygame = self._ensure_pygame(stmt.line)

        width, height = self._parse_window_size(stmt)
        title = stmt.settings.get("title", "EasyLang Window")
        background = self._parse_background(stmt)

        pygame.init()
        screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
        font = pygame.font.SysFont(None, 28)
        clock = pygame.time.Clock()

        self.window_should_close = False
        last_key = ""

        try:
            while not self.window_should_close:
                self._check_stop()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.window_should_close = True
                    elif event.type == pygame.KEYDOWN:
                        last_key = pygame.key.name(event.key).upper()

                mouse_x, mouse_y = pygame.mouse.get_pos()
                mouse_down = any(pygame.mouse.get_pressed())

                self.env.set("key", last_key)
                self.env.set("mouse_x", mouse_x)
                self.env.set("mouse_y", mouse_y)
                self.env.set("mouse_down", mouse_down)

                if stmt.body:
                    self._execute_statements(stmt.body)

                screen.fill(background)
                self.draw_cursor_y = 20
                self._execute_draw_statements(stmt.draw, screen, font)
                pygame.display.flip()
                clock.tick(60)
        finally:
            pygame.quit()

    def _execute_draw_statements(self, statements: List, screen, font):
        for stmt in statements:
            self._check_stop()
            if isinstance(stmt, PrintText):
                self._draw_text(screen, font, stmt.text)
            elif isinstance(stmt, PrintVar):
                value = self._eval_expression(stmt.expr, stmt.line)
                self._draw_text(screen, font, self._format_value(value))
            elif isinstance(stmt, AssignNumber):
                value = self._eval_expression(stmt.expr, stmt.line)
                if not isinstance(value, (int, float)):
                    raise EasyLangError(stmt.line, "Number variables can only store numbers.",
                                       "Use 'text' for words and names.")
                self.env.set(stmt.name, value)
            elif isinstance(stmt, AssignText):
                self.env.set(stmt.name, stmt.text)
            elif isinstance(stmt, IfBlock):
                if self._eval_condition(stmt.condition, stmt.line):
                    self._execute_draw_statements(stmt.body, screen, font)
            elif isinstance(stmt, RepeatBlock):
                count = self._eval_expression(stmt.count_expr, stmt.line)
                if not isinstance(count, (int, float)):
                    raise EasyLangError(stmt.line, "Repeat needs a number.",
                                       "Example: repeat 5 times")
                for _ in range(int(count)):
                    self._execute_draw_statements(stmt.body, screen, font)
            elif isinstance(stmt, CloseWindow):
                self.window_should_close = True
            else:
                raise EasyLangError(stmt.line, "This command is not allowed inside draw: block.",
                                   "Use print: or printvar: inside draw:.")

    def _draw_text(self, screen, font, text: str):
        color = (255, 255, 255)
        surface = font.render(text, True, color)
        screen.blit(surface, (20, self.draw_cursor_y))
        self.draw_cursor_y += surface.get_height() + 6

    def _parse_window_size(self, stmt: WindowBlock):
        raw = stmt.settings.get("window_size") or stmt.settings.get("windows_size")
        if not raw:
            return 640, 480
        raw = raw.lower().replace(" ", "")
        if "x" not in raw:
            raise EasyLangError(stmt.line, "window_size must look like 800x600.",
                               "Example: window_size = 800x600")
        w, h = raw.split("x", 1)
        if not w.isdigit() or not h.isdigit():
            raise EasyLangError(stmt.line, "window_size must be two numbers like 800x600.",
                               "Example: window_size = 800x600")
        return int(w), int(h)

    def _parse_background(self, stmt: WindowBlock):
        raw = stmt.settings.get("background", "0,0,0")
        parts = re.split(r"[, ]+", raw.strip())
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise EasyLangError(stmt.line, "background must be three numbers like 10,20,30.",
                               "Example: background = 10,20,30")
        return tuple(int(p) for p in parts)

    def _ensure_pygame(self, line: int):
        try:
            import pygame
            return pygame
        except Exception:
            raise EasyLangError(line, "Pygame is required for window drawing.",
                               "Install it with: pip install pygame")

    def _run_function(self, stmt: RunFunction):
        if stmt.name not in self.functions:
            raise EasyLangError(stmt.line, f"Function '{stmt.name}' does not exist.",
                               "Make sure you wrote 'make function' before 'run'.")
        func = self.functions[stmt.name]
        self.env.push()
        try:
            if func.param:
                if stmt.arg_text is None:
                    raise EasyLangError(stmt.line, f"Function '{stmt.name}' needs one value.",
                                       f"Example: run {stmt.name} Alex")
                arg_value = self._resolve_name_or_literal(stmt.arg_text, stmt.line, allow_literal=True)
                self.env.set(func.param, arg_value)
            else:
                if stmt.arg_text is not None:
                    raise EasyLangError(stmt.line, f"Function '{stmt.name}' takes no values.",
                                       f"Example: run {stmt.name}")
            self._execute_statements(func.body)
        finally:
            self.env.pop()

    def _eval_expression(self, expr: Expression, line: int):
        left = self._resolve_operand(expr.left, line)
        if expr.op is None:
            return left
        right = self._resolve_operand(expr.right, line)
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise EasyLangError(line, "Math only works with numbers.",
                               "Use 'number' variables or check your values.")
        if expr.op == "+":
            return left + right
        if expr.op == "-":
            return left - right
        if expr.op == "*":
            return left * right
        if expr.op == "/":
            if right == 0:
                raise EasyLangError(line, "You tried to divide by zero.",
                                   "Change the right side to a non-zero number.")
            return left / right
        raise EasyLangError(line, f"Unknown operator '{expr.op}'.")

    def _eval_condition(self, cond: Condition, line: int) -> bool:
        if cond.op in ("<", ">"):
            left = self._resolve_operand(cond.left, line)
            right = self._resolve_operand(cond.right, line)
            if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                raise EasyLangError(line, "< and > only work with numbers.",
                                   "Use number variables in comparisons.")
            return left < right if cond.op == "<" else left > right
        if cond.op == "==":
            left = self._resolve_name_or_literal(cond.left.raw, line, allow_literal=True)
            right = self._resolve_name_or_literal(cond.right.raw, line, allow_literal=True)
            return str(left) == str(right)
        raise EasyLangError(line, f"Unknown comparison '{cond.op}'.")

    def _resolve_operand(self, operand: Optional[Operand], line: int):
        if operand is None:
            raise EasyLangError(line, "Missing value.")
        if operand.is_number:
            return self._number_value(operand.raw)
        return self._resolve_name_or_literal(operand.raw, line, allow_literal=False)

    def _resolve_name_or_literal(self, raw: str, line: int, allow_literal: bool):
        if self.env.has(raw):
            return self.env.get(raw)
        if allow_literal:
            if self._looks_number(raw):
                return self._number_value(raw)
            return raw
        raise EasyLangError(line, f"'{raw}' is not defined.",
                           "Create it first with 'number' or 'text'.")

    def _number_value(self, raw: str):
        if "." in raw:
            return float(raw)
        return int(raw)

    def _looks_number(self, raw: str) -> bool:
        if raw.startswith("-"):
            raw = raw[1:]
        if raw.count(".") > 1:
            return False
        raw = raw.replace(".", "")
        return raw.isdigit()

    def _format_value(self, value: Any) -> str:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
