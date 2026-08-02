#!/usr/bin/env bash
set -euo pipefail

# stt
mkdir -p internal/stt/pb
protoc -I proto \
  --go_out=internal/stt/pb --go_opt=paths=source_relative \
  --go-grpc_out=internal/stt/pb --go-grpc_opt=paths=source_relative \
  stt.proto
cd stt && uv run python -m grpc_tools.protoc -I../proto --python_out=. --grpc_python_out=. ../proto/stt.proto && cd ..

# llm
mkdir -p internal/llm/pb
protoc -I proto \
  --go_out=internal/llm/pb --go_opt=paths=source_relative \
  --go-grpc_out=internal/llm/pb --go-grpc_opt=paths=source_relative \
  llm.proto
cd llm && uv run python -m grpc_tools.protoc -I../proto --python_out=. --grpc_python_out=. ../proto/llm.proto && cd ..

# tts
mkdir -p internal/tts/pb
protoc -I proto \
  --go_out=internal/tts/pb --go_opt=paths=source_relative \
  --go-grpc_out=internal/tts/pb --go-grpc_opt=paths=source_relative \
  tts.proto
cd tts && uv run python -m grpc_tools.protoc -I../proto --python_out=. --grpc_python_out=. ../proto/tts.proto && cd ..
