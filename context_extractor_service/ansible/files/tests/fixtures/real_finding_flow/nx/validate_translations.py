import argparse
import logging
import xml.etree.ElementTree as ET


def validate_xml(root, path):
    return root, path


def validate_file(path):
    tree = ET.parse(path)
    root = tree.getroot()
    return validate_xml(root, path)


def main():
    parser = argparse.ArgumentParser()
    return parser
