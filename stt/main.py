from config import MODEL_DIR, DEFAULT_MODEL
from engine_manager import STTManager

sm = STTManager()

def main():
    print(sm.get_model())


if __name__ == "__main__":
    main()
