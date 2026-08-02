package health

import (
	"context"
	"sync"
	"time"

	llmclient "github.com/mugen64/bibi-core/internal/llm"
	sttclient "github.com/mugen64/bibi-core/internal/stt"
	ttsclient "github.com/mugen64/bibi-core/internal/tts"
)

type ServiceStatus struct {
	Healthy bool   `json:"healthy"`
	Error   string `json:"error,omitempty"`
}

type Report struct {
	Status string        `json:"status"` // "ok" | "degraded"
	STT    ServiceStatus `json:"stt"`
	LLM    ServiceStatus `json:"llm"`
	TTS    ServiceStatus `json:"tts"`
}

type Aggregator struct {
	sttClient *sttclient.Client
	llmClient *llmclient.Client
	ttsClient *ttsclient.Client
}

func NewAggregator(stt *sttclient.Client, llm *llmclient.Client, tts *ttsclient.Client) *Aggregator {
	return &Aggregator{sttClient: stt, llmClient: llm, ttsClient: tts}
}

// Check queries all three backend services concurrently and returns a
// combined report. Runs all checks in parallel so total latency is
// bounded by the slowest single service, not the sum of all three.
func (a *Aggregator) Check(ctx context.Context) Report {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	var wg sync.WaitGroup
	report := Report{Status: "ok"}
	var mu sync.Mutex

	wg.Add(3)

	go func() {
		defer wg.Done()
		status := checkSTT(ctx, a.sttClient)
		mu.Lock()
		report.STT = status
		mu.Unlock()
	}()

	go func() {
		defer wg.Done()
		status := checkLLM(ctx, a.llmClient)
		mu.Lock()
		report.LLM = status
		mu.Unlock()
	}()

	go func() {
		defer wg.Done()
		status := checkTTS(ctx, a.ttsClient)
		mu.Lock()
		report.TTS = status
		mu.Unlock()
	}()

	wg.Wait()

	if !report.STT.Healthy || !report.LLM.Healthy || !report.TTS.Healthy {
		report.Status = "degraded"
	}

	return report
}

func checkSTT(ctx context.Context, c *sttclient.Client) ServiceStatus {
	resp, err := c.HealthCheck(ctx)
	if err != nil {
		return ServiceStatus{Healthy: false, Error: err.Error()}
	}
	return ServiceStatus{Healthy: resp.Healthy}
}

func checkLLM(ctx context.Context, c *llmclient.Client) ServiceStatus {
	resp, err := c.HealthCheck(ctx)
	if err != nil {
		return ServiceStatus{Healthy: false, Error: err.Error()}
	}
	return ServiceStatus{Healthy: resp.Healthy}
}

func checkTTS(ctx context.Context, c *ttsclient.Client) ServiceStatus {
	resp, err := c.HealthCheck(ctx)
	if err != nil {
		return ServiceStatus{Healthy: false, Error: err.Error()}
	}
	return ServiceStatus{Healthy: resp.Healthy}
}
