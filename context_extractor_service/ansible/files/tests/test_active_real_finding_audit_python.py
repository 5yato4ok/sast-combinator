from _active_real_finding_audit_helpers import *
def test_active_finding_python_script_invocation_should_keep_argument_and_command_context(monkeypatch, tmp_path):
    run_after_fetch_path = "build_utils/python/run_after_fetch.py"
    run_after_fetch_source = """\
from pathlib import Path
import argparse
import sys


def main():
    parser = argparse.ArgumentParser()
    args, _ = parser.parse_known_args()
    Path(args.checker_flag_file).touch()
    sys.path += args.checker_pythonpath
    script = __import__(args.checker_run_script)
    script.main()
"""
    tracker_path = "cloud/ams/utils/tracker_evaluator/scripts/run.py"
    tracker_source = """\
import os
import subprocess

SERVER_CONFIG_PATH = "server.json"


def main(args, benchmark, datasets_folder, output_folder, detector_engine_path, tracker_evaluator_path, tracker):
    serverConfigPath = os.path.join(args.nx_source_folder, SERVER_CONFIG_PATH)
    cmd =[
            tracker_evaluator_path,
            "-d",
            datasets_folder,
            "-o",
            output_folder,
            f"--benchmark={benchmark}",
            f"--server_config={serverConfigPath}",
            f"--detector_engine={detector_engine_path}",
            f"--tracker={tracker}",
    ]
    subprocess.run(cmd)
"""
    ninja_path = "open/build_utils/ninja/ninja_tool.py"
    ninja_source = """\
import subprocess


def run_commands(script_data):
    for command in script_data.commands_to_run:
        print(f"Running {command}...")
        subprocess.call(command)
"""
    qml_path = "open/build_utils/qmldeploy.py"
    qml_source = """\
import subprocess


class Deploy:
    def invoke_qmlimportscanner(self, qml_root):
        command = [self.scanner_path, "-rootPath", qml_root, "-importPath", self.import_path]
        process = subprocess.Popen(command, stdout=subprocess.PIPE)
        return process
"""
    copy_lib_path = "open/build_utils/linux/copy_system_library.py"
    copy_lib_source = """\
import subprocess


def get_lib_dirs_from_compiler(compiler, compiler_flags=""):
    lines = subprocess.check_output(
        "{} --print-search-dirs {}".format(compiler, compiler_flags),
        universal_newlines=True,
        shell=True).split()
    return lines
"""
    _write_source_tree(tmp_path, run_after_fetch_path, run_after_fetch_source)
    _write_source_tree(tmp_path, tracker_path, tracker_source)
    _write_source_tree(tmp_path, ninja_path, ninja_source)
    _write_source_tree(tmp_path, qml_path, qml_source)
    _write_source_tree(tmp_path, copy_lib_path, copy_lib_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    run_after_fetch_identifiers = mcp_server.find_identifiers("9ce90895", run_after_fetch_path, 11)
    run_after_fetch_trace = mcp_server.trace_identifier_backward("9ce90895", run_after_fetch_path, 11, "args")
    tracker_extracted = mcp_server.extract_function("9ce90895", tracker_path, 9)
    tracker_identifiers = mcp_server.find_identifiers("9ce90895", tracker_path, 9)
    tracker_trace = mcp_server.trace_identifier_backward("9ce90895", tracker_path, 9, "serverConfigPath")
    copy_lib_identifiers = mcp_server.find_identifiers("9ce90895", copy_lib_path, 5)
    copy_lib_trace = mcp_server.trace_identifier_backward("9ce90895", copy_lib_path, 5, "compiler")
    ninja_identifiers = mcp_server.find_identifiers("9ce90895", ninja_path, 7)
    ninja_trace = mcp_server.trace_identifier_backward("9ce90895", ninja_path, 7, "command")
    qml_identifiers = mcp_server.find_identifiers("9ce90895", qml_path, 6)
    qml_trace = mcp_server.trace_identifier_backward("9ce90895", qml_path, 6, "command")

    assert run_after_fetch_identifiers["reads"] == ["__import__", "args", "checker_run_script"]
    assert run_after_fetch_identifiers["writes"] == ["script"]
    assert run_after_fetch_identifiers["language"] == "python"
    assert run_after_fetch_trace == [
        {"line": 8, "code": "args, _ = parser.parse_known_args()", "writes": ["args"], "reads": ["parse_known_args", "parser"]},
        {"line": 7, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert tracker_extracted["meta"]["code_on_line"] == "    cmd =["
    assert {
        "benchmark",
        "datasets_folder",
        "detector_engine_path",
        "output_folder",
        "serverConfigPath",
        "tracker",
        "tracker_evaluator_path",
    } <= set(tracker_identifiers["reads"])
    assert tracker_identifiers["writes"] == ["cmd"]
    assert tracker_trace == [
        {
            "line": 8,
            "code": "serverConfigPath = os.path.join(args.nx_source_folder, SERVER_CONFIG_PATH)",
            "writes": ["serverConfigPath"],
            "reads": ["SERVER_CONFIG_PATH", "args", "join", "nx_source_folder", "os", "path"],
        }
    ]
    assert copy_lib_identifiers["reads"] == [
        "check_output",
        "compiler",
        "compiler_flags",
        "format",
        "shell",
        "split",
        "subprocess",
        "universal_newlines",
    ]
    assert copy_lib_identifiers["writes"] == ["lines"]
    assert copy_lib_trace == []
    assert ninja_identifiers["reads"] == ["call", "command", "subprocess"]
    assert ninja_identifiers["writes"] == []
    assert ninja_trace == [
        {
            "line": 5,
            "code": "for command in script_data.commands_to_run:",
            "writes": ["command"],
            "reads": ["call", "commands_to_run", "print", "script_data", "subprocess"],
        }
    ]
    assert qml_identifiers["reads"] == ["import_path", "qml_root", "scanner_path", "self"]
    assert qml_identifiers["writes"] == ["command"]
    assert qml_trace == [
        {
            "line": 6,
            "code": 'command = [self.scanner_path, "-rootPath", qml_root, "-importPath", self.import_path]',
            "writes": ["command"],
            "reads": ["import_path", "qml_root", "scanner_path", "self"],
        }
    ]




def test_active_finding_python_pinger_should_keep_executable_and_command_context(monkeypatch, tmp_path):
    file_path = "vms/vms_benchmark/lib/vms_benchmark/pinger.py"
    source = """\
import os
import platform
import subprocess
from pathlib import Path


class Pinger:
    def __init__(self, host):
        if platform.system() == 'Windows':
            _ping_exe = Path(os.environ['WINDIR']).joinpath("System32", "ping.exe")
            self._ping_command = [_ping_exe.as_posix(), "-n", "1", host]

    def ping(self) -> bool:
        completed_proc = subprocess.run(
            self._ping_command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        return completed_proc.returncode == 0
"""
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    init_extracted = mcp_server.extract_function("9ce90895", file_path, 11)
    init_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 11)
    init_trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 11, "_ping_exe")
    ping_extracted = mcp_server.extract_function("9ce90895", file_path, 14)
    ping_identifiers = mcp_server.find_identifiers("9ce90895", file_path, 14)
    ping_trace = mcp_server.trace_identifier_backward("9ce90895", file_path, 14, "self")

    assert init_extracted["meta"]["code_on_line"] == '            self._ping_command = [_ping_exe.as_posix(), "-n", "1", host]'
    assert init_identifiers["reads"] == ["_ping_exe", "as_posix", "host", "self"]
    assert init_identifiers["writes"] == ["_ping_command"]
    assert init_identifiers["language"] == "python"
    assert init_trace == [
        {
            "line": 10,
            "code": '_ping_exe = Path(os.environ[\'WINDIR\']).joinpath("System32", "ping.exe")',
            "writes": ["_ping_exe"],
            "reads": ["Path", "environ", "joinpath", "os"],
        }
    ]
    assert ping_extracted["meta"]["code_on_line"] == "        completed_proc = subprocess.run("
    assert ping_identifiers["reads"] == ["DEVNULL", "_ping_command", "run", "self", "stderr", "stdout", "subprocess"]
    assert ping_identifiers["writes"] == ["completed_proc"]
    assert ping_identifiers["language"] == "python"
    assert ping_trace == []




def test_active_finding_python_file_parsing_helpers_should_keep_path_and_xml_context(monkeypatch, tmp_path):
    deps_path = "open/vms/distribution/common/scripts/generate_deb_dependencies.py"
    deps_source = """\
import argparse
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = parser.parse_args()
    with open(args.file, "r") as file:
        deps = yaml.load(file, yaml.Loader)
    return deps
"""
    validate_path = "build_utils/translation/validate_translations.py"
    validate_source = """\
import argparse
import xml.etree.ElementTree as ET


def validate_xml(root, path):
    return True


def validate_file(path):
    tree = ET.parse(path)
    root = tree.getroot()
    return validate_xml(root, path)
"""
    merge_wxl_path = "open/vms/distribution/wix/scripts/merge_wxl_files.py"
    merge_wxl_source = """\
from pathlib import Path
import xml.etree.ElementTree as ElementTree


class WxlFile():
    def __init__(self, path):
        self.tree = ElementTree.parse(path)
        self.root = self.tree.getroot()
"""
    team_path = "open/build_utils/macos/team.py"
    team_source = """\
import os
import subprocess
import xml.etree.ElementTree as ET


def parse():
    output = subprocess.check_output(
        ["/usr/libexec/PlistBuddy", "-x", "-c", "print IDEProvisioningTeamByIdentifier",
         f"{os.environ['HOME']}/Library/Preferences/com.apple.dt.Xcode.plist"])
    for e in ET.fromstring(output).findall('dict/array/dict'):
        return e
"""
    axis_path = "vms/server/mediaserver/update_db_scripts/axis_compare.py"
    axis_source = """\
import requests, re, os
import xml.etree.ElementTree as ET

api_key = "apikey example"
headers={"authorization": api_key}
axis_base_url = "https://www.axis.com/api/pia/v2/items"
parameters = ""
axis_url = axis_base_url + parameters
get_list = requests.get(axis_url, headers = headers).json()
f1_path = os.path.abspath(os.getcwd() + "/axis.xml")
tree = ET.parse(f1_path)
"""
    av_path = "vms/server/mediaserver/update_db_scripts/av_compare.py"
    av_source = """\
import re
from xml.dom import minidom

f1_path = "/tmp/av.xml"
arecont_xml = minidom.parse(f1_path)
arecont_xml_models = arecont_xml.getElementsByTagName('resource')
for model in arecont_xml_models:
    match = re.match('\\d+\\w+', model.attributes['name'].value)
"""
    _write_source_tree(tmp_path, deps_path, deps_source)
    _write_source_tree(tmp_path, validate_path, validate_source)
    _write_source_tree(tmp_path, merge_wxl_path, merge_wxl_source)
    _write_source_tree(tmp_path, team_path, team_source)
    _write_source_tree(tmp_path, axis_path, axis_source)
    _write_source_tree(tmp_path, av_path, av_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    deps_identifiers = mcp_server.find_identifiers("9ce90895", deps_path, 10)
    deps_trace = mcp_server.trace_identifier_backward("9ce90895", deps_path, 10, "args")
    validate_identifiers = mcp_server.find_identifiers("9ce90895", validate_path, 10)
    validate_trace = mcp_server.trace_identifier_backward("9ce90895", validate_path, 10, "path")
    merge_identifiers = mcp_server.find_identifiers("9ce90895", merge_wxl_path, 7)
    merge_trace = mcp_server.trace_identifier_backward("9ce90895", merge_wxl_path, 7, "path")
    team_identifiers = mcp_server.find_identifiers("9ce90895", team_path, 10)
    team_trace = mcp_server.trace_identifier_backward("9ce90895", team_path, 10, "output")
    axis_identifiers = mcp_server.find_identifiers("9ce90895", axis_path, 5)
    axis_trace = mcp_server.trace_identifier_backward("9ce90895", axis_path, 5, "api_key")
    av_identifiers = mcp_server.find_identifiers("9ce90895", av_path, 5)
    av_trace = mcp_server.trace_identifier_backward("9ce90895", av_path, 5, "f1_path")

    assert deps_identifiers["reads"] == ["Loader", "file", "load", "yaml"]
    assert deps_identifiers["writes"] == ["deps"]
    assert deps_trace == [
        {"line": 8, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
        {"line": 6, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert validate_identifiers["reads"] == ["ET", "parse", "path"]
    assert validate_identifiers["writes"] == ["tree"]
    assert validate_trace == []
    assert merge_identifiers["reads"] == ["ElementTree", "parse", "path", "self"]
    assert merge_identifiers["writes"] == ["tree"]
    assert merge_trace == []
    assert team_identifiers["reads"] == ["ET", "findall", "fromstring", "output"]
    assert team_identifiers["writes"] == ["e"]
    assert team_trace == [
        {
            "line": 7,
            "code": "output = subprocess.check_output(",
            "writes": ["output"],
            "reads": ["check_output", "environ", "os", "subprocess"],
        }
    ]
    assert axis_identifiers["reads"] == ["api_key"]
    assert axis_identifiers["writes"] == ["headers"]
    assert axis_trace == [{"line": 4, "code": 'api_key = "apikey example"', "writes": ["api_key"], "reads": []}]
    assert av_identifiers["reads"] == ["f1_path", "minidom", "parse"]
    assert av_identifiers["writes"] == ["arecont_xml"]
    assert av_trace == [{"line": 4, "code": 'f1_path = "/tmp/av.xml"', "writes": ["f1_path"], "reads": []}]




def test_active_finding_python_hash_and_template_helpers_should_keep_content_and_tempfile_context(monkeypatch, tmp_path):
    cache_path = "cloud/storage/analytics_vectorizer/vectorizer/clip_model_cache.py"
    cache_source = """\
import hashlib
import typing
import numpy as np
import PIL.Image


class Cache:
    @staticmethod
    def get_content_hash(content: typing.Union[bytes, str]) -> str:
        if isinstance(content, str):
            return hashlib.md5(content.encode()).hexdigest()
        elif isinstance(content, PIL.Image.Image) or isinstance(content, np.ndarray):
            return hashlib.md5(content.tobytes()).hexdigest()
        else:
            return hashlib.md5(content).hexdigest()
"""
    utils_path = "cloud/ams/model/src/nx/train/utils.py"
    utils_source = """\
import tempfile
import jinja2


def build(datasetRoot):
    with tempfile.NamedTemporaryFile(suffix='.yaml') as data_file:
        with open(data_file.name, mode='w') as f:
            data_conf_str = jinja2.Template(\"\"\"\npath: {{datasetRoot}}\n\"\"\").render({'datasetRoot': datasetRoot})
            f.write(data_conf_str)
"""
    yolov11_path = "cloud/ams/model/src/nx/utils/train/nx_yolov11_train.py"
    yolov11_source = """\
import tempfile
import jinja2

NX_YOLO_MODEL_CONFIG = "model: {{scale}}"


def run(parser, logger):
    args = parser.parse_args()
    with tempfile.NamedTemporaryFile(suffix='.yaml') as modelFile, \\
        tempfile.NamedTemporaryFile(suffix='.yaml') as dataFile:
        with open(modelFile.name, mode='w') as f:
            f.write(jinja2.Template(NX_YOLO_MODEL_CONFIG).render({'scale': args.scale}))
        with open(dataFile.name, mode='w') as f:
            dataConfStr = jinja2.Template(\"\"\"\npath: {{datasetRoot}}\nscale: {{scale}}\n\"\"\").render({'datasetRoot': args.dataset_root, 'scale': args.scale})
"""
    _write_source_tree(tmp_path, cache_path, cache_source)
    _write_source_tree(tmp_path, utils_path, utils_source)
    _write_source_tree(tmp_path, yolov11_path, yolov11_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    cache_str_identifiers = mcp_server.find_identifiers("9ce90895", cache_path, 11)
    cache_img_identifiers = mcp_server.find_identifiers("9ce90895", cache_path, 13)
    cache_bytes_identifiers = mcp_server.find_identifiers("9ce90895", cache_path, 15)
    utils_identifiers = mcp_server.find_identifiers("9ce90895", utils_path, 7)
    utils_trace = mcp_server.trace_identifier_backward("9ce90895", utils_path, 7, "data_file")
    model_identifiers = mcp_server.find_identifiers("9ce90895", yolov11_path, 12)
    model_trace = mcp_server.trace_identifier_backward("9ce90895", yolov11_path, 12, "f")
    data_identifiers = mcp_server.find_identifiers("9ce90895", yolov11_path, 14)
    data_trace = mcp_server.trace_identifier_backward("9ce90895", yolov11_path, 14, "dataFile")

    assert cache_str_identifiers["reads"] == ["content", "encode", "hashlib", "hexdigest", "md5"]
    assert cache_str_identifiers["writes"] == []
    assert cache_img_identifiers["reads"] == ["content", "hashlib", "hexdigest", "md5", "tobytes"]
    assert cache_img_identifiers["writes"] == []
    assert cache_bytes_identifiers["reads"] == ["content", "hashlib", "hexdigest", "md5"]
    assert cache_bytes_identifiers["writes"] == []
    assert utils_identifiers["reads"] == ["Template", "data_conf_str", "data_file", "datasetRoot", "jinja2", "mode", "name", "open", "render", "write"]
    assert utils_identifiers["writes"] == ["f"]
    assert utils_trace == [
        {
            "line": 6,
            "code": "with tempfile.NamedTemporaryFile(suffix='.yaml') as data_file:",
            "writes": ["data_file"],
            "reads": ["NamedTemporaryFile", "Template", "data_conf_str", "datasetRoot", "f", "jinja2", "mode", "name", "open", "render", "suffix", "tempfile", "write"],
        }
    ]
    assert model_identifiers["reads"] == ["NX_YOLO_MODEL_CONFIG", "Template", "args", "f", "jinja2", "render", "scale", "write"]
    assert model_identifiers["writes"] == []
    assert model_trace == [
        {
            "line": 11,
            "code": "with open(modelFile.name, mode='w') as f:",
            "writes": ["f"],
            "reads": ["NX_YOLO_MODEL_CONFIG", "Template", "args", "jinja2", "mode", "modelFile", "name", "open", "render", "scale", "write"],
        },
        {
            "line": 9,
            "code": "with tempfile.NamedTemporaryFile(suffix='.yaml') as modelFile, \\",
            "writes": ["modelFile"],
            "reads": ["NX_YOLO_MODEL_CONFIG", "NamedTemporaryFile", "Template", "args", "dataConfStr", "dataset_root", "f", "jinja2", "mode", "name", "open", "render", "scale", "suffix", "tempfile", "write"],
        },
        {"line": 8, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]
    assert data_identifiers["reads"] == ["Template", "args", "dataset_root", "jinja2", "render", "scale"]
    assert data_identifiers["writes"] == ["dataConfStr"]
    assert data_trace == [
        {
            "line": 9,
            "code": "with tempfile.NamedTemporaryFile(suffix='.yaml') as modelFile, \\",
            "writes": ["dataFile"],
            "reads": ["NX_YOLO_MODEL_CONFIG", "NamedTemporaryFile", "Template", "args", "dataConfStr", "dataset_root", "f", "jinja2", "mode", "name", "open", "render", "scale", "suffix", "tempfile", "write"],
        },
        {"line": 8, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]




def test_active_finding_python_file_io_and_fallback_paths_should_keep_open_context(monkeypatch, tmp_path):
    monitoring_path = "cloud/infra/monitoring/monitoring_simple/simple.py"
    monitoring_source = """\
import requests
from contextlib import contextmanager
from requests.auth import HTTPDigestAuth

ADMIN_PASS = "admin"
DEFAULT_LOGIN = "admin"


@contextmanager
def run(mediaserver_ip):
    r = requests_retry_session().post('http://{}:7001/api/setupLocalSystem'.format(mediaserver_ip),
                                      params={'systemName': 'monitoring',
                                              'password': ADMIN_PASS},
                                      auth=requests.auth.HTTPDigestAuth(DEFAULT_LOGIN, 'admin'))
    yield r
"""
    embed_path = "build_utils/code_signing/embed_zip_signature.py"
    embed_source = """\
def signature_string_from_file(prefix, file):
    with open(file) as f:
        return prefix + \":\" + f.read()
"""
    preprocess_path = "build_utils/email_templates/preprocess.py"
    preprocess_source = """\
from pathlib import Path


def generate_file(source_file: Path, target_file: Path, transformer):
    text = open(source_file).read()
    if transformer:
        text = transformer.transform(text) + '\\n'
"""
    after_fetch_path = "build_utils/python/run_after_fetch.py"
    after_fetch_source = """\
from pathlib import Path
import re


def have_to_run_script(sources_dir, script_name):
    git_root_path = Path(sources_dir).joinpath('.git')
    with open(git_root_path) as f:
        git_root_path_file_content = f.readline().rstrip()
    git_info_path = Path(sources_dir).joinpath('git_info.txt')
    with open(git_info_path) as f:
        content = f.readlines()
        for line in content:
            match = re.match(r'^fetchTimestampS=(?P<fetch_timestamp>[\\d\\.,]+)', line)
            if match:
                return float(match['fetch_timestamp'].replace(',', '.'))
"""
    replace_path = "build_utils/replace_in_file.py"
    replace_source = """\
import argparse


def main(parser):
    args = parser.parse_args()
    replacement_string = bytes(args.replacement_string)
    for file_name in args.files:
        with open(file_name, 'rb') as f:
            data = f.read()
"""
    deploy_path = "cloud/ams/analytics_server/deploy/build_analytics_model.py"
    deploy_source = """\
import json


def prepare_json_config(config_json: str, output_dir: str) -> dict:
    with open(config_json, 'r') as f:
        config_data = json.load(f)
    return config_data
"""
    _write_source_tree(tmp_path, monitoring_path, monitoring_source)
    _write_source_tree(tmp_path, embed_path, embed_source)
    _write_source_tree(tmp_path, preprocess_path, preprocess_source)
    _write_source_tree(tmp_path, after_fetch_path, after_fetch_source)
    _write_source_tree(tmp_path, replace_path, replace_source)
    _write_source_tree(tmp_path, deploy_path, deploy_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    monitoring_classification = mcp_server.classify_file("9ce90895", monitoring_path)
    monitoring_identifiers = mcp_server.find_identifiers("9ce90895", monitoring_path, 12)
    monitoring_decorators = mcp_server.find_decorators("9ce90895", monitoring_path, 12)
    embed_identifiers = mcp_server.find_identifiers("9ce90895", embed_path, 2)
    preprocess_identifiers = mcp_server.find_identifiers("9ce90895", preprocess_path, 5)
    after_fetch_git_identifiers = mcp_server.find_identifiers("9ce90895", after_fetch_path, 8)
    after_fetch_git_trace = mcp_server.trace_identifier_backward("9ce90895", after_fetch_path, 8, "git_root_path")
    after_fetch_info_identifiers = mcp_server.find_identifiers("9ce90895", after_fetch_path, 10)
    after_fetch_info_trace = mcp_server.trace_identifier_backward("9ce90895", after_fetch_path, 10, "git_info_path")
    replace_identifiers = mcp_server.find_identifiers("9ce90895", replace_path, 7)
    replace_trace = mcp_server.trace_identifier_backward("9ce90895", replace_path, 7, "file_name")
    deploy_classification = mcp_server.classify_file("9ce90895", deploy_path)
    deploy_identifiers = mcp_server.find_identifiers("9ce90895", deploy_path, 5)

    assert monitoring_classification["type"] == "config"
    assert monitoring_decorators == ["@contextmanager"]
    assert monitoring_identifiers["reads"] == [
        "ADMIN_PASS",
        "DEFAULT_LOGIN",
        "HTTPDigestAuth",
        "auth",
        "format",
        "mediaserver_ip",
        "params",
        "post",
        "requests",
        "requests_retry_session",
    ]
    assert monitoring_identifiers["writes"] == ["r"]
    assert embed_identifiers["reads"] == ["file", "open", "prefix", "read"]
    assert embed_identifiers["writes"] == ["f"]
    assert preprocess_identifiers["reads"] == ["open", "read", "source_file"]
    assert preprocess_identifiers["writes"] == ["text"]
    assert after_fetch_git_identifiers["reads"] == ["f", "readline", "rstrip"]
    assert after_fetch_git_identifiers["writes"] == ["git_root_path_file_content"]
    assert after_fetch_git_trace == [
        {"line": 6, "code": "git_root_path = Path(sources_dir).joinpath('.git')", "writes": ["git_root_path"], "reads": ["Path", "joinpath", "sources_dir"]}
    ]
    assert after_fetch_info_identifiers["reads"] == ["content", "float", "git_info_path", "line", "match", "open", "re", "readlines", "replace"]
    assert after_fetch_info_identifiers["writes"] == ["f"]
    assert after_fetch_info_trace == [
        {"line": 9, "code": "git_info_path = Path(sources_dir).joinpath('git_info.txt')", "writes": ["git_info_path"], "reads": ["Path", "joinpath", "sources_dir"]}
    ]
    assert replace_identifiers["reads"] == ["args", "data", "f", "files", "open", "read"]
    assert replace_identifiers["writes"] == ["file_name"]
    assert replace_trace == [
        {"line": 7, "code": "for file_name in args.files:", "writes": ["file_name"], "reads": ["args", "data", "f", "files", "open", "read"]},
        {"line": 5, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]
    assert deploy_classification["type"] == "config"
    assert deploy_identifiers["reads"] == ["config_data", "config_json", "json", "load", "open"]
    assert deploy_identifiers["writes"] == ["f"]




def test_active_finding_python_reader_and_loader_helpers_should_keep_argument_context(monkeypatch, tmp_path):
    tao_path = "cloud/ams/model/src/nx/utils/dataset/converters/tao_to_labelme.py"
    tao_source = """\
import pathlib
import json


def load(images_root, annotations_file, logger, AnnFile):
    files = {}
    for path in pathlib.Path(images_root).rglob('*.jpg'):
        files[str(path)] = AnnFile(image_file=path.relative_to(images_root), segments=[])
        logger.debug("Found image file: " + str(path))
    with open(annotations_file, 'r') as ann_file:
        file_content = ann_file.read()
        annotations_obj = json.loads(file_content)
    return annotations_obj
"""
    profiler_path = "cloud/ams/utils/trtexec/profiler.py"
    profiler_source = """\
import json


def main(args, features, hasNames, mergeHeaders, allFeatures):
    count = args.gp and not hasNames(features)
    profile = None
    reference = None
    with open(args.name) as f:
        profile = json.load(f)
        profileCount = profile[0][\"count\"]
        profile = profile[1:]
    if args.reference:
        with open(args.reference) as f:
            reference = json.load(f)
            referenceCount = reference[0][\"count\"]
            reference = reference[1:]
        allFeatures = mergeHeaders(allFeatures)
"""
    tracer_path = "cloud/ams/utils/trtexec/tracer.py"
    tracer_source = """\
import json


def main(args, pu, allMetrics):
    metrics = args.metrics.split(\",\")
    count = args.gp and (len(metrics) == 1)
    if not args.no_header:
        pu.printHeader(allMetrics, metrics, args.gp, count)
    with open(args.name) as f:
        trace = json.load(f)
    return trace
"""
    _write_source_tree(tmp_path, tao_path, tao_source)
    _write_source_tree(tmp_path, profiler_path, profiler_source)
    _write_source_tree(tmp_path, tracer_path, tracer_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    tao_identifiers = mcp_server.find_identifiers("9ce90895", tao_path, 10)
    tao_trace = mcp_server.trace_identifier_backward("9ce90895", tao_path, 10, "annotations_file")
    profile_identifiers = mcp_server.find_identifiers("9ce90895", profiler_path, 8)
    profile_trace = mcp_server.trace_identifier_backward("9ce90895", profiler_path, 8, "args")
    reference_identifiers = mcp_server.find_identifiers("9ce90895", profiler_path, 13)
    reference_trace = mcp_server.trace_identifier_backward("9ce90895", profiler_path, 13, "args")
    tracer_identifiers = mcp_server.find_identifiers("9ce90895", tracer_path, 9)
    tracer_trace = mcp_server.trace_identifier_backward("9ce90895", tracer_path, 9, "args")

    assert tao_identifiers["reads"] == ["annotations_file", "annotations_obj", "file_content", "json", "loads", "open", "read"]
    assert tao_identifiers["writes"] == ["ann_file"]
    assert tao_trace == []
    assert profile_identifiers["reads"] == ["args", "json", "load", "name", "open", "profile", "profileCount"]
    assert profile_identifiers["writes"] == ["f"]
    assert profile_trace == []
    assert reference_identifiers["reads"] == ["args", "json", "load", "open", "reference", "referenceCount"]
    assert reference_identifiers["writes"] == ["f"]
    assert reference_trace == []
    assert tracer_identifiers["reads"] == ["args", "json", "load", "name", "open", "trace"]
    assert tracer_identifiers["writes"] == ["f"]
    assert tracer_trace == []




def test_active_finding_python_conversion_and_writeback_helpers_should_keep_path_context(monkeypatch, tmp_path):
    json_to_cmake_path = "open/build_utils/json_to_cmake.py"
    json_to_cmake_source = """\
import json


def parse_dict(data, prefix=None):
    return data


def convert_json_file_to_cmake_file(json_file_name, cmake_file_name, prefix=None):
    with open(json_file_name, encoding=\"utf-8\") as json_file:
        variables = parse_dict(json.load(json_file), prefix=prefix)
    with open(cmake_file_name, \"w\", encoding=\"utf-8\") as cmake_file:
        return variables
"""
    replace_qt_path = "open/build_utils/msvc/replace_conan_qt_path.py"
    replace_qt_source = """\
import json
import os
from pathlib import Path


def patch(file, qtdir):
    binaries_dir = (Path(qtdir) / 'bin').as_posix()
    with open(file, 'r', encoding='utf-8-sig') as source:
        json_root = json.load(source)
    return json_root, binaries_dir
"""
    yaml2json_path = "open/build_utils/yaml2json.py"
    yaml2json_source = """\
import argparse
import json
import yaml


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    with open(args.input, 'r') as input:
        with open(args.output, 'w') as output:
            json.dump(yaml.safe_load(input), output, indent=4)
"""
    generate_path = "open/vms/server/plugins/analytics/stub_analytics_plugin/object_streamer_files/generate.py"
    generate_source = """\
import json
from pathlib import Path


def load_config(config_file: Path):
    with open(config_file, encoding='UTF-8') as config:
        return json.load(config)
"""
    preprocess_path = "build_utils/email_templates/preprocess.py"
    preprocess_source = """\
from pathlib import Path


def generate_file(target_file: Path, text):
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, 'w', encoding=\"utf-8\", newline='\\n') as f:
        f.write(text)
"""
    labelme_path = "cloud/ams/model/src/nx/utils/dataset/converters/labelme_to_yolo.py"
    labelme_source = """\
import pathlib


def save(json_file, segments):
    result_yolo_file = str(json_file.parent / pathlib.Path(json_file.stem + \".txt\"))
    with open(result_yolo_file, 'w', encoding='utf-8') as f:
        for segment in segments:
            f.write(str(segment))
"""
    dumpwts_path = "cloud/ams/utils/trtexec/src/dumpTFWts.py"
    dumpwts_source = """\
def main(opt):
    outputbase = opt.output
    outputFileName = outputbase + \".wts2\"
    outputFile = open(outputFileName, \"w\")
    return outputFile
"""
    _write_source_tree(tmp_path, json_to_cmake_path, json_to_cmake_source)
    _write_source_tree(tmp_path, replace_qt_path, replace_qt_source)
    _write_source_tree(tmp_path, yaml2json_path, yaml2json_source)
    _write_source_tree(tmp_path, generate_path, generate_source)
    _write_source_tree(tmp_path, preprocess_path, preprocess_source)
    _write_source_tree(tmp_path, labelme_path, labelme_source)
    _write_source_tree(tmp_path, dumpwts_path, dumpwts_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    json_to_cmake_identifiers = mcp_server.find_identifiers("9ce90895", json_to_cmake_path, 9)
    json_to_cmake_trace = mcp_server.trace_identifier_backward("9ce90895", json_to_cmake_path, 9, "json_file_name")
    replace_qt_identifiers = mcp_server.find_identifiers("9ce90895", replace_qt_path, 8)
    replace_qt_trace = mcp_server.trace_identifier_backward("9ce90895", replace_qt_path, 8, "file")
    yaml2json_identifiers = mcp_server.find_identifiers("9ce90895", yaml2json_path, 9)
    yaml2json_trace = mcp_server.trace_identifier_backward("9ce90895", yaml2json_path, 9, "args")
    generate_identifiers = mcp_server.find_identifiers("9ce90895", generate_path, 6)
    generate_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 6, "config_file")
    preprocess_identifiers = mcp_server.find_identifiers("9ce90895", preprocess_path, 6)
    preprocess_trace = mcp_server.trace_identifier_backward("9ce90895", preprocess_path, 6, "target_file")
    labelme_identifiers = mcp_server.find_identifiers("9ce90895", labelme_path, 6)
    labelme_trace = mcp_server.trace_identifier_backward("9ce90895", labelme_path, 6, "result_yolo_file")
    dumpwts_identifiers = mcp_server.find_identifiers("9ce90895", dumpwts_path, 4)
    dumpwts_trace = mcp_server.trace_identifier_backward("9ce90895", dumpwts_path, 4, "outputFileName")

    assert json_to_cmake_identifiers["reads"] == ["encoding", "json", "json_file_name", "load", "open", "parse_dict", "prefix", "variables"]
    assert json_to_cmake_identifiers["writes"] == ["json_file"]
    assert json_to_cmake_trace == []
    assert replace_qt_identifiers["reads"] == ["encoding", "file", "json", "json_root", "load", "open"]
    assert replace_qt_identifiers["writes"] == ["source"]
    assert replace_qt_trace == []
    assert yaml2json_identifiers["reads"] == ["args", "dump", "indent", "json", "open", "output", "safe_load", "yaml"]
    assert yaml2json_identifiers["writes"] == ["input"]
    assert yaml2json_trace == [
        {"line": 8, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
        {"line": 7, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert generate_identifiers["reads"] == ["config_file", "encoding", "json", "load", "open"]
    assert generate_identifiers["writes"] == ["config"]
    assert generate_trace == []
    assert preprocess_identifiers["reads"] == ["encoding", "newline", "open", "target_file", "text", "write"]
    assert preprocess_identifiers["writes"] == ["f"]
    assert preprocess_trace == []
    assert labelme_identifiers["reads"] == ["encoding", "open", "result_yolo_file", "segment", "segments", "str", "write"]
    assert labelme_identifiers["writes"] == ["f"]
    assert labelme_trace == [{"line": 5, "code": 'result_yolo_file = str(json_file.parent / pathlib.Path(json_file.stem + ".txt"))', "writes": ["result_yolo_file"], "reads": ["Path", "json_file", "parent", "pathlib", "stem", "str"]}]
    assert dumpwts_identifiers["reads"] == ["open", "outputFileName"]
    assert dumpwts_identifiers["writes"] == ["outputFile"]
    assert dumpwts_trace == [
        {"line": 3, "code": 'outputFileName = outputbase + ".wts2"', "writes": ["outputFileName"], "reads": ["outputbase"]},
        {"line": 2, "code": "outputbase = opt.output", "writes": ["outputbase"], "reads": ["opt", "output"]},
    ]




def test_active_finding_python_ninja_and_misc_open_helpers_should_keep_file_binding_context(monkeypatch, tmp_path):
    ninja_path = "open/build_utils/ninja/ninja_tool.py"
    ninja_source = """\
from pathlib import Path

PERSISTENT_KNOWN_FILES_FILE_NAME = "known.txt"


def update_persistent_known_files_file(build_dir, directories):
    persistent_known_files = build_dir / PERSISTENT_KNOWN_FILES_FILE_NAME
    if persistent_known_files.is_file():
        with open(persistent_known_files) as f:
            current_files = [Path(name) for name in f.read().splitlines()]
    else:
        current_files = []
    with open(persistent_known_files, "w") as f:
        f.writelines([])


def generate_list_of_targets_affected_by_listed_files(build_dir, changed_files_list_file_name, affected_targets_list_file_name):
    with open(build_dir / changed_files_list_file_name) as f:
        files = f.read().splitlines()
    try:
        with open(build_dir / affected_targets_list_file_name) as f:
            old_targets = set([l.rstrip() for l in f.readlines()])
    except:
        old_targets = None
    return files, old_targets
"""
    remove_docs_path = "open/build_utils/remove_proprietary_docs.py"
    remove_docs_source = """\
import argparse


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    with open(args.input, "rb") as f:
        data = f.read().decode('utf-8')
    return data
"""
    signtool_path = "open/build_utils/signtool/signtool.py"
    signtool_source = """\
import yaml


def sign_file(config_file):
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config
"""
    signtool_client_path = "build_utils/code_signing/signtool_client.py"
    signtool_client_source = """\
import argparse


def main(client):
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    client.load_arguments(args)
"""
    replace_path = "build_utils/replace_in_file.py"
    replace_source = """\
import argparse


def main(parser):
    args = parser.parse_args()
    replacement_string = bytes(args.replacement_string)
    for file_name in args.files:
        data = b\"payload\"
        with open(file_name, "wb") as f:
            f.write(data)
"""
    _write_source_tree(tmp_path, ninja_path, ninja_source)
    _write_source_tree(tmp_path, remove_docs_path, remove_docs_source)
    _write_source_tree(tmp_path, signtool_path, signtool_source)
    _write_source_tree(tmp_path, signtool_client_path, signtool_client_source)
    _write_source_tree(tmp_path, replace_path, replace_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    ninja_known_identifiers = mcp_server.find_identifiers("9ce90895", ninja_path, 8)
    ninja_known_trace = mcp_server.trace_identifier_backward("9ce90895", ninja_path, 8, "persistent_known_files")
    ninja_changed_identifiers = mcp_server.find_identifiers("9ce90895", ninja_path, 17)
    ninja_changed_trace = mcp_server.trace_identifier_backward("9ce90895", ninja_path, 17, "changed_files_list_file_name")
    ninja_affected_identifiers = mcp_server.find_identifiers("9ce90895", ninja_path, 20)
    ninja_affected_trace = mcp_server.trace_identifier_backward("9ce90895", ninja_path, 20, "affected_targets_list_file_name")
    remove_docs_identifiers = mcp_server.find_identifiers("9ce90895", remove_docs_path, 7)
    remove_docs_trace = mcp_server.trace_identifier_backward("9ce90895", remove_docs_path, 7, "args")
    signtool_identifiers = mcp_server.find_identifiers("9ce90895", signtool_path, 5)
    signtool_trace = mcp_server.trace_identifier_backward("9ce90895", signtool_path, 5, "config_file")
    signtool_client_identifiers = mcp_server.find_identifiers("9ce90895", signtool_client_path, 6)
    signtool_client_trace = mcp_server.trace_identifier_backward("9ce90895", signtool_client_path, 6, "args")
    replace_identifiers = mcp_server.find_identifiers("9ce90895", replace_path, 8)
    replace_trace = mcp_server.trace_identifier_backward("9ce90895", replace_path, 8, "file_name")

    assert ninja_known_identifiers["reads"] == ["Path", "is_file", "name", "open", "persistent_known_files", "read", "splitlines"]
    assert ninja_known_identifiers["writes"] == ["current_files", "f"]
    assert ninja_known_trace == [{"line": 7, "code": "persistent_known_files = build_dir / PERSISTENT_KNOWN_FILES_FILE_NAME", "writes": ["persistent_known_files"], "reads": ["PERSISTENT_KNOWN_FILES_FILE_NAME", "build_dir"]}]
    assert ninja_changed_identifiers["reads"] == ["f", "files", "l", "old_targets", "open", "read", "readlines", "rstrip", "set", "splitlines"]
    assert ninja_changed_identifiers["writes"] == ["affected_targets_list_file_name", "build_dir", "changed_files_list_file_name", "generate_list_of_targets_affected_by_listed_files"]
    assert ninja_changed_trace == []
    assert ninja_affected_identifiers["reads"] == []
    assert ninja_affected_identifiers["writes"] == []
    assert ninja_affected_trace == []
    assert remove_docs_identifiers["reads"] == ["args", "data", "decode", "input", "open", "read"]
    assert remove_docs_identifiers["writes"] == ["f"]
    assert remove_docs_trace == [
        {"line": 6, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
        {"line": 5, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert signtool_identifiers["reads"] == ["config", "config_file", "open", "safe_load", "yaml"]
    assert signtool_identifiers["writes"] == ["f"]
    assert signtool_trace == []
    assert signtool_client_identifiers["reads"] == ["parse_args", "parser"]
    assert signtool_client_identifiers["writes"] == ["args"]
    assert signtool_client_trace == [
        {"line": 6, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
        {"line": 5, "code": "parser = argparse.ArgumentParser()", "writes": ["parser"], "reads": ["ArgumentParser", "argparse"]},
    ]
    assert replace_identifiers["reads"] == []
    assert replace_identifiers["writes"] == ["data"]
    assert replace_trace == [
        {"line": 7, "code": "for file_name in args.files:", "writes": ["file_name"], "reads": ["args", "data", "f", "files", "open", "write"]},
        {"line": 5, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]




def test_active_finding_python_benchmark_and_manifest_writes_should_keep_context_bindings(monkeypatch, tmp_path):
    benchmark_path = "vms/vms_benchmark/bin/main.py"
    benchmark_source = """\
def _rtsp_perf_frames(output_file_path, report):
    if output_file_path:
        output_file = open(output_file_path, "w")
        report(f"log to {output_file_path!r}")
    else:
        output_file = None
    return output_file


def run(stream_reader_context_manager, ini):
    archive_read_pos_ms_utc = 0
    stream_reader_context = None
    with stream_reader_context_manager as stream_reader_context:
        stream_reader_process = stream_reader_context[0]
        rtsp_perf_frames = _rtsp_perf_frames(
            ini["stdout"],
            ini["rtspPerfLinesOutputFile"])
    return rtsp_perf_frames
"""
    extract_system_path = "build_utils/customization/extract_system_data.py"
    extract_system_source = """\
import json


def main(parser):
    args = parser.parse_args()
    input = json.load(args.source)
    systemData = input['desktop']['systemData']
    json.dump(systemData, args.destination)
"""
    generate_path = "open/vms/server/plugins/analytics/stub_analytics_plugin/object_streamer_files/generate.py"
    generate_source = """\
import json


def main(args, generation_manager, ManifestEncoder, StreamEntryEncoder):
    manifest = generation_manager.generate_manifest()
    with open(args.manifest_file, 'w', encoding='UTF-8') as manifest_file:
        json.dump(manifest, manifest_file, cls=ManifestEncoder, indent=4)
        manifest_file.write(\"\\n\")

    stream = generation_manager.generate_stream()
    with open(args.stream_file, 'w', encoding='UTF-8') as stream_file:
        indent = None if args.compressed_stream else 4
        separators = (\",\", \":\") if args.compressed_stream else (\",\", \": \")
        json.dump(stream, stream_file, cls=StreamEntryEncoder, indent=indent, separators=separators)
        stream_file.write(\"\\n\")
"""
    _write_source_tree(tmp_path, benchmark_path, benchmark_source)
    _write_source_tree(tmp_path, extract_system_path, extract_system_source)
    _write_source_tree(tmp_path, generate_path, generate_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    benchmark_output_identifiers = mcp_server.find_identifiers("9ce90895", benchmark_path, 3)
    benchmark_output_trace = mcp_server.trace_identifier_backward("9ce90895", benchmark_path, 3, "output_file_path")
    benchmark_stream_identifiers = mcp_server.find_identifiers("9ce90895", benchmark_path, 14)
    benchmark_stream_trace = mcp_server.trace_identifier_backward("9ce90895", benchmark_path, 14, "stream_reader_context")
    extract_system_identifiers = mcp_server.find_identifiers("9ce90895", extract_system_path, 7)
    extract_system_trace = mcp_server.trace_identifier_backward("9ce90895", extract_system_path, 7, "systemData")
    manifest_identifiers = mcp_server.find_identifiers("9ce90895", generate_path, 6)
    manifest_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 6, "args")
    stream_identifiers = mcp_server.find_identifiers("9ce90895", generate_path, 11)
    stream_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 11, "args")
    manifest_file_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 7, "manifest_file")
    stream_file_trace = mcp_server.trace_identifier_backward("9ce90895", generate_path, 14, "stream_file")

    assert benchmark_output_identifiers["reads"] == ["open", "output_file_path"]
    assert benchmark_output_identifiers["writes"] == ["output_file"]
    assert benchmark_output_trace == []
    assert benchmark_stream_identifiers["reads"] == ["stream_reader_context"]
    assert benchmark_stream_identifiers["writes"] == ["stream_reader_process"]
    assert benchmark_stream_trace == [
        {"line": 13, "code": "with stream_reader_context_manager as stream_reader_context:", "writes": ["stream_reader_context"], "reads": ["_rtsp_perf_frames", "ini", "rtsp_perf_frames", "stream_reader_context_manager", "stream_reader_process"]},
    ]
    assert extract_system_identifiers["reads"] == ["input"]
    assert extract_system_identifiers["writes"] == ["systemData"]
    assert extract_system_trace == [
        {"line": 7, "code": "systemData = input['desktop']['systemData']", "writes": ["systemData"], "reads": ["input"]},
        {"line": 6, "code": "input = json.load(args.source)", "writes": ["input"], "reads": ["args", "json", "load", "source"]},
        {"line": 5, "code": "args = parser.parse_args()", "writes": ["args"], "reads": ["parse_args", "parser"]},
    ]
    assert manifest_identifiers["reads"] == ["ManifestEncoder", "args", "cls", "dump", "encoding", "indent", "json", "manifest", "open", "write"]
    assert manifest_identifiers["writes"] == ["manifest_file"]
    assert manifest_trace == []
    assert stream_identifiers["reads"] == ["StreamEntryEncoder", "args", "cls", "compressed_stream", "dump", "encoding", "indent", "json", "open", "separators", "stream", "write"]
    assert stream_identifiers["writes"] == ["stream_file"]
    assert stream_trace == []
    assert manifest_file_trace == [
        {"line": 6, "code": "with open(args.manifest_file, 'w', encoding='UTF-8') as manifest_file:", "writes": ["manifest_file"], "reads": ["ManifestEncoder", "args", "cls", "dump", "encoding", "indent", "json", "manifest", "open", "write"]},
        {"line": 5, "code": "manifest = generation_manager.generate_manifest()", "writes": ["manifest"], "reads": ["generate_manifest", "generation_manager"]},
    ]
    assert stream_file_trace == [
        {"line": 11, "code": "with open(args.stream_file, 'w', encoding='UTF-8') as stream_file:", "writes": ["stream_file"], "reads": ["StreamEntryEncoder", "args", "cls", "compressed_stream", "dump", "encoding", "indent", "json", "open", "separators", "stream", "write"]},
        {"line": 10, "code": "stream = generation_manager.generate_stream()", "writes": ["stream"], "reads": ["generate_stream", "generation_manager"]},
    ]




def test_active_finding_python_submodule_and_file_mutation_helpers_should_keep_binding_context(monkeypatch, tmp_path):
    nx_submodule_path = "build_utils/nx_submodule/nx_submodule.py"
    nx_submodule_source = """\
import argparse
from pathlib import Path

import nx_submodule_lib


def _create_arg_parser():
    return argparse.ArgumentParser()


def _get_repo_url(args):
    return args.subrepo_url


def main():
    parser = _create_arg_parser()
    args = parser.parse_args()
    args.git_ref = args.git_ref or args.commit_sha

    if args.action == "create":
        nx_submodule_lib.create_submodule(
            dir=args.submodule_local_dir.resolve(),
            repo_url=_get_repo_url(args),
            repo_dir=args.subrepo_dir,
            git_ref=args.git_ref)
    else:
        if args.submodule_local_dir:
            nx_submodule_lib.update_submodule(
                dir=args.submodule_local_dir.resolve(),
                git_ref=args.git_ref,
                fetch_url=args.fetch_url)
        else:
            repo_url = _get_repo_url(args)
            main_repo_dir = (args.main_repo_dir or Path.cwd()).resolve()
            nx_submodule_lib.find_and_update_submodules(
                main_repo_dir=main_repo_dir,
                git_ref=args.git_ref,
                repo_url=repo_url,
                fetch_url=args.fetch_url)
"""
    clear_cmake_path = "build_utils/python/clear_cmake_build.py"
    clear_cmake_source = """\
import os
import shutil


def delete_path(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
"""
    merge_sync_path = "open/build_utils/merge_and_sync_directories.py"
    merge_sync_source = """\
import os
import shutil
import sys


def merge_and_sync_directories(output_dir):
    unneeded_files = ["old.txt"]
    unneeded_dirs = ["stale/subdir"]

    for f in unneeded_files:
        print(f"Removing {f}", file=sys.stderr)
        os.remove(f)

    for d in reversed(unneeded_dirs):
        print(f"Removing {d}", file=sys.stderr)
        if os.path.isdir(d):
            shutil.rmtree(d)
"""
    pack_path = "open/build_utils/customization/pack.py"
    pack_source = """\
import argparse
import logging
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    if args.log:
        Path(args.log).parent.mkdir(exist_ok=True, parents=True)
        logging.basicConfig(filename=args.log, filemode="w")
"""
    converter_path = "cloud/ams/utils/pytorch_to_onnx_converter/nx_ultralytics_to_onnx_converter.py"
    converter_source = """\
import argparse
import shutil

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    model = YOLO(args.input)
    f = model.export(format="onnx", batch=args.batch)
    shutil.move(f, args.output)
"""
    copy_lib_path = "open/build_utils/linux/copy_system_library.py"
    copy_lib_source = """\
import os
import shutil


def copy_library(file_name, target_dir):
    real_file = os.path.realpath(file_name)
    real_basename = os.path.basename(real_file)
    target_file_name = os.path.join(target_dir, real_basename)
    if os.path.exists(target_file_name):
        os.remove(target_file_name)
    shutil.copy2(real_file, target_file_name)
"""
    _write_source_tree(tmp_path, nx_submodule_path, nx_submodule_source)
    _write_source_tree(tmp_path, clear_cmake_path, clear_cmake_source)
    _write_source_tree(tmp_path, merge_sync_path, merge_sync_source)
    _write_source_tree(tmp_path, pack_path, pack_source)
    _write_source_tree(tmp_path, converter_path, converter_source)
    _write_source_tree(tmp_path, copy_lib_path, copy_lib_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    nx_classification = mcp_server.classify_file("9ce90895", nx_submodule_path)
    nx_create_identifiers = mcp_server.find_identifiers("9ce90895", nx_submodule_path, 19)
    nx_create_trace = mcp_server.trace_identifier_backward("9ce90895", nx_submodule_path, 19, "args")
    nx_update_identifiers = mcp_server.find_identifiers("9ce90895", nx_submodule_path, 25)
    nx_recurse_identifiers = mcp_server.find_identifiers("9ce90895", nx_submodule_path, 32)
    nx_recurse_trace = mcp_server.trace_identifier_backward("9ce90895", nx_submodule_path, 32, "main_repo_dir")
    clear_rmtree_identifiers = mcp_server.find_identifiers("9ce90895", clear_cmake_path, 6)
    clear_remove_identifiers = mcp_server.find_identifiers("9ce90895", clear_cmake_path, 8)
    clear_remove_trace = mcp_server.trace_identifier_backward("9ce90895", clear_cmake_path, 8, "path")
    merge_remove_identifiers = mcp_server.find_identifiers("9ce90895", merge_sync_path, 11)
    merge_remove_trace = mcp_server.trace_identifier_backward("9ce90895", merge_sync_path, 11, "f")
    merge_rmtree_identifiers = mcp_server.find_identifiers("9ce90895", merge_sync_path, 15)
    merge_rmtree_trace = mcp_server.trace_identifier_backward("9ce90895", merge_sync_path, 15, "d")
    pack_identifiers = mcp_server.find_identifiers("9ce90895", pack_path, 10)
    pack_trace = mcp_server.trace_identifier_backward("9ce90895", pack_path, 10, "args")
    converter_identifiers = mcp_server.find_identifiers("9ce90895", converter_path, 11)
    converter_trace = mcp_server.trace_identifier_backward("9ce90895", converter_path, 11, "args")
    copy_lib_identifiers = mcp_server.find_identifiers("9ce90895", copy_lib_path, 10)
    copy_lib_trace = mcp_server.trace_identifier_backward("9ce90895", copy_lib_path, 10, "real_file")

    assert nx_classification["type"] == "production"
    assert {"args", "create_submodule", "nx_submodule_lib", "repo_dir", "repo_url"} <= set(nx_create_identifiers["reads"])
    assert nx_create_identifiers["writes"] == ["args", "git_ref", "main_repo_dir", "parser", "repo_url"]
    assert nx_create_identifiers["language"] == "python"
    _assert_trace_codes(nx_create_trace, ["args = parser.parse_args()", "parser = _create_arg_parser()"])
    assert {"_get_repo_url", "args", "create_submodule", "dir", "git_ref", "nx_submodule_lib", "repo_dir", "repo_url", "resolve", "submodule_local_dir", "subrepo_dir"} <= set(
        nx_update_identifiers["reads"]
    )
    assert nx_update_identifiers["writes"] == []
    assert {"Path", "args", "cwd", "fetch_url", "find_and_update_submodules", "git_ref", "main_repo_dir", "nx_submodule_lib", "repo_url", "resolve"} <= set(
        nx_recurse_identifiers["reads"]
    )
    assert nx_recurse_identifiers["writes"] == ["main_repo_dir", "repo_url"]
    _assert_trace_codes(nx_recurse_trace, ["if args.submodule_local_dir:", "args.git_ref = args.git_ref or args.commit_sha", "args = parser.parse_args()"])
    assert clear_rmtree_identifiers == {"reads": ["isdir", "os", "path", "remove", "rmtree", "shutil"], "writes": [], "language": "python"}
    assert clear_remove_identifiers == {"reads": ["isdir", "os", "path", "remove", "rmtree", "shutil"], "writes": [], "language": "python"}
    assert clear_remove_trace == []
    assert merge_remove_identifiers == {"reads": ["f", "file", "print", "stderr", "sys"], "writes": [], "language": "python"}
    _assert_trace_codes(merge_remove_trace, ["for f in unneeded_files:"])
    assert merge_rmtree_identifiers == {"reads": ["d", "file", "print", "stderr", "sys"], "writes": [], "language": "python"}
    _assert_trace_codes(merge_rmtree_trace, ["for d in reversed(unneeded_dirs):", 'unneeded_dirs = ["stale/subdir"]'])
    assert pack_identifiers["reads"] == ["Path", "args", "exist_ok", "log", "mkdir", "parent", "parents"]
    assert pack_identifiers["writes"] == []
    _assert_trace_codes(pack_trace, ["args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert converter_identifiers["reads"] == ["args", "batch", "export", "format", "model"]
    assert converter_identifiers["writes"] == ["f"]
    _assert_trace_codes(converter_trace, ["args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert copy_lib_identifiers["reads"] == ["os", "remove", "target_file_name"]
    assert copy_lib_identifiers["writes"] == []
    _assert_trace_codes(copy_lib_trace, ["real_file = os.path.realpath(file_name)"])




def test_active_finding_python_copy_and_move_helpers_should_keep_path_bindings(monkeypatch, tmp_path):
    copy_lib_path = "open/build_utils/linux/copy_system_library.py"
    copy_lib_source = """\
import argparse
import os
import shutil
import sys


def find_library(lib, lib_dirs):
    return "/tmp/" + lib


def copy_library(file_name, target_dir, list_files=False):
    real_file = os.path.realpath(file_name)
    real_basename = os.path.basename(real_file)
    target_file_name = os.path.join(target_dir, real_basename)
    if os.path.exists(target_file_name):
        os.remove(target_file_name)
    shutil.copy2(real_file, target_file_name)


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    lib_dirs = []
    libs = []
    for lib in args.libs:
        file_name = find_library(lib, lib_dirs)
        libs.append(file_name)
    for lib in libs:
        copy_library(lib, args.dest_dir, list_files=args.list)
"""
    build_model_path = "cloud/ams/analytics_server/deploy/build_analytics_model.py"
    build_model_source = """\
import os
import shutil

QUANT_CALIB_FILE = "calib.cache"
TRT_CALIB_CACH_FILE_NAME = "tmp.cache"


def build_trt_model(**kwargs):
    return kwargs


def calculate_calib_file(dataset_path, output_dir):
    build_trt_model(output_dir=output_dir, calib_dataset=os.path.join(dataset_path, "images"))
    target_calib_file = os.path.join(output_dir, QUANT_CALIB_FILE)
    shutil.move(TRT_CALIB_CACH_FILE_NAME, target_calib_file)
"""
    yolov11_path = "cloud/ams/model/src/nx/utils/train/nx_yolov11_train.py"
    yolov11_source = """\
import argparse
import shutil


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    for attempt_i in range(args.train_attempts):
        try:
            shutil.move("runs/detect", "runs/attempt_" + str(attempt_i))
        except Exception:
            pass
"""
    pack_server_path = "cloud/ams/analytics_server/deploy/deprecated/pack_server.py"
    pack_server_source = """\
import argparse
import os
import shutil

TARGET_MODELS_FOLDER = "models"
TARGET_MODEL_NAME = "model.bin"
TARGET_MODEL_CONFIG_NAME = "config.json"


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    target_app_path = "/tmp/server"
    deploy_folder_path = "/tmp/deploy"
    target_lib_path = "/tmp/lib"
    shutil.copy(target_app_path, args.pkg_path)
    shutil.copy(os.path.join(deploy_folder_path, "config.json"), args.pkg_path)
    shutil.copy(os.path.join(deploy_folder_path, "entrypoint.sh"), args.pkg_path)
    target_model_folder_path = os.path.join(args.pkg_path, TARGET_MODELS_FOLDER)
    os.makedirs(target_model_folder_path, exist_ok=True)
    target_model_path = os.path.join(target_model_folder_path, TARGET_MODEL_NAME)
    if args.model_path != target_model_path:
        shutil.copy(args.model_path, target_model_path)
    if args.model_config:
        target_model_config_path = os.path.join(target_model_folder_path, TARGET_MODEL_CONFIG_NAME)
        if args.model_config != target_model_config_path:
            shutil.copy(args.model_config, target_model_config_path)
"""
    pack_benchmark_path = "cloud/ams/analytics_server/deploy/pack_benchmark.py"
    pack_benchmark_source = """\
import argparse
import os
import shutil

TARGET_MODELS_FOLDER = "models"
TARGET_MODEL_NAME = "model.bin"
TARGET_MODEL_CONFIG_NAME = "config.json"


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    target_app_path = "/tmp/bench"
    shutil.copy(target_app_path, args.pkg_path)
    shutil.copy(args.file_path, args.pkg_path)
    target_model_folder_path = os.path.join(args.pkg_path, TARGET_MODELS_FOLDER)
    os.makedirs(target_model_folder_path)
    target_model_path = os.path.join(target_model_folder_path, TARGET_MODEL_NAME)
    shutil.copy(args.model_path, target_model_path)
    if args.model_config:
        target_model_config_path = os.path.join(target_model_folder_path, TARGET_MODEL_CONFIG_NAME)
        shutil.copy(args.model_config, target_model_config_path)
"""
    adapt_images_path = "cloud/ams/model/src/nx/utils/dataset/adapters/adapt_images.py"
    adapt_images_source = """\
import pathlib
import shutil


def copy_non_same(src_path, dst_path):
    if src_path != dst_path:
        shutil.copy(src_path, dst_path)


def save_image_as_is(ann_file, target_dir):
    copy_non_same(
        ann_file.parent / (ann_file.stem + ".jpg"),
        pathlib.Path(target_dir) / str(ann_file.stem + ".jpg")
    )
    copy_non_same(
        ann_file.parent / (ann_file.stem + ".json"),
        pathlib.Path(target_dir) / str(ann_file.stem + ".json")
    )


def save_mosaic_candidate(used_files, target_dir):
    result_file = used_files[0].name
    copy_non_same(
        used_files[0].parent / (used_files[0].name + ".jpg"),
        pathlib.Path(target_dir) / str(result_file + ".jpg"),
    )
    copy_non_same(
        used_files[0].parent / (used_files[0].name + ".json"),
        pathlib.Path(target_dir) / str(result_file + ".json"),
    )
"""
    macdeployqt_path = "open/vms/distribution/dmg/client/resources.in/macdeployqt.py"
    macdeployqt_source = """\
import os
import shutil
from os.path import join


def main(app_path, bindir, helpdir):
    resources_dir = "{app_path}/Contents/Resources".format(app_path=app_path)
    help_dir = "{}/help".format(resources_dir)
    shutil.copytree(helpdir, help_dir)
    shutil.copy(join(bindir, "launcher.version"), resources_dir)
"""
    filter_images_path = "cloud/ams/model/src/nx/utils/dataset/adapters/filter_images.py"
    filter_images_source = """\
import pathlib
import shutil


def copy_filtered(file_path, target_dir, copied_files):
    ann_file = file_path.parent / (file_path.stem + ".json")
    if ann_file not in copied_files:
        copied_files[ann_file] = True
        shutil.copy(
            ann_file,
            str(target_dir / (file_path.stem + ".json"))
        )
        shutil.copy(
            str(file_path.parent / (file_path.stem + ".jpg")),
            str(target_dir / (file_path.stem + ".jpg"))
        )
"""
    _write_source_tree(tmp_path, copy_lib_path, copy_lib_source)
    _write_source_tree(tmp_path, build_model_path, build_model_source)
    _write_source_tree(tmp_path, yolov11_path, yolov11_source)
    _write_source_tree(tmp_path, pack_server_path, pack_server_source)
    _write_source_tree(tmp_path, pack_benchmark_path, pack_benchmark_source)
    _write_source_tree(tmp_path, adapt_images_path, adapt_images_source)
    _write_source_tree(tmp_path, macdeployqt_path, macdeployqt_source)
    _write_source_tree(tmp_path, filter_images_path, filter_images_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    copy_lib_identifiers = mcp_server.find_identifiers("9ce90895", copy_lib_path, 24)
    copy_lib_trace = mcp_server.trace_identifier_backward("9ce90895", copy_lib_path, 24, "lib")
    build_model_classification = mcp_server.classify_file("9ce90895", build_model_path)
    build_model_identifiers = mcp_server.find_identifiers("9ce90895", build_model_path, 14)
    build_model_trace = mcp_server.trace_identifier_backward("9ce90895", build_model_path, 14, "target_calib_file")
    yolov11_identifiers = mcp_server.find_identifiers("9ce90895", yolov11_path, 9)
    yolov11_trace = mcp_server.trace_identifier_backward("9ce90895", yolov11_path, 9, "attempt_i")
    pack_server_identifiers = mcp_server.find_identifiers("9ce90895", pack_server_path, 15)
    pack_server_trace = mcp_server.trace_identifier_backward("9ce90895", pack_server_path, 15, "args")
    pack_benchmark_identifiers = mcp_server.find_identifiers("9ce90895", pack_benchmark_path, 14)
    pack_benchmark_trace = mcp_server.trace_identifier_backward("9ce90895", pack_benchmark_path, 14, "args")
    adapt_copy_identifiers = mcp_server.find_identifiers("9ce90895", adapt_images_path, 7)
    adapt_copy_trace = mcp_server.trace_identifier_backward("9ce90895", adapt_images_path, 7, "src_path")
    adapt_save_identifiers = mcp_server.find_identifiers("9ce90895", adapt_images_path, 11)
    adapt_save_trace = mcp_server.trace_identifier_backward("9ce90895", adapt_images_path, 11, "ann_file")
    adapt_mosaic_identifiers = mcp_server.find_identifiers("9ce90895", adapt_images_path, 22)
    adapt_mosaic_trace = mcp_server.trace_identifier_backward("9ce90895", adapt_images_path, 22, "result_file")
    macdeployqt_identifiers = mcp_server.find_identifiers("9ce90895", macdeployqt_path, 10)
    macdeployqt_trace = mcp_server.trace_identifier_backward("9ce90895", macdeployqt_path, 10, "help_dir")
    filter_images_identifiers = mcp_server.find_identifiers("9ce90895", filter_images_path, 9)
    filter_images_trace = mcp_server.trace_identifier_backward("9ce90895", filter_images_path, 9, "ann_file")

    assert copy_lib_identifiers == {"reads": [], "writes": ["libs"], "language": "python"}
    assert copy_lib_trace == []
    assert build_model_classification["type"] == "config"
    assert build_model_identifiers == {
        "reads": ["QUANT_CALIB_FILE", "join", "os", "output_dir", "path"],
        "writes": ["target_calib_file"],
        "language": "python",
    }
    _assert_trace_codes(build_model_trace, ["target_calib_file = os.path.join(output_dir, QUANT_CALIB_FILE)"])
    assert yolov11_identifiers["reads"] == []
    assert yolov11_identifiers["writes"] == []
    _assert_trace_codes(yolov11_trace, ["for attempt_i in range(args.train_attempts):", "args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert pack_server_identifiers["reads"] == []
    assert pack_server_identifiers["writes"] == ["target_lib_path"]
    _assert_trace_codes(pack_server_trace, ["args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert {"args", "copy", "pkg_path", "shutil", "target_app_path"} <= set(pack_benchmark_identifiers["reads"])
    assert pack_benchmark_identifiers["writes"] == []
    _assert_trace_codes(pack_benchmark_trace, ["args = parser.parse_args()", "parser = argparse.ArgumentParser()"])
    assert adapt_copy_identifiers == {"reads": ["copy", "dst_path", "shutil", "src_path"], "writes": [], "language": "python"}
    assert adapt_copy_trace == []
    assert {"Path", "ann_file", "copy_non_same", "parent", "pathlib", "stem", "str", "target_dir"} <= set(adapt_save_identifiers["reads"])
    assert adapt_save_identifiers["writes"] == []
    assert adapt_save_trace == []
    assert adapt_mosaic_identifiers == {"reads": ["name", "used_files"], "writes": ["result_file"], "language": "python"}
    _assert_trace_codes(adapt_mosaic_trace, ["result_file = used_files[0].name"])
    assert macdeployqt_identifiers == {"reads": ["bindir", "copy", "join", "resources_dir", "shutil"], "writes": [], "language": "python"}
    _assert_trace_codes(
        macdeployqt_trace,
        ['help_dir = "{}/help".format(resources_dir)', 'resources_dir = "{app_path}/Contents/Resources".format(app_path=app_path)'],
    )
    assert filter_images_identifiers == {
        "reads": ["ann_file", "copy", "file_path", "shutil", "stem", "str", "target_dir"],
        "writes": [],
        "language": "python",
    }
    _assert_trace_codes(filter_images_trace, ["copied_files[ann_file] = True"])




def test_active_finding_python_converter_and_bundle_helpers_should_keep_copyfile_and_hierarchy_context(monkeypatch, tmp_path):
    crowdhuman_path = "cloud/ams/model/src/nx/utils/dataset/converters/crowdhuman_to_labelme.py"
    crowdhuman_source = """\
import pathlib
import shutil


def save_image(image_file, target_root):
    shutil.copyfile(image_file, pathlib.Path(target_root) / image_file.name)
"""
    mot_path = "cloud/ams/model/src/nx/utils/dataset/converters/mot_to_labelme.py"
    mot_source = """\
import pathlib
import shutil


def save_frame(frame_id, image_file, target_seq_path):
    shutil.copyfile(image_file, target_seq_path / (str(frame_id) + ".jpg"))
"""
    voc_path = "cloud/ams/model/src/nx/utils/dataset/converters/voc_to_labelme.py"
    voc_source = """\
import pathlib
import shutil


def save_voc_image(image_file, target_root):
    shutil.copyfile(image_file, pathlib.Path(target_root) / (image_file.name))
"""
    captcha_path = "cloud/ams/model/src/nx/utils/dataset/converters/filter_google_captcha_set.py"
    captcha_source = """\
import pathlib
import shutil


def save_captcha_image(image_file, target_root):
    shutil.copyfile(image_file, pathlib.Path(target_root) / (image_file.name))
"""
    tao_path = "cloud/ams/model/src/nx/utils/dataset/converters/tao_to_labelme.py"
    tao_source = """\
import os
import pathlib
import shutil


class AnnFile:
    def __init__(self, image_file):
        self.image_file = image_file


def save_tao_image(image_file, ann_file, target_root):
    os.makedirs(str(pathlib.Path(target_root) / ann_file.image_file.parent), exist_ok=True)
    shutil.copyfile(image_file, pathlib.Path(target_root) / ann_file.image_file)
"""
    signtool_path = "open/build_utils/signtool/signtool.py"
    signtool_source = """\
import shutil


def sign(in_file_path, out_file_path):
    if out_file_path and out_file_path != in_file_path:
        shutil.copyfile(in_file_path, out_file_path)
        file_to_sign = out_file_path
    else:
        file_to_sign = in_file_path
    return file_to_sign
"""
    client_macdeployqt_path = "open/vms/distribution/dmg/client/resources.in/macdeployqt.py"
    client_macdeployqt_source = """\
import shutil
from os.path import join


def prepare(build_dir, binary, sbindir, tbindir, applauncher_binary):
    shutil.copyfile(join(sbindir, "@client.binary.name@"), binary)
    shutil.copyfile(join(sbindir, "@applauncher.binary.name@"), applauncher_binary)
    shutil.copyfile(join(build_dir, "qt.conf"), join(tbindir, "qt.conf"))
"""
    server_macdeployqt_path = "vms/distribution/dmg/mediaserver/resources.in/macdeployqt.py"
    server_macdeployqt_source = """\
import shutil
from os.path import join


def prepare(build_dir, binary, sbindir, tbindir):
    shutil.copyfile(join(sbindir, "@server.binary.name@"), binary)
    shutil.copyfile(join(build_dir, "qt.conf"), join(tbindir, "qt.conf"))
"""
    open_images_path = "cloud/ams/model/src/nx/utils/dataset/converters/open_images_parts_to_labelme.py"
    open_images_source = """\
import json
import pathlib


def enrich_class_mapping_with_hierarchy(hierarchy_file, class_mapping):
    file_content = pathlib.Path(hierarchy_file).read_text()
    hierarchy_json = json.loads(file_content)
    result_class_mapping = dict(class_mapping)
    return hierarchy_json, result_class_mapping


def allocate_target_dir(target_root, result_w, result_h, object_image):
    STEP_H = 40
    STEP_W = 40
    round_h = int(result_h / STEP_H) * STEP_H
    round_w = int(result_w / STEP_W) * STEP_W
    target_dir = pathlib.Path(target_root) / (str(round_w) + "x" + str(round_h))
    return target_dir, object_image
"""
    _write_source_tree(tmp_path, crowdhuman_path, crowdhuman_source)
    _write_source_tree(tmp_path, mot_path, mot_source)
    _write_source_tree(tmp_path, voc_path, voc_source)
    _write_source_tree(tmp_path, captcha_path, captcha_source)
    _write_source_tree(tmp_path, tao_path, tao_source)
    _write_source_tree(tmp_path, signtool_path, signtool_source)
    _write_source_tree(tmp_path, client_macdeployqt_path, client_macdeployqt_source)
    _write_source_tree(tmp_path, server_macdeployqt_path, server_macdeployqt_source)
    _write_source_tree(tmp_path, open_images_path, open_images_source)
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    crowdhuman_identifiers = mcp_server.find_identifiers("9ce90895", crowdhuman_path, 5)
    crowdhuman_trace = mcp_server.trace_identifier_backward("9ce90895", crowdhuman_path, 5, "image_file")
    mot_identifiers = mcp_server.find_identifiers("9ce90895", mot_path, 6)
    mot_trace = mcp_server.trace_identifier_backward("9ce90895", mot_path, 6, "image_file")
    voc_identifiers = mcp_server.find_identifiers("9ce90895", voc_path, 5)
    voc_trace = mcp_server.trace_identifier_backward("9ce90895", voc_path, 5, "image_file")
    captcha_identifiers = mcp_server.find_identifiers("9ce90895", captcha_path, 5)
    captcha_trace = mcp_server.trace_identifier_backward("9ce90895", captcha_path, 5, "image_file")
    tao_identifiers = mcp_server.find_identifiers("9ce90895", tao_path, 12)
    tao_trace = mcp_server.trace_identifier_backward("9ce90895", tao_path, 12, "image_file")
    signtool_identifiers = mcp_server.find_identifiers("9ce90895", signtool_path, 5)
    signtool_trace = mcp_server.trace_identifier_backward("9ce90895", signtool_path, 5, "out_file_path")
    client_mac_identifiers = mcp_server.find_identifiers("9ce90895", client_macdeployqt_path, 6)
    client_mac_trace = mcp_server.trace_identifier_backward("9ce90895", client_macdeployqt_path, 6, "binary")
    server_mac_identifiers = mcp_server.find_identifiers("9ce90895", server_macdeployqt_path, 6)
    server_mac_trace = mcp_server.trace_identifier_backward("9ce90895", server_macdeployqt_path, 6, "binary")
    open_images_read_identifiers = mcp_server.find_identifiers("9ce90895", open_images_path, 6)
    open_images_read_trace = mcp_server.trace_identifier_backward("9ce90895", open_images_path, 6, "hierarchy_file")
    open_images_target_identifiers = mcp_server.find_identifiers("9ce90895", open_images_path, 14)
    open_images_target_trace = mcp_server.trace_identifier_backward("9ce90895", open_images_path, 14, "target_dir")

    assert crowdhuman_identifiers == {"reads": ["Path", "copyfile", "name", "pathlib", "shutil"], "writes": ["image_file", "save_image", "target_root"], "language": "python"}
    assert crowdhuman_trace == []
    assert mot_identifiers == {
        "reads": ["copyfile", "frame_id", "image_file", "shutil", "str", "target_seq_path"],
        "writes": [],
        "language": "python",
    }
    assert mot_trace == []
    assert voc_identifiers == {"reads": ["Path", "copyfile", "name", "pathlib", "shutil"], "writes": ["image_file", "save_voc_image", "target_root"], "language": "python"}
    assert voc_trace == []
    assert captcha_identifiers == {"reads": ["Path", "copyfile", "name", "pathlib", "shutil"], "writes": ["image_file", "save_captcha_image", "target_root"], "language": "python"}
    assert captcha_trace == []
    assert {"Path", "ann_file", "exist_ok", "image_file", "makedirs", "os", "parent", "pathlib", "str", "target_root"} == set(tao_identifiers["reads"])
    assert tao_identifiers["writes"] == []
    assert tao_identifiers["language"] == "python"
    assert tao_trace == []
    assert signtool_identifiers == {
        "reads": ["copyfile", "in_file_path", "out_file_path", "shutil"],
        "writes": ["file_to_sign"],
        "language": "python",
    }
    assert signtool_trace == []
    assert client_mac_identifiers == {
        "reads": ["binary", "copyfile", "join", "sbindir", "shutil"],
        "writes": [],
        "language": "python",
    }
    assert client_mac_trace == []
    assert server_mac_identifiers == {
        "reads": ["binary", "copyfile", "join", "sbindir", "shutil"],
        "writes": [],
        "language": "python",
    }
    assert server_mac_trace == []
    assert open_images_read_identifiers == {
        "reads": ["Path", "hierarchy_file", "pathlib", "read_text"],
        "writes": ["file_content"],
        "language": "python",
    }
    assert open_images_read_trace == []
    assert open_images_target_identifiers == {
        "reads": [],
        "writes": ["STEP_W"],
        "language": "python",
    }
    assert open_images_target_trace == []
