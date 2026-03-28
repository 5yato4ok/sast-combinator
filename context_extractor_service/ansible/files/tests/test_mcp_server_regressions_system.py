from _mcp_server_regressions_helpers import *
def test_find_identifiers_should_capture_go_assignment_reads_and_writes(monkeypatch):
    source = """\
func f(data []byte) {
    hash := md5.Sum(data)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "site_info_reader.go"))

    result = mcp_server.find_identifiers("pipe", "site_info_reader.go", 2)

    assert "hash" in result["writes"]
    assert "md5" in result["reads"]
    assert "data" in result["reads"]




def test_find_identifiers_should_capture_cpp_member_initializer_identifiers(monkeypatch):
    source = """\
struct P {
    LivePreviewThumbnail* const thumbnailSource = new LivePreviewThumbnail(q);
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "live_preview.cpp"))

    result = mcp_server.find_identifiers("pipe", "live_preview.cpp", 2)

    assert "thumbnailSource" in result["writes"]
    assert "q" in result["reads"]  # LivePreviewThumbnail is a type, not a value
    assert "q" in result["reads"]




def test_find_identifiers_should_capture_python_with_open_identifiers(monkeypatch):
    source = """\
def f(scss_file):
    with open(scss_file) as f:
        return f.read()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "extract_brand_core_values.py"))

    result = mcp_server.find_identifiers("pipe", "extract_brand_core_values.py", 2)

    assert "open" in result["reads"]
    assert "scss_file" in result["reads"]
    assert "f" in result["writes"]




def test_find_identifiers_should_capture_python_function_signature_parameters(monkeypatch):
    source = """\
def change_view(self, request, object_id, form_url='', extra_context=None):
    return True
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "admin.py"))

    result = mcp_server.find_identifiers("pipe", "admin.py", 1)

    assert "change_view" in result["writes"]
    assert "self" in result["writes"]
    assert "request" in result["writes"]
    assert "object_id" in result["writes"]




def test_find_identifiers_should_capture_cpp_static_helper_signature_and_call_identifiers(monkeypatch):
    source = """\
template<class Get, class Set>
static void backup(Object* object, Get get, Set set, const char* backupId)
{
    new QnTypedPropertyBackup(object, get, set, backupId);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "property_backup.h"))

    signature_result = mcp_server.find_identifiers("pipe", "property_backup.h", 2)
    body_result = mcp_server.find_identifiers("pipe", "property_backup.h", 4)

    assert "backup" in signature_result["writes"]
    assert "object" in signature_result["writes"]
    assert "get" in signature_result["writes"]
    assert "set" in signature_result["writes"]
    assert "backupId" in signature_result["writes"]
    assert "object" in body_result["reads"]  # QnTypedPropertyBackup is a type, not a value
    assert "object" in body_result["reads"]
    assert "get" in body_result["reads"]
    assert "set" in body_result["reads"]
    assert "backupId" in body_result["reads"]



def test_find_identifiers_should_capture_python_with_open_join_identifiers(monkeypatch):
    source = """\
import os

def copy():
    with open(os.path.join(NGINX_DEPLOYMENT_DIR, 'nginx.conf.template'), 'r') as template_file:
        return template_file.read()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "copy_nginx_configs.py"))

    result = mcp_server.find_identifiers("pipe", "copy_nginx_configs.py", 4)

    assert "open" in result["reads"]
    assert "os" in result["reads"]
    assert "NGINX_DEPLOYMENT_DIR" in result["reads"]
    assert "template_file" in result["writes"]



def test_find_identifiers_should_capture_python_with_open_write_identifiers(monkeypatch):
    source = """\
def save(file_name, data):
    with open(file_name, 'wb') as f:
        f.write(data)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "filldata.py"))

    result = mcp_server.find_identifiers("pipe", "filldata.py", 2)

    assert "open" in result["reads"]
    assert "file_name" in result["reads"]
    assert "f" in result["writes"]




def test_find_identifiers_should_capture_python_with_open_join_write_identifiers(monkeypatch):
    source = """\
import os

def write_out(base):
    with open(os.path.join(base, 'nginx.test.conf'), 'w') as outfile:
        outfile.write('x')
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "copy_nginx_configs.py"))

    result = mcp_server.find_identifiers("pipe", "copy_nginx_configs.py", 4)

    assert "open" in result["reads"]
    assert "os" in result["reads"]
    assert "base" in result["reads"]
    assert "outfile" in result["writes"]





def test_trace_identifier_backward_should_not_self_reference_cpp_constructor_allocation():
    source = """\
void DragProcessingInstrument::initialize()
{
    DragProcessor *processor = new DragProcessor(this);
    processor->setHandler(this);
}
"""

    chain = trace_identifier_backward(source, Path("drag_processing_instrument.cpp"), 4, "processor")

    assert chain
    assert "processor" not in chain[0]["reads"]
    assert "this" in chain[0]["reads"]


