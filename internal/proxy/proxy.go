package proxy

import (
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
)

// NewServiceProxy returns a reverse proxy that forwards requests to
// targetAddr, stripping the given prefix first - so a request to
// /api/stt/voices with prefix "/api/stt" reaches the backend as /voices.
func NewServiceProxy(name, targetAddr, prefix string) http.Handler {
	target := &url.URL{Scheme: "http", Host: targetAddr}
	rp := httputil.NewSingleHostReverseProxy(target)

	// Wrap the default director to also strip the prefix, and log/handle
	// errors so a downstream service being down doesn't just hang or
	// return a bare connection-refused to the client.
	originalDirector := rp.Director
	rp.Director = func(r *http.Request) {
		r.URL.Path = strings.TrimPrefix(r.URL.Path, prefix)
		if r.URL.Path == "" {
			r.URL.Path = "/"
		}
		originalDirector(r)
	}

	rp.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		slog.Error("proxy error", "service", name, "target", targetAddr, "error", err)
		w.WriteHeader(http.StatusBadGateway)
		w.Write([]byte(`{"error":"` + name + ` service unavailable"}`))
	}

	return rp
}
