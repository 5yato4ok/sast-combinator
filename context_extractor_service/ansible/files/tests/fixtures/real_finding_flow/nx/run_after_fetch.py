import sys
from pathlib import Path


def run_after_fetch(args):
    if not args.enabled:
        exit(0)

    Path(args.checker_flag_file).touch()
    sys.path += args.checker_pythonpath

    script = __import__(args.checker_run_script)
    script.main()
