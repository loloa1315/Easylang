import os
import re
import sys
import time
import queue
import threading
import pygame
import subprocess

from compiler.packager import build_package
from dataclasses import dataclass


EASY_COMMANDS = [
    "print:",
    "printvar:",
    "number",
    "text",
    "input",
    "if",
    "repeat",
    "times",
    "make function",
    "run",
    "draw window:",
    "draw:",
    "close window",
    "window_size",
    "windows_size",
    "title",
    "background",
    "end",
]

BEGINNER_GUIDE = """EasyLang Beginner Guide

Basics:
print: Hello world
printvar: apples + oranges

Variables:
number apples = 5
text name = John

Input:
input name = What is your name?

Conditions:
if apples < oranges
    print: Apples are fewer
end

Loops:
repeat 3 times
    print: hello
end

Window:
draw window:
    window_size = 800x600
    title = EasyLang Window
    background = 10,20,30
    draw:
        print: Hello from EasyLang
end

Functions:
make function greet name
    print: Hello
    printvar: name
end

run greet Alex
"""

TIPS = (
    "Tips for beginners:\n"
    "- Use print: for words and sentences.\n"
    "- Use printvar: for numbers or variables.\n"
    "- Always close blocks with end.\n"
    "- Use repeat for loops.\n"
    "- Use make function and run to create reusable actions.\n"
    "- Use input to get answers from the user."
)


