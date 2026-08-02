Record 5 seconds of sample audio

```bash
```
```bash
arecord -D default -f S16_LE -r 16000 -c 1 -d 5 sample.wav
```
```
```
Download piper voices
```
python3 -m piper.download_voices en_US-lessac-medium

```
Play audio
```
pw-play file.ext 

```

```


Check current python executable
```
python -c "import sys; print(sys.executable)"
```



Protobuf code gen
```

go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
```
```
```