def test_find_identifiers_should_capture_csharp_upload_copytoasync_reads(monkeypatch):
    source = """\
using Microsoft.AspNetCore.Http;

class UploadController {
    async Task SaveAsync(IFormFile formFile, Stream targetStream, CancellationToken cancellationToken) {
        await formFile.CopyToAsync(targetStream, cancellationToken);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "UploadController.cs"))

    result = mcp_server.find_identifiers("pipe", "UploadController.cs", 5)

    assert "formFile" in result["reads"]
    assert "CopyToAsync" in result["reads"]
    assert "targetStream" in result["reads"]
    assert "cancellationToken" in result["reads"]
    assert result["writes"] == []


def test_find_identifiers_should_capture_csharp_process_startinfo_argumentlist_reads(monkeypatch):
    source = """\
using System.Diagnostics;

class Runner {
    void Run(string userInput) {
        var psi = new ProcessStartInfo("git");
        psi.ArgumentList.Add(userInput);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Runner.cs"))

    result = mcp_server.find_identifiers("pipe", "Runner.cs", 6)

    assert "psi" in result["reads"]
    assert "ArgumentList" in result["reads"]
    assert "Add" in result["reads"]
    assert "userInput" in result["reads"]
    assert result["writes"] == []


def test_find_identifiers_should_capture_csharp_process_start_assignment(monkeypatch):
    source = """\
using System.Diagnostics;

class Runner {
    void Run(ProcessStartInfo psi) {
        var process = Process.Start(psi);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Runner.cs"))

    result = mcp_server.find_identifiers("pipe", "Runner.cs", 5)

    assert "process" in result["writes"]
    assert "Process" in result["reads"]
    assert "Start" in result["reads"]
    assert "psi" in result["reads"]


def test_find_identifiers_should_capture_csharp_results_file_reads(monkeypatch):
    source = """\
class DownloadController {
    object Download(string path) {
        return Results.File(path, "application/octet-stream");
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "DownloadController.cs"))

    result = mcp_server.find_identifiers("pipe", "DownloadController.cs", 3)

    assert "Results" in result["reads"]
    assert "File" in result["reads"]
    assert "path" in result["reads"]
    assert result["writes"] == []


def test_find_identifiers_should_capture_csharp_process_startinfo_object_initializer(monkeypatch):
    source = """\
using System.Diagnostics;

class Runner {
    void Run(string userInput) {
        var psi = new ProcessStartInfo {
            FileName = "git",
            Arguments = userInput,
            UseShellExecute = false,
        };
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Runner.cs"))

    result = mcp_server.find_identifiers("pipe", "Runner.cs", 5)

    assert "psi" in result["writes"]
    assert "ProcessStartInfo" in result["reads"]
    assert "userInput" in result["reads"]


def test_find_identifiers_should_capture_csharp_file_create_assignment_reads(monkeypatch):
    source = """\
using Microsoft.AspNetCore.Http;

class UploadController {
    async Task SaveAsync(IFormFile formFile, string path, CancellationToken cancellationToken) {
        await using var stream = File.Create(path);
        await formFile.CopyToAsync(stream, cancellationToken);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "UploadController.cs"))

    result = mcp_server.find_identifiers("pipe", "UploadController.cs", 5)

    assert "stream" in result["writes"]
    assert "File" in result["reads"]
    assert "Create" in result["reads"]
    assert "path" in result["reads"]


def test_find_identifiers_should_capture_csharp_process_startinfo_nested_argument_composition(monkeypatch):
    source = """\
using System.Diagnostics;

class Runner {
    void Run(string toolPath, string userInput) {
        var psi = new ProcessStartInfo {
            FileName = toolPath,
            Arguments = "--name " + userInput,
        };
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Runner.cs"))

    result = mcp_server.find_identifiers("pipe", "Runner.cs", 5)

    assert "psi" in result["writes"]
    assert "toolPath" in result["reads"]
    assert "userInput" in result["reads"]


def test_find_identifiers_should_capture_csharp_path_combine_before_file_create(monkeypatch):
    source = """\
using Microsoft.AspNetCore.Http;

class UploadController {
    async Task SaveAsync(IFormFile formFile, string fileName, CancellationToken cancellationToken) {
        var path = Path.Combine(rootDir, fileName);
        await using var stream = File.Create(path);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "UploadController.cs"))

    result = mcp_server.find_identifiers("pipe", "UploadController.cs", 6)

    assert "stream" in result["writes"]
    assert "File" in result["reads"]
    assert "Create" in result["reads"]
    assert "path" in result["reads"]


def test_find_identifiers_should_keep_typescript_declaration_reads_and_writes(monkeypatch):
    source = """\
function save(rootDir: string, fileName: string) {
    const path = join(rootDir, fileName);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "save.ts"))

    result = mcp_server.find_identifiers("pipe", "save.ts", 2)

    assert "path" in result["writes"]
    assert "join" in result["reads"]
    assert "rootDir" in result["reads"]
    assert "fileName" in result["reads"]


def test_find_identifiers_should_keep_java_local_declaration_reads_and_writes(monkeypatch):
    source = """\
class UploadController {
    void save(String rootDir, String fileName) {
        String path = join(rootDir, fileName);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "UploadController.java"))

    result = mcp_server.find_identifiers("pipe", "UploadController.java", 3)

    assert "path" in result["writes"]
    assert "join" in result["reads"]
    assert "rootDir" in result["reads"]
    assert "fileName" in result["reads"]


def test_find_identifiers_should_keep_go_short_var_declaration_reads_and_writes(monkeypatch):
    source = """\
func save(rootDir string, fileName string) {
    path := join(rootDir, fileName)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "save.go"))

    result = mcp_server.find_identifiers("pipe", "save.go", 2)

    assert "path" in result["writes"]
    assert "join" in result["reads"]
    assert "rootDir" in result["reads"]
    assert "fileName" in result["reads"]


def test_find_identifiers_should_keep_python_assignment_reads_and_writes(monkeypatch):
    source = """\
def save(root_dir, file_name):
    path = join(root_dir, file_name)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "save.py"))

    result = mcp_server.find_identifiers("pipe", "save.py", 2)

    assert "path" in result["writes"]
    assert "join" in result["reads"]
    assert "root_dir" in result["reads"]
    assert "file_name" in result["reads"]


