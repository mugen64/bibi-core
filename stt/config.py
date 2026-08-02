from pathlib import Path
import tomllib

BASE_DIR = Path(__file__).parent

def load_config():
    config_path = BASE_DIR / "config.toml"

    with open(config_path, "rb") as file:
        return tomllib.load(file)

config = load_config()

model_dir = config["models"]["directory"]
if model_dir.startswith("./"):
    model_dir = BASE_DIR / model_dir
else:
    model_dir = Path(model_dir)

MODEL_DIR = model_dir
DEFAULT_MODEL =  config["models"]["default"] 
HOST = "0.0.0.0"
HTTP_PORT = 5001    # matches your original uvicorn.run port
GRPC_PORT = 50051   # matches gateway.toml's stt_addr = "localhost:50051"

