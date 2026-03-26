from argparse import ArgumentParser
from zipfile import ZipFile


DGST_SHA256_PREFIX = "signature,digest,sha256,base64"


def signature_string(prefix, signature):
    return prefix + ":" + signature


def signature_string_from_file(prefix, file):
    with open(file) as f:
        return prefix + ":" + f.read()


def main():
    parser = ArgumentParser()
    parser.add_argument("zip_file", help="Zip file to modify.")
    parser.add_argument("--dgst-sha256", type=str, help="Digest SHA256 signature in base64 format.")
    parser.add_argument("--dgst-sha256-file", type=str)
