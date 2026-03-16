from typing import Callable, Optional

from .parser import Parser, EasyLangError
from .runtime import Runtime, StopExecution


class EasyLangInterpreter:
    def run_source(self, source: str, output_callback: Optional[Callable[[str], None]] = None, stop_event=None):
        parser = Parser()
        program = parser.parse(source)
        runtime = Runtime(output_callback=output_callback, stop_event=stop_event)
        runtime.execute(program)

    def run_file(self, path: str, output_callback: Optional[Callable[[str], None]] = None, stop_event=None):
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        self.run_source(source, output_callback=output_callback, stop_event=stop_event)


def run_source_with_errors(source: str, output_callback: Optional[Callable[[str], None]] = None, stop_event=None):
    interpreter = EasyLangInterpreter()
    try:
        interpreter.run_source(source, output_callback=output_callback, stop_event=stop_event)
    except EasyLangError as e:
        if output_callback:
            output_callback(e.friendly())
        else:
            print(e.friendly())
    except StopExecution:
        if output_callback:
            output_callback("Program stopped.")
        else:
            print("Program stopped.")


def run_file_with_errors(path: str, output_callback: Optional[Callable[[str], None]] = None, stop_event=None):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    run_source_with_errors(source, output_callback=output_callback, stop_event=stop_event)
