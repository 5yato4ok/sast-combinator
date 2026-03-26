import json
import os
import shutil
from pathlib import Path


OUTPUT_TRT_MODEL_NAME = "model.engine"
OUTPUT_CONFIG_NAME = "config.json"
OUTPUT_ONNX_MODEL_NAME = "model.onnx"
OUTPUT_PT_MODEL_NAME = "model.pt"


def prepare_output_dir(directory: str) -> None:
    user_response = input(
        f"Directory {directory} already exists. Do you want to clean it? (y/n): "
    )
    if user_response.lower() == "y":
        shutil.rmtree(directory)

    Path(directory).mkdir(parents=True, exist_ok=True)


def prepare_json_config(config_json: str, output_dir: str) -> dict:
    with open(config_json, "r") as f:
        config_data = json.load(f)
    config_data["classCount"] = 9
    config_data["weightsFile"] = OUTPUT_TRT_MODEL_NAME
    output_config = os.path.join(output_dir, OUTPUT_CONFIG_NAME)
    with open(output_config, "w") as f:
        json.dump(config_data, f, indent=4)


def build_onnx_model(input_pt_file: str, output_onnx_file: str, batch_size: int) -> None:
    model = YOLO(input_pt_file)
    f = model.export(format="onnx", batch=batch_size)
    shutil.move(f, output_onnx_file)
    print("ONNX model built successfully in " + output_onnx_file)


def prepare_onnx_model(input_model_file: str, output_dir: str, batch_size: int) -> None:
    extension = os.path.splitext(input_model_file)[1].lower()

    input_onnx = None
    input_pt = None
    if input_model_file.endswith(".pt"):
        input_pt = input_model_file
    elif input_model_file.endswith(".onnx"):
        input_onnx = input_model_file
    else:
        raise ValueError(f"Unsupported input model format: {extension}")

    output_onnx_path = os.path.join(output_dir, OUTPUT_ONNX_MODEL_NAME)
    output_pt_path = os.path.join(output_dir, OUTPUT_PT_MODEL_NAME)

    if input_pt:
        input_onnx = build_onnx_model(input_pt, output_onnx_path, batch_size)
        shutil.copy2(input_pt, output_pt_path)
    else:
        shutil.copy2(input_onnx, output_onnx_path)
