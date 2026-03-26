import os
import re


def main(scss_file):
    with open(scss_file) as f:
        return re.search(r"brand_core_value", f.read())


project_root = "."
FILE_PATH = "skins/{skin}/palette.scss"
colors = {}
for skin in ("dark", "light"):
    colors[skin] = main(os.path.join(project_root, FILE_PATH.format(skin=f"{skin}")))