@dataclass
class Button:
    label: str
    rect: pygame.Rect
    tooltip: str
    action: callable

    def draw(self, surface, font, colors, hover=False):
        bg = colors["button_hover"] if hover else colors["button"]
        pygame.draw.rect(surface, bg, self.rect, border_radius=6)
        pygame.draw.rect(surface, colors["button_border"], self.rect, 1, border_radius=6)
        text = font.render(self.label, True, colors["text"])
        surface.blit(text, (self.rect.x + 10, self.rect.y + (self.rect.height - text.get_height()) // 2))

    def hit(self, pos):
        return self.rect.collidepoint(pos)


class TextEditor:
    def __init__(self, rect, font, colors):
        self.rect = rect
        self.font = font
        self.colors = colors
        self.line_height = font.get_linesize() + 4
        self.lines = [""]
        self.cursor_row = 0
        self.cursor_col = 0
        self.scroll = 0
        self.suggestion = ""

    def set_text(self, text: str):
        self.lines = text.splitlines()
        if not self.lines:
            self.lines = [""]
        self.cursor_row = 0
        self.cursor_col = 0
        self.scroll = 0

    def get_text(self) -> str:
        return "\n".join(self.lines) + "\n"

    def insert_text(self, text: str):
        line = self.lines[self.cursor_row]
        self.lines[self.cursor_row] = line[:self.cursor_col] + text + line[self.cursor_col:]
        self.cursor_col += len(text)

    def backspace(self):
        if self.cursor_col > 0:
            line = self.lines[self.cursor_row]
            self.lines[self.cursor_row] = line[:self.cursor_col - 1] + line[self.cursor_col:]
            self.cursor_col -= 1
        elif self.cursor_row > 0:
            prev_line = self.lines[self.cursor_row - 1]
            line = self.lines[self.cursor_row]
            self.cursor_col = len(prev_line)
            self.lines[self.cursor_row - 1] = prev_line + line
            self.lines.pop(self.cursor_row)
            self.cursor_row -= 1

    def delete(self):
        line = self.lines[self.cursor_row]
        if self.cursor_col < len(line):
            self.lines[self.cursor_row] = line[:self.cursor_col] + line[self.cursor_col + 1:]
        elif self.cursor_row < len(self.lines) - 1:
            next_line = self.lines[self.cursor_row + 1]
            self.lines[self.cursor_row] = line + next_line
            self.lines.pop(self.cursor_row + 1)

    def newline(self):
        line = self.lines[self.cursor_row]
        indent = self._current_indent(line)
        extra = ""
        stripped = line.strip()
        if stripped.startswith("if ") or stripped.startswith("repeat ") or stripped.startswith("make function ") or stripped.startswith("draw window:"):
            extra = "    "
        new_indent = indent + extra
        self.lines[self.cursor_row] = line[:self.cursor_col]
        self.lines.insert(self.cursor_row + 1, new_indent + line[self.cursor_col:])
        self.cursor_row += 1
        self.cursor_col = len(new_indent)

    def _current_indent(self, line: str) -> str:
        return line[: len(line) - len(line.lstrip(" "))]

    def move_cursor(self, dr, dc):
        self.cursor_row = max(0, min(len(self.lines) - 1, self.cursor_row + dr))
        self.cursor_col = max(0, min(len(self.lines[self.cursor_row]), self.cursor_col + dc))

    def move_cursor_home(self):
        self.cursor_col = 0

    def move_cursor_end(self):
        self.cursor_col = len(self.lines[self.cursor_row])

    def handle_key(self, event):
        self.suggestion = ""
        if event.key == pygame.K_BACKSPACE:
            self.backspace()
        elif event.key == pygame.K_DELETE:
            self.delete()
        elif event.key == pygame.K_RETURN:
            self.newline()
        elif event.key == pygame.K_TAB:
            self.handle_autocomplete()
        elif event.key == pygame.K_LEFT:
            self.move_cursor(0, -1)
        elif event.key == pygame.K_RIGHT:
            self.move_cursor(0, 1)
        elif event.key == pygame.K_UP:
            self.move_cursor(-1, 0)
        elif event.key == pygame.K_DOWN:
            self.move_cursor(1, 0)
        elif event.key == pygame.K_HOME:
            self.move_cursor_home()
        elif event.key == pygame.K_END:
            self.move_cursor_end()
        else:
            if event.unicode and event.unicode.isprintable():
                self.insert_text(event.unicode)
        self._ensure_visible()

    def handle_autocomplete(self):
        line = self.lines[self.cursor_row]
        prefix = line[:self.cursor_col].lstrip(" ")
        if " " in prefix:
            self.insert_text("    ")
            return
        stripped = prefix
        if not stripped:
            self.insert_text("    ")
            return
        matches = [cmd for cmd in EASY_COMMANDS if cmd.startswith(stripped)]
        if len(matches) == 1:
            self.lines[self.cursor_row] = line[:self.cursor_col - len(stripped)] + matches[0] + line[self.cursor_col:]
            self.cursor_col = self.cursor_col - len(stripped) + len(matches[0])
        elif len(matches) > 1:
            self.suggestion = "Suggestions: " + ", ".join(matches[:6])
        else:
            self.insert_text("    ")

    def _ensure_visible(self):
        max_visible = self.visible_lines()
        if self.cursor_row < self.scroll:
            self.scroll = self.cursor_row
        elif self.cursor_row >= self.scroll + max_visible:
            self.scroll = self.cursor_row - max_visible + 1

    def visible_lines(self):
        return max(1, (self.rect.height // self.line_height) - 1)

    def draw(self, surface):
        pygame.draw.rect(surface, self.colors["editor_bg"], self.rect)
        pygame.draw.rect(surface, self.colors["panel_border"], self.rect, 1)

        gutter_width = 48
        gutter = pygame.Rect(self.rect.x, self.rect.y, gutter_width, self.rect.height)
        pygame.draw.rect(surface, self.colors["gutter"], gutter)
        pygame.draw.line(surface, self.colors["panel_border"], (gutter.right, self.rect.y), (gutter.right, self.rect.y + self.rect.height))

        start_line = self.scroll
        end_line = min(len(self.lines), start_line + self.visible_lines())
        y = self.rect.y + 6

        for i in range(start_line, end_line):
            line = self.lines[i]
            num_text = self.font.render(str(i + 1), True, self.colors["gutter_text"])
            surface.blit(num_text, (self.rect.x + 10, y))

            self._draw_highlighted_line(surface, line, self.rect.x + gutter_width + 8, y)
            y += self.line_height

        self._draw_cursor(surface, gutter_width)

        if self.suggestion:
            self._draw_suggestion(surface)

    def _draw_highlighted_line(self, surface, line, x, y):
        if "#" in line:
            code, comment = line.split("#", 1)
        else:
            code, comment = line, ""

        chunks = self._syntax_chunks(code)
        cursor_x = x
        for text, color in chunks:
            if text:
                img = self.font.render(text, True, color)
                surface.blit(img, (cursor_x, y))
                cursor_x += img.get_width()

        if comment:
            img = self.font.render("#" + comment, True, self.colors["comment"])
            surface.blit(img, (cursor_x, y))

    def _syntax_chunks(self, text):
        keywords = [
            "print:", "printvar:", "number", "text", "input", "if", "repeat", "times",
            "make", "function", "run", "draw", "window:", "draw:", "close", "end",
            "window_size", "windows_size", "title", "background",
        ]
        pattern = r"(\b\d+(?:\.\d+)?\b|printvar:|print:|\b(?:number|text|input|if|repeat|times|make|function|run|draw|window:|draw:|close|end|window_size|windows_size|title|background)\b)"
        parts = []
        last = 0
        for match in re.finditer(pattern, text):
            if match.start() > last:
                parts.append((text[last:match.start()], self.colors["text"]))
            token = match.group(0)
            if token.replace(".", "", 1).isdigit():
                color = self.colors["number"]
            else:
                color = self.colors["keyword"]
            parts.append((token, color))
            last = match.end()
        if last < len(text):
            parts.append((text[last:], self.colors["text"]))
        return parts

    def _draw_cursor(self, surface, gutter_width):
        start_line = self.scroll
        end_line = min(len(self.lines), start_line + self.visible_lines())
        if not (start_line <= self.cursor_row < end_line):
            return
        line = self.lines[self.cursor_row]
        before = line[:self.cursor_col]
        x = self.rect.x + gutter_width + 8 + self.font.size(before)[0]
        y = self.rect.y + 6 + (self.cursor_row - start_line) * self.line_height
        pygame.draw.rect(surface, self.colors["cursor"], (x, y, 2, self.font.get_height()))

    def _draw_suggestion(self, surface):
        padding = 8
        text = self.font.render(self.suggestion, True, self.colors["text"])
        w = text.get_width() + padding * 2
        h = text.get_height() + padding * 2
        rect = pygame.Rect(self.rect.x + 20, self.rect.y + self.rect.height - h - 10, w, h)
        pygame.draw.rect(surface, self.colors["popup_bg"], rect, border_radius=6)
        pygame.draw.rect(surface, self.colors["panel_border"], rect, 1, border_radius=6)
        surface.blit(text, (rect.x + padding, rect.y + padding))


class ConsolePanel:
    def __init__(self, rect, font, colors):
        self.rect = rect
        self.font = font
        self.colors = colors
        self.line_height = font.get_linesize() + 2
        self.lines = []
        self.scroll = 0

    def append(self, text: str, is_error=False):
        for line in text.splitlines() or [""]:
            self.lines.append((line, is_error))
        self.scroll = max(0, len(self.lines) - self.visible_lines())

    def clear(self):
        self.lines = []
        self.scroll = 0

    def visible_lines(self):
        return max(1, (self.rect.height // self.line_height) - 1)

    def draw(self, surface):
        pygame.draw.rect(surface, self.colors["console_bg"], self.rect)
        pygame.draw.rect(surface, self.colors["panel_border"], self.rect, 1)
        start = self.scroll
        end = min(len(self.lines), start + self.visible_lines())
        y = self.rect.y + 6
        for i in range(start, end):
            line, is_error = self.lines[i]
            color = self.colors["error"] if is_error else self.colors["text"]
            img = self.font.render(line, True, color)
            surface.blit(img, (self.rect.x + 8, y))
            y += self.line_height


class ModalInput:
    def __init__(self, title, prompt="", initial=""):
        self.title = title
        self.prompt = prompt
        self.value = initial
        self.active = True
        self.result = None

    def handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            self.active = False
            self.result = None
        elif event.key == pygame.K_RETURN:
            self.active = False
            self.result = self.value
        elif event.key == pygame.K_BACKSPACE:
            self.value = self.value[:-1]
        else:
            if event.unicode and event.unicode.isprintable():
                self.value += event.unicode

    def draw(self, surface, font, colors):
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        width = 520
        height = 180
        rect = pygame.Rect((surface.get_width() - width) // 2, (surface.get_height() - height) // 2, width, height)
        pygame.draw.rect(surface, colors["popup_bg"], rect, border_radius=8)
        pygame.draw.rect(surface, colors["panel_border"], rect, 1, border_radius=8)

        title = font.render(self.title, True, colors["text"])
        surface.blit(title, (rect.x + 20, rect.y + 18))

        prompt = font.render(self.prompt, True, colors["muted"])
        surface.blit(prompt, (rect.x + 20, rect.y + 56))

        box = pygame.Rect(rect.x + 20, rect.y + 90, rect.width - 40, 36)
        pygame.draw.rect(surface, colors["editor_bg"], box, border_radius=6)
        pygame.draw.rect(surface, colors["panel_border"], box, 1, border_radius=6)

        text = font.render(self.value, True, colors["text"])
        surface.blit(text, (box.x + 10, box.y + 8))


class InfoModal:
    def __init__(self, title, text):
        self.title = title
        self.text = text
        self.active = True

    def handle_key(self, event):
        if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
            self.active = False

    def draw(self, surface, font, colors):
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        width = 600
        height = 320
        rect = pygame.Rect((surface.get_width() - width) // 2, (surface.get_height() - height) // 2, width, height)
        pygame.draw.rect(surface, colors["popup_bg"], rect, border_radius=8)
        pygame.draw.rect(surface, colors["panel_border"], rect, 1, border_radius=8)

        title = font.render(self.title, True, colors["text"])
        surface.blit(title, (rect.x + 20, rect.y + 18))

        y = rect.y + 58
        for line in self.text.splitlines():
            img = font.render(line, True, colors["muted"])
            surface.blit(img, (rect.x + 20, y))
            y += 22

class ExamplePicker:
    def __init__(self, examples):
        self.examples = examples
        self.active = True
        self.selected = 0
        self.action = None

    def handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            self.active = False
        elif event.key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
        elif event.key == pygame.K_DOWN:
            self.selected = min(len(self.examples) - 1, self.selected + 1)
        elif event.key == pygame.K_RETURN:
            self.action = "load"
            self.active = False
        elif event.key == pygame.K_r:
            self.action = "run"
            self.active = False

    def handle_click(self, pos, rect):
        x, y = pos
        if not rect.collidepoint(pos):
            return
        index = (y - rect.y - 60) // 28
        if 0 <= index < len(self.examples):
            self.selected = index

    def draw(self, surface, font, colors):
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        width = 420
        height = 320
        rect = pygame.Rect((surface.get_width() - width) // 2, (surface.get_height() - height) // 2, width, height)
        pygame.draw.rect(surface, colors["popup_bg"], rect, border_radius=8)
        pygame.draw.rect(surface, colors["panel_border"], rect, 1, border_radius=8)

        title = font.render("Examples (Enter=Load, R=Run)", True, colors["text"])
        surface.blit(title, (rect.x + 20, rect.y + 18))

        y = rect.y + 60
        for i, name in enumerate(self.examples):
            color = colors["keyword"] if i == self.selected else colors["text"]
            line = font.render(name, True, color)
            surface.blit(line, (rect.x + 20, y))
            y += 28
        return rect


class BuildPicker:
    def __init__(self):
        self.options = [
            ("deb", ".deb(debian/ubunto)"),
            ("exe", ".exe(windows)"),
            ("pkg.tar.zst", ".pkg.tar.zst(archlinux)"),
            ("pkg", ".pkg(macos)"),
        ]
        self.active = True
        self.selected = 0
        self.action = None

    def handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            self.active = False
        elif event.key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
        elif event.key == pygame.K_DOWN:
            self.selected = min(len(self.options) - 1, self.selected + 1)
        elif event.key == pygame.K_RETURN:
            self.action = "build"
            self.active = False

    def handle_click(self, pos, rect):
        if not rect.collidepoint(pos):
            return
        index = (pos[1] - rect.y - 60) // 28
        if 0 <= index < len(self.options):
            self.selected = index

    def draw(self, surface, font, colors):
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        width = 460
        height = 260
        rect = pygame.Rect((surface.get_width() - width) // 2, (surface.get_height() - height) // 2, width, height)
        pygame.draw.rect(surface, colors["popup_bg"], rect, border_radius=8)
        pygame.draw.rect(surface, colors["panel_border"], rect, 1, border_radius=8)

        title = font.render("Build Package", True, colors["text"])
        surface.blit(title, (rect.x + 20, rect.y + 18))
        y = rect.y + 60
        for i, (_key, label) in enumerate(self.options):
            color = colors["keyword"] if i == self.selected else colors["text"]
            line = font.render(label, True, color)
            surface.blit(line, (rect.x + 20, y))
            y += 28
        return rect


class FileExplorer:
    def __init__(self, mode, start_dir, initial_name=""):
        self.mode = mode  # "open" or "save"
        self.current_dir = os.path.abspath(start_dir)
        self.entries = []
        self.selected = 0
        self.scroll = 0
        self.active = True
        self.result = None
        self.filename = initial_name
        self.last_click_time = 0
        self._refresh()

    def _refresh(self):
        self.entries = []
        parent = os.path.dirname(self.current_dir)
        if parent and parent != self.current_dir:
            self.entries.append(("..", parent, True))
        try:
            names = os.listdir(self.current_dir)
        except FileNotFoundError:
            names = []
        dirs = []
        files = []
        for name in sorted(names):
            path = os.path.join(self.current_dir, name)
            if os.path.isdir(path):
                dirs.append((name, path, True))
            elif name.endswith(".el"):
                files.append((name, path, False))
        self.entries.extend(dirs + files)
        self.selected = 0
        self.scroll = 0

    def handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            self.active = False
            return
        if event.key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
            return
        if event.key == pygame.K_DOWN:
            self.selected = min(len(self.entries) - 1, self.selected + 1)
            return
        if event.key == pygame.K_BACKSPACE and self.mode == "save":
            self.filename = self.filename[:-1]
            return
        if event.key == pygame.K_RETURN:
            self._activate_selected()
            return
        if self.mode == "save" and event.unicode and event.unicode.isprintable():
            self.filename += event.unicode

    def handle_click(self, pos, rect):
        if not rect.collidepoint(pos):
            return
        list_top = rect.y + 70
        row_height = 26
        index = (pos[1] - list_top) // row_height + self.scroll
        if 0 <= index < len(self.entries):
            self.selected = index
            now = time.time()
            if now - self.last_click_time < 0.3:
                self._activate_selected()
            self.last_click_time = now

    def handle_scroll(self, direction):
        max_scroll = max(0, len(self.entries) - self.visible_rows())
        self.scroll = max(0, min(max_scroll, self.scroll - direction))

    def visible_rows(self):
        return 10

    def _activate_selected(self):
        if not self.entries:
            return
        name, path, is_dir = self.entries[self.selected]
        if is_dir:
            self.current_dir = path
            self._refresh()
            return
        if self.mode == "open":
            self.result = path
            self.active = False
            return
        if self.mode == "save":
            self.filename = name
            self._finalize_save()

    def _finalize_save(self):
        if not self.filename:
            return
        filename = self.filename
        if not filename.endswith(".el"):
            filename += ".el"
        self.result = os.path.join(self.current_dir, filename)
        self.active = False

    def draw(self, surface, font, colors):
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        width = 720
        height = 420
        rect = pygame.Rect((surface.get_width() - width) // 2, (surface.get_height() - height) // 2, width, height)
        pygame.draw.rect(surface, colors["popup_bg"], rect, border_radius=8)
        pygame.draw.rect(surface, colors["panel_border"], rect, 1, border_radius=8)

        title_text = "Open File" if self.mode == "open" else "Save File"
        title = font.render(title_text, True, colors["text"])
        surface.blit(title, (rect.x + 20, rect.y + 16))

        path_text = font.render(self.current_dir, True, colors["muted"])
        surface.blit(path_text, (rect.x + 20, rect.y + 44))

        list_top = rect.y + 70
        row_height = 26
        visible = self.visible_rows()
        start = self.scroll
        end = min(len(self.entries), start + visible)
        for i in range(start, end):
            name, _path, is_dir = self.entries[i]
            y = list_top + (i - start) * row_height
            if i == self.selected:
                pygame.draw.rect(surface, colors["button_hover"], (rect.x + 14, y - 2, rect.width - 28, row_height), border_radius=4)
            label = f"[{name}]" if is_dir else name
            color = colors["keyword"] if is_dir else colors["text"]
            line = font.render(label, True, color)
            surface.blit(line, (rect.x + 20, y))

        if self.mode == "save":
            box = pygame.Rect(rect.x + 20, rect.y + rect.height - 70, rect.width - 40, 32)
            pygame.draw.rect(surface, colors["editor_bg"], box, border_radius=6)
            pygame.draw.rect(surface, colors["panel_border"], box, 1, border_radius=6)
            hint = font.render("Filename:", True, colors["muted"])
            surface.blit(hint, (box.x, box.y - 22))
            text = font.render(self.filename, True, colors["text"])
            surface.blit(text, (box.x + 8, box.y + 6))

        footer = "Enter to select, Esc to cancel, double click to open"
        footer_img = font.render(footer, True, colors["muted"])
        surface.blit(footer_img, (rect.x + 20, rect.y + rect.height - 28))
        return rect

class EasyLangIDE:
    def __init__(self, initial_file=None):
        pygame.init()
        pygame.display.set_caption("EasyLang IDE (Pygame)")
        self.screen = pygame.display.set_mode((1280, 800))
        self.clock = pygame.time.Clock()

        self.colors = {
            "bg": (20, 22, 28),
            "panel": (27, 30, 37),
            "panel_border": (48, 52, 60),
            "editor_bg": (17, 19, 24),
            "console_bg": (12, 13, 16),
            "gutter": (25, 27, 33),
            "gutter_text": (120, 125, 135),
            "button": (42, 46, 56),
            "button_hover": (60, 66, 78),
            "button_border": (68, 72, 80),
            "text": (222, 226, 230),
            "muted": (170, 175, 185),
            "keyword": (92, 164, 214),
            "number": (150, 220, 150),
            "comment": (120, 140, 120),
            "cursor": (230, 230, 230),
            "error": (255, 120, 120),
            "popup_bg": (32, 36, 44),
        }

        self.font = pygame.font.SysFont("Consolas", 16)
        self.small_font = pygame.font.SysFont("Consolas", 14)

        self.workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.examples_dir = os.path.join(self.workspace, "examples")
        self.current_file = None

        self.toolbar_height = 46
        self.sidebar_width = 220
        self.guide_width = 260
        self.console_height = 160

        self.editor_rect = pygame.Rect(
            self.sidebar_width,
            self.toolbar_height,
            self.screen.get_width() - self.sidebar_width - self.guide_width,
            self.screen.get_height() - self.toolbar_height - self.console_height,
        )
        self.console_rect = pygame.Rect(
            self.sidebar_width,
            self.screen.get_height() - self.console_height,
            self.screen.get_width() - self.sidebar_width - self.guide_width,
            self.console_height,
        )
        self.sidebar_rect = pygame.Rect(0, self.toolbar_height, self.sidebar_width, self.screen.get_height() - self.toolbar_height)
        self.guide_rect = pygame.Rect(self.screen.get_width() - self.guide_width, self.toolbar_height, self.guide_width, self.screen.get_height() - self.toolbar_height)

        self.editor = TextEditor(self.editor_rect, self.font, self.colors)
        self.console = ConsolePanel(self.console_rect, self.small_font, self.colors)

        self.buttons = []
        self._build_buttons()

        self.output_queue = queue.Queue()
        self.prompt_queue = queue.Queue()
        self.process = None

        self.modal = None
        self.examples_popup = None
        self.file_picker = None
        self.build_picker = None
        self.pending_build_target = None
        self.build_thread = None
        self.build_log_path = None
        self.pending_prompt = None
        self.guide_scroll = 0

        if initial_file and os.path.exists(initial_file):
            self.open_file(initial_file)
        else:
            self._load_default_example()

    def _build_buttons(self):
        labels = [
            ("New", "Start a new file", self.new_file),
            ("Open", "Open an .el file", self.open_file_prompt),
            ("Save", "Save the current file", self.save_file_prompt),
            ("Run", "Run the current program", self.run_code),
            ("Stop", "Stop a running program", self.stop_code),
            ("Examples", "Load or run an example", self.show_examples),
            ("Build", "Package into .deb/.exe/.pkg.tar.zst/.pkg", self.show_builds),
            ("Tips", "Show beginner tips", self.show_tips),
        ]
        x = 12
        for label, tip, action in labels:
            rect = pygame.Rect(x, 8, 92, 30)
            self.buttons.append(Button(label, rect, tip, action))
            x += 102

    def _load_default_example(self):
        path = os.path.join(self.examples_dir, "hello.el")
        if os.path.exists(path):
            self.open_file(path)
        else:
            self.editor.set_text("print: Hello world")

    def run(self):
        running = True
        while running:
            self.clock.tick(60)
            running = self._handle_events()
            self._drain_output()
            self._draw()
        pygame.quit()

    def _handle_events(self):
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.stop_code()
                return False

            if self.modal:
                if event.type == pygame.KEYDOWN:
                    self.modal.handle_key(event)
                    if not self.modal.active:
                        result = getattr(self.modal, "result", None)
                        modal_type = self.modal.title
                        self.modal = None
                        self._handle_modal_result(modal_type, result)
                if event.type == pygame.MOUSEBUTTONDOWN and hasattr(self.modal, "active"):
                    self.modal.active = False
                    result = getattr(self.modal, "result", None)
                    modal_type = self.modal.title
                    self.modal = None
                    self._handle_modal_result(modal_type, result)
                continue

            if self.file_picker:
                if event.type == pygame.KEYDOWN:
                    self.file_picker.handle_key(event)
                    if not self.file_picker.active:
                        result = self.file_picker.result
                        mode = self.file_picker.mode
                        self.file_picker = None
                        if result and mode == "open":
                            self.open_file(result)
                        elif result and mode == "save":
                            self.save_file(result)
                        elif mode == "save" and self.pending_build_target:
                            self.console.append("Build canceled (no file selected).", is_error=True)
                            self.pending_build_target = None
                if event.type == pygame.MOUSEBUTTONDOWN:
                    rect = self.file_picker.draw(self.screen, self.font, self.colors)
                    self.file_picker.handle_click(event.pos, rect)
                if event.type == pygame.MOUSEWHEEL:
                    self.file_picker.handle_scroll(event.y)
                continue

            if self.examples_popup:
                if event.type == pygame.KEYDOWN:
                    self.examples_popup.handle_key(event)
                    if not self.examples_popup.active:
                        action = self.examples_popup.action
                        selected = self.examples_popup.examples[self.examples_popup.selected] if self.examples_popup.examples else None
                        self.examples_popup = None
                        if selected and action:
                            if action == "load":
                                self.load_example(selected)
                            else:
                                self.run_example(selected)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    rect = self.examples_popup.draw(self.screen, self.font, self.colors)
                    self.examples_popup.handle_click(event.pos, rect)
                continue

            if self.build_picker:
                if event.type == pygame.KEYDOWN:
                    self.build_picker.handle_key(event)
                    if not self.build_picker.active:
                        action = self.build_picker.action
                        key, _label = self.build_picker.options[self.build_picker.selected]
                        self.build_picker = None
                        if action == "build":
                            self.build_package_target(key)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    rect = self.build_picker.draw(self.screen, self.font, self.colors)
                    self.build_picker.handle_click(event.pos, rect)
                continue

            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self._handle_toolbar_click(mouse_pos):
                        continue
                    if self.sidebar_rect.collidepoint(mouse_pos):
                        self._handle_sidebar_click(mouse_pos)
                        continue
            if event.type == pygame.KEYDOWN:
                if event.mod & pygame.KMOD_CTRL and event.key == pygame.K_s:
                    self.save_file_prompt()
                elif event.mod & pygame.KMOD_CTRL and event.key == pygame.K_o:
                    self.open_file_prompt()
                elif event.mod & pygame.KMOD_CTRL and event.key == pygame.K_n:
                    self.new_file()
                elif event.mod & pygame.KMOD_CTRL and event.key == pygame.K_r:
                    self.run_code()
                elif event.key == pygame.K_F5:
                    self.run_code()
                elif event.key == pygame.K_ESCAPE:
                    self.stop_code()
                else:
                    if self.editor_rect.collidepoint(mouse_pos):
                        self.editor.handle_key(event)

            if event.type == pygame.MOUSEWHEEL:
                if self.editor_rect.collidepoint(mouse_pos):
                    self.editor.scroll = max(0, self.editor.scroll - event.y)
                elif self.guide_rect.collidepoint(mouse_pos):
                    self.guide_scroll = max(0, self.guide_scroll - event.y * 20)
                elif self.console_rect.collidepoint(mouse_pos):
                    self.console.scroll = max(0, self.console.scroll - event.y)

        return True

    def _draw(self):
        self.screen.fill(self.colors["bg"])
        self._draw_toolbar()
        self._draw_sidebar()
        self.editor.draw(self.screen)
        self.console.draw(self.screen)
        self._draw_guide()
        self._draw_status()
        if self.modal:
            self.modal.draw(self.screen, self.font, self.colors)
        if self.examples_popup:
            self.examples_popup.draw(self.screen, self.font, self.colors)
        if self.file_picker:
            self.file_picker.draw(self.screen, self.font, self.colors)
        if self.build_picker:
            self.build_picker.draw(self.screen, self.font, self.colors)
        pygame.display.flip()

    def _draw_toolbar(self):
        bar = pygame.Rect(0, 0, self.screen.get_width(), self.toolbar_height)
        pygame.draw.rect(self.screen, self.colors["panel"], bar)
        pygame.draw.line(self.screen, self.colors["panel_border"], (0, bar.bottom), (bar.right, bar.bottom))
        mouse_pos = pygame.mouse.get_pos()
        for button in self.buttons:
            hover = button.hit(mouse_pos)
            button.draw(self.screen, self.small_font, self.colors, hover=hover)

    def _draw_sidebar(self):
        pygame.draw.rect(self.screen, self.colors["panel"], self.sidebar_rect)
        pygame.draw.line(self.screen, self.colors["panel_border"], (self.sidebar_rect.right, self.sidebar_rect.y), (self.sidebar_rect.right, self.sidebar_rect.bottom))
        title = self.small_font.render("Explorer", True, self.colors["text"])
        self.screen.blit(title, (12, self.toolbar_height + 10))

        y = self.toolbar_height + 40
        files = self._list_el_files(self.workspace)
        for path in files[:25]:
            name = os.path.basename(path)
            color = self.colors["keyword"] if path == self.current_file else self.colors["text"]
            line = self.small_font.render(name, True, color)
            self.screen.blit(line, (12, y))
            y += 22

    def _draw_guide(self):
        pygame.draw.rect(self.screen, self.colors["panel"], self.guide_rect)
        pygame.draw.line(self.screen, self.colors["panel_border"], (self.guide_rect.x, self.guide_rect.y), (self.guide_rect.x, self.guide_rect.bottom))
        title = self.small_font.render("Beginner Guide", True, self.colors["text"])
        self.screen.blit(title, (self.guide_rect.x + 12, self.guide_rect.y + 10))

        lines = BEGINNER_GUIDE.splitlines()
        y = self.guide_rect.y + 38 - self.guide_scroll
        for line in lines:
            if y > self.guide_rect.bottom - 20:
                break
            if y > self.guide_rect.y:
                img = self.small_font.render(line, True, self.colors["muted"])
                self.screen.blit(img, (self.guide_rect.x + 12, y))
            y += 20

    def _draw_status(self):
        mouse_pos = pygame.mouse.get_pos()
        tooltip = ""
        for button in self.buttons:
            if button.hit(mouse_pos):
                tooltip = button.tooltip
                break
        if tooltip:
            text = self.small_font.render(tooltip, True, self.colors["muted"])
            self.screen.blit(text, (self.sidebar_rect.right + 12, self.toolbar_height - 20))

    def _handle_toolbar_click(self, pos):
        for button in self.buttons:
            if button.hit(pos):
                button.action()
                return True
        return False

    def _handle_sidebar_click(self, pos):
        files = self._list_el_files(self.workspace)
        y_start = self.toolbar_height + 40
        index = (pos[1] - y_start) // 22
        if 0 <= index < len(files):
            self.open_file(files[index])

    def _list_el_files(self, root):
        try:
            names = [os.path.join(root, f) for f in os.listdir(root) if f.endswith(".el")]
            return sorted(names)
        except FileNotFoundError:
            return []

    def show_tips(self):
        self.modal = InfoModal("Beginner Tips (Esc to close)", TIPS)

    def open_file_prompt(self):
        self.file_picker = FileExplorer("open", self.workspace)

    def save_file_prompt(self):
        if self.current_file:
            self.save_file(self.current_file)
        else:
            self.file_picker = FileExplorer("save", self.workspace)

    def _handle_modal_result(self, modal_type, result):
        if modal_type == "Open File" and result:
            self.open_file(result)
        elif modal_type == "Save File" and result:
            self.save_file(result)
        elif modal_type == "Input" and result is not None:
            self._send_input(result)
        if modal_type == "Input" and result is None:
            self.pending_prompt = None

    def new_file(self):
        self.current_file = None
        self.editor.set_text("")
        self.console.clear()

    def open_file(self, path):
        if not os.path.exists(path):
            self.console.append(f"File not found: {path}", is_error=True)
            return
        with open(path, "r", encoding="utf-8") as f:
            self.editor.set_text(f.read())
        self.current_file = path
        self.console.append(f"Opened: {path}")

    def save_file(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.get_text().rstrip() + "\n")
            self.current_file = path
            self.console.append(f"Saved: {path}")
            if self.pending_build_target:
                target = self.pending_build_target
                self.pending_build_target = None
                self._start_build(target, path)
        except Exception as exc:
            self.console.append(str(exc), is_error=True)

    def show_examples(self):
        examples = self._list_examples()
        self.examples_popup = ExamplePicker(examples)

    def show_builds(self):
        self.build_picker = BuildPicker()

    def _list_examples(self):
        if not os.path.isdir(self.examples_dir):
            return []
        return sorted([name for name in os.listdir(self.examples_dir) if name.endswith(".el")])

    def load_example(self, name):
        path = os.path.join(self.examples_dir, name)
        self.open_file(path)

    def run_example(self, name):
        path = os.path.join(self.examples_dir, name)
        if os.path.exists(path):
            self.open_file(path)
            self.run_code()

    def build_package_target(self, target):
        if self.build_thread and self.build_thread.is_alive():
            self.console.append("Build already running.", is_error=True)
            return
        if not self.current_file:
            self.pending_build_target = target
            self.save_file_prompt()
            return
        self._start_build(target, self.current_file)

    def _start_build(self, target, source_file):
        output_dir = os.path.join(self.workspace, "dist")
        app_name = os.path.splitext(os.path.basename(source_file))[0]
        os.makedirs(output_dir, exist_ok=True)
        log_name = f"build_{app_name}.log"
        self.build_log_path = os.path.join(output_dir, log_name)
        with open(self.build_log_path, "w", encoding="utf-8") as f:
            f.write(f"EasyLang build log for {app_name}\n")
            f.write(f"Target: {target}\n")
        self.console.append(f"Building {target} for {app_name}...")
        self.console.append(f"Build log: {self.build_log_path}")

        def worker():
            build_package(target, source_file, app_name, output_dir, self._build_log)

        self.build_thread = threading.Thread(target=worker, daemon=True)
        self.build_thread.start()

    def _build_log(self, message, is_error=False):
        if self.build_log_path:
            try:
                with open(self.build_log_path, "a", encoding="utf-8") as f:
                    prefix = "ERROR: " if is_error else ""
                    f.write(prefix + message + "\n")
            except Exception:
                pass
        self.output_queue.put((message, is_error))

    def run_code(self):
        if self.process and self.process.poll() is None:
            self.console.append("Program is already running.", is_error=True)
            return
        self.console.clear()

        temp_path = self.current_file
        if not temp_path:
            temp_path = os.path.join(self.workspace, ".__easylang_tmp__.el")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(self.editor.get_text())

        self._start_subprocess(temp_path)

    def _start_subprocess(self, path):
        self.console.append("Running...")
        cmd = [
            sys.executable,
            "-c",
            (
                "import sys, os;"
                f"sys.path.insert(0, r'{self.workspace}');"
                "from interpreter.interpreter import run_file_with_errors;"
                "run_file_with_errors(sys.argv[1])"
            ),
            path,
        ]
        env = os.environ.copy()
        env["EASYLANG_INPUT_MODE"] = "marker"
        self.process = subprocess.Popen(
            cmd,
            cwd=self.workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        self._start_reader_thread()

    def _start_reader_thread(self):
        def reader():
            for line in self.process.stdout:
                line = line.rstrip("\n")
                if line.startswith("__EASY_INPUT__"):
                    prompt = line[len("__EASY_INPUT__"):].strip()
                    self.prompt_queue.put(prompt)
                else:
                    is_error = line.startswith("Line ")
                    self.output_queue.put((line, is_error))
            self.output_queue.put(("Program finished.", False))
        threading.Thread(target=reader, daemon=True).start()

    def _drain_output(self):
        while not self.output_queue.empty():
            line, is_error = self.output_queue.get_nowait()
            self.console.append(line, is_error=is_error)

        if self.pending_prompt is None and not self.prompt_queue.empty():
            self.pending_prompt = self.prompt_queue.get_nowait()
            self.modal = ModalInput("Input", self.pending_prompt, "")

    def _send_input(self, text):
        if self.process and self.process.poll() is None and self.process.stdin:
            try:
                self.process.stdin.write(text + "\n")
                self.process.stdin.flush()
                self.console.append(f"> {text}")
            except Exception:
                self.console.append("Failed to send input.", is_error=True)
        self.pending_prompt = None

    def stop_code(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            time.sleep(0.1)
            if self.process.poll() is None:
                self.process.kill()
            self.console.append("Program stopped.")


if __name__ == "__main__":
    EasyLangIDE().run()
