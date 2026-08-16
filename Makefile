.PHONY: run build watch clean

BINARY := bin/gateway

run:
	go run ./cmd/gateway

build:
	go build -o $(BINARY) ./cmd/gateway

watch:
	air -c .air.toml

clean:
	rm -rf bin tmp
