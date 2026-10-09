package proxy

import (
	"encoding/json"
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

	// Rewrite (not the deprecated Director) routes to target and strips
	// the given prefix, preserving the inbound Host header to match
	// NewSingleHostReverseProxy's old default behavior.
	rp := &httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.SetURL(target)
			pr.Out.Host = pr.In.Host

			pr.Out.URL.Path = strings.TrimPrefix(pr.In.URL.Path, prefix)
			if pr.Out.URL.Path == "" {
				pr.Out.URL.Path = "/"
			}
		},
	}

	rp.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		slog.Error("proxy error", "service", name, "target", targetAddr, "error", err)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		body, _ := json.Marshal(map[string]string{"error": name + " service unavailable"})
		if _, werr := w.Write(body); werr != nil {
			slog.Error("failed to write proxy error response", "service", name, "error", werr)
		}
	}

	return rp
}
