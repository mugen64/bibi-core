#!/usr/bin/env bash
set -euo pipefail

proj_dir=$(pwd)

# -- gen stt protobufs
mkdir -p internal/stt/pb

protoc -I proto \
  --go_out=internal/stt/pb --go_opt=paths=source_relative \
  --go-grpc_out=internal/stt/pb --go-grpc_opt=paths=source_relative \
  stt.proto

cd stt
uv run python -m grpc_tools.protoc \
  -I../proto \
  --python_out=. \
  --grpc_python_out=. \
  ../proto/stt.proto
cd "$proj_dir"
# -- end gen stt protobufs

# -- gen llm protobufs
echo "go -> llm"
pwd
mkdir -p internal/llm/pb

protoc -I proto \
  --go_out=internal/llm/pb --go_opt=paths=source_relative \
  --go-grpc_out=internal/llm/pb --go-grpc_opt=paths=source_relative \
  llm.proto

echo "python"
cd llm

uv run python -m grpc_tools.protoc \
  -I../proto \
  --python_out=. \
  --grpc_python_out=. \
  ../proto/llm.proto
cd "$proj_dir"


