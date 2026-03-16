import argparse
import os

from ide.ide import EasyLangIDE


def main():
    parser = argparse.ArgumentParser(description="EasyLang - beginner-friendly language and Pygame IDE")
    parser.add_argument("file", nargs="?", help="Open an .el file in the IDE")
    args = parser.parse_args()

    initial_file = None
    if args.file:
        if os.path.exists(args.file):
            initial_file = args.file
        else:
            print(f"File not found: {args.file}")
            return

    EasyLangIDE(initial_file=initial_file).run()


if __name__ == "__main__":
    main()
