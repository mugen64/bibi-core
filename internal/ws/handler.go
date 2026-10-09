package ws

import (
	"log/slog"
	"net/http"

	"github.com/gorilla/websocket"
	llmclient "github.com/mugen64/bibi-core/internal/llm"
	sttclient "github.com/mugen64/bibi-core/internal/stt"
	ttsclient "github.com/mugen64/bibi-core/internal/tts"
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
func NewHandler(sttClient *sttclient.Client, llmClient *llmclient.Client, ttsClient *ttsclient.Client, allowedOrigins []string) http.HandlerFunc {
	upgrader := websocket.Upgrader{
		ReadBufferSize:  4096,
		WriteBufferSize: 4096,
		//	ReadBufferSize:  16384, // 16KB - closer to actual PCM chunk sizes
		//	WriteBufferSize: 16384,
		CheckOrigin: makeOriginChecker(allowedOrigins),
	}

	return func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			slog.Error("websocket upgrade failed", "error", err)
			return
		}
		session := NewSession(conn, sttClient, llmClient, ttsClient)
		session.Run()
	}
}

// makeOriginChecker allows requests with no Origin header (non-browser
// clients never send one) and, when allowedOrigins is non-empty, any
// origin exactly matching one of them. An empty allowedOrigins allows
// every origin - an explicit, documented default suited to local dev,
// not an accidental one.
func makeOriginChecker(allowedOrigins []string) func(*http.Request) bool {
	if len(allowedOrigins) == 0 {
		return func(r *http.Request) bool { return true }
	}

	allowed := make(map[string]struct{}, len(allowedOrigins))
	for _, o := range allowedOrigins {
		allowed[o] = struct{}{}
	}

	return func(r *http.Request) bool {
		origin := r.Header.Get("Origin")
		if origin == "" {
			return true
		}
		_, ok := allowed[origin]
		return ok
	}
}
