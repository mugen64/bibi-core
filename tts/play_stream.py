import subprocess
from piper_engine import Piper

def play_stream(piper, text):
    player = None

    try:
        for chunk in piper.stream(text):
            if player is None:
                player = subprocess.Popen(
                    [
                        "pw-cat",
                        "-p",
                        "-a",
                        "--format",
                        "s16",
                        "--rate",
                        str(chunk.sample_rate),
                        "--channels",
                        str(chunk.sample_channels),
                        "-"
                    ],
                    stdin=subprocess.PIPE,
                )

            player.stdin.write(chunk.audio_int16_bytes)

    finally:
        if player and player.stdin:
            player.stdin.close()
        if player:
            player.wait()
