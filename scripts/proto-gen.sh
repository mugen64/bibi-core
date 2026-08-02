#!/usr/bin/env bash
set -euo pipefail

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

# -- end gen stt protobufs

