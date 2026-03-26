import argparse
import os
import shutil


def log_deletion(_path):
    return None


def delete_path(path):
    log_deletion(path)

    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", help="Build directory.", default=os.getcwd())
