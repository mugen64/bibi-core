package ws

import (
	"log/slog"
	"net/http"

	"github.com/gorilla/websocket"
)

/**
*
*  4096 (4KB) is the typical OS Memory Page size
* Binary audio chunks: if you're sending ~3-4 second PCM windows at 16kHz mono (16-bit samples),
* 	that's roughly 16000 * 2 * 3 ≈ 96KB per chunk.
* 	A 4KB buffer doesn't reject that
* 	— gorilla/websocket handles messages larger than the buffer fine,
* 	it just does more internal read/write iterations to move the data.
* 	So 4096 isn't wrong, but if your typical frame size is closer to 50-100KB, a larger buffer
* 	(e.g. 16KB or 32KB) would mean fewer read/write syscalls per message —
* 	marginally more efficient.
* JSON control messages: these are tiny (well under 4KB),
* so the buffer size is irrelevant for them either way.
*
*
*
**/
var upgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 4096,
	//	ReadBufferSize:  16384, // 16KB - closer to actual PCM chunk sizes
	//	WriteBufferSize: 16384,
	// Locked down to same-origin by default in production; loosen only
	// if the client is served from a different origin during dev.
	CheckOrigin: func(r *http.Request) bool { return true },
}

// Handler upgrades an HTTP connection to WebSocket and runs the session.
func Handler(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		slog.Error("websocket upgrade failed", "error", err)
		return
	}

	session := NewSession(conn)
	session.Run()
}