def test_find_identifiers_should_keep_python_subprocess_command_composition(monkeypatch):
    source = """\
def run(tool_path, user_input):
    cmd = [tool_path, "--name", user_input]
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "runner.py"))

    result = mcp_server.find_identifiers("pipe", "runner.py", 2)

    assert "cmd" in result["writes"]
    assert "tool_path" in result["reads"]
    assert "user_input" in result["reads"]


def test_find_identifiers_should_keep_python_path_join_before_open(monkeypatch):
    source = """\
def save(base_dir, file_name):
    path = os.path.join(base_dir, file_name)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "save.py"))

    result = mcp_server.find_identifiers("pipe", "save.py", 2)

    assert "path" in result["writes"]
    assert "os" in result["reads"]
    assert "base_dir" in result["reads"]
    assert "file_name" in result["reads"]


def test_find_identifiers_should_keep_typescript_command_argument_array(monkeypatch):
    source = """\
function run(toolPath: string, userInput: string) {
  const cmd = [toolPath, '--name', userInput]
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "runner.ts"))

    result = mcp_server.find_identifiers("pipe", "runner.ts", 2)

    assert "cmd" in result["writes"]
    assert "toolPath" in result["reads"]
    assert "userInput" in result["reads"]


def test_find_identifiers_should_keep_java_process_builder_arguments(monkeypatch):
    source = """\
class Runner {
    void run(String toolPath, String userInput) {
        ProcessBuilder builder = new ProcessBuilder(toolPath, "--name", userInput);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "Runner.java"))

    result = mcp_server.find_identifiers("pipe", "Runner.java", 3)

    assert "builder" in result["writes"]
    assert "toolPath" in result["reads"]
    assert "userInput" in result["reads"]


def test_find_identifiers_should_keep_go_exec_command_arguments(monkeypatch):
    source = """\
func run(toolPath string, userInput string) {
    cmd := exec.Command(toolPath, "--name", userInput)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "runner.go"))

    result = mcp_server.find_identifiers("pipe", "runner.go", 2)

    assert "cmd" in result["writes"]
    assert "exec" in result["reads"]
    assert "Command" in result["reads"]
    assert "toolPath" in result["reads"]
    assert "userInput" in result["reads"]


def test_find_identifiers_should_keep_cpp_command_argument_vector(monkeypatch):
    source = """\
#include <vector>
#include <string>

void run(const std::string& toolPath, const std::string& userInput) {
    std::vector<std::string> cmd{toolPath, "--name", userInput};
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "runner.cpp"))

    result = mcp_server.find_identifiers("pipe", "runner.cpp", 5)

    assert "cmd" in result["writes"]
    assert "toolPath" in result["reads"]
    assert "userInput" in result["reads"]


def test_find_identifiers_should_keep_cpp_path_join_before_open(monkeypatch):
    source = """\
#include <filesystem>

void save(const std::filesystem::path& baseDir, const std::string& fileName) {
    auto path = baseDir / fileName;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "save.cpp"))

    result = mcp_server.find_identifiers("pipe", "save.cpp", 4)

    assert "path" in result["writes"]
    assert "baseDir" in result["reads"]
    assert "fileName" in result["reads"]
