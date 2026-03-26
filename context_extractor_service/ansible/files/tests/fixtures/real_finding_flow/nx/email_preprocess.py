import logging
from pathlib import Path


def generate_file(source_file: Path, target_file: Path, transformer):
    text = open(source_file).read()
    if transformer:
        text = transformer.transform(text) + '\n'

    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, 'w', encoding="utf-8", newline='\n') as f:
        f.write(text)


def process_file(source_file: Path, target_file: Path, css_file: Path):
    logging.info(f"Generating html email template from {source_file} with css {css_file}")
