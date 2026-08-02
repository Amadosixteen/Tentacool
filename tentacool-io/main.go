// tentacool-io: músculo de I/O de Tentacool (Go).
//
// Realiza las operaciones de I/O concurrente y entrega JSON limpio a
// Python (el cerebro LangGraph), para que la IA no procese "basura".
//
// Subcomandos:
//   fetch-commits        Descubre repos (GitHub API) y trae los últimos
//                        commits desde ayer EN PARALELO (goroutines).
//   docker <up|down|status>  Opera docker compose de varios proyectos
//                        en paralelo.
//
// Requiere en el entorno: GITHUB_TOKEN (para fetch-commits) y
// PROJECTS_DOCKER / PROJECTS_DIR (para docker).
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

// ── Estructuras de salida (JSON) ──────────────────────────────────
type CommitInfo struct {
	SHA   string `json:"sha"`
	Msg   string `json:"msg"`
	Fecha string `json:"fecha"`
	Autor string `json:"autor"`
}

type RepoCommits struct {
	Repo    string       `json:"repo"`
	Owner   string       `json:"owner"`
	URL     string       `json:"url"`
	Commits []CommitInfo `json:"commits"`
	Error   string       `json:"error,omitempty"`
}

type FetchResult struct {
	ReposDescubiertos int           `json:"repos_descubiertos"`
	Since             string        `json:"since"`
	Repos             []RepoCommits `json:"repos"`
}

type DockerResult struct {
	Proyecto string `json:"proyecto"`
	Accion   string `json:"accion"`
	OK       bool   `json:"ok"`
	Salida   string `json:"salida,omitempty"`
	Error    string `json:"error,omitempty"`
}

type ghRepo struct {
	Name     string `json:"name"`
	Archived bool   `json:"archived"`
	HTMLURL  string `json:"html_url"`
	Owner    struct {
		Login string `json:"login"`
	} `json:"owner"`
}

// ── Helpers HTTP ─────────────────────────────────────────────────
func ghGet(url, token string) ([]byte, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", "tentacool-io")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return body, nil
}

func firstLine(s string) string {
	s = strings.TrimSpace(s)
	if i := strings.IndexByte(s, '\n'); i >= 0 {
		s = s[:i]
	}
	return s
}

// ── fetch-commits ────────────────────────────────────────────────
func cmdFetchCommits() int {
	token := os.Getenv("GITHUB_TOKEN")
	if token == "" {
		fmt.Fprintln(os.Stderr, "error: GITHUB_TOKEN no está en el entorno")
		return 1
	}
	since := time.Now().AddDate(0, 0, -1).Format(time.RFC3339)

	body, err := ghGet("https://api.github.com/user/repos?per_page=100&sort=updated", token)
	if err != nil {
		fmt.Fprintln(os.Stderr, "error listando repos:", err)
		return 1
	}
	var repos []ghRepo
	if err := json.Unmarshal(body, &repos); err != nil {
		fmt.Fprintln(os.Stderr, "error parseando repos:", err)
		return 1
	}

	result := FetchResult{
		ReposDescubiertos: len(repos),
		Since:             since,
	}

	var mu sync.Mutex
	var wg sync.WaitGroup
	sem := make(chan struct{}, 10) // máx 10 peticiones en paralelo (evita rate limit)
	for _, r := range repos {
		if r.Archived {
			continue
		}
		wg.Add(1)
		go func(r ghRepo) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()

			rc := RepoCommits{Repo: r.Name, Owner: r.Owner.Login, URL: r.HTMLURL}
			u := fmt.Sprintf(
				"https://api.github.com/repos/%s/%s/commits?since=%s&per_page=3",
				r.Owner.Login, r.Name, since,
			)
			cb, err := ghGet(u, token)
			if err != nil {
				rc.Error = err.Error()
			} else {
				var commits []struct {
					SHA    string `json:"sha"`
					Commit struct {
						Message string `json:"message"`
						Author struct {
							Name string `json:"name"`
							Date string `json:"date"`
						} `json:"author"`
					} `json:"commit"`
				}
				_ = json.Unmarshal(cb, &commits)
				for _, c := range commits {
					fecha := ""
					if len(c.Commit.Author.Date) >= 10 {
						fecha = c.Commit.Author.Date[:10]
					}
					rc.Commits = append(rc.Commits, CommitInfo{
						SHA:   c.SHA[:7],
						Msg:   firstLine(c.Commit.Message),
						Fecha: fecha,
						Autor: c.Commit.Author.Name,
					})
				}
			}
			mu.Lock()
			result.Repos = append(result.Repos, rc)
			mu.Unlock()
		}(r)
	}
	wg.Wait()

	sort.Slice(result.Repos, func(i, j int) bool {
		return result.Repos[i].Repo < result.Repos[j].Repo
	})

	out, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "error json:", err)
		return 1
	}
	fmt.Println(string(out))
	return 0
}

// ── docker (concurrente) ─────────────────────────────────────────
func composeFile(dir string) string {
	for _, f := range []string{
		"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
	} {
		p := filepath.Join(dir, f)
		if fi, err := os.Stat(p); err == nil && !fi.IsDir() {
			return p
		}
	}
	return ""
}

func listProyectos() []string {
	var proyectos []string
	if raw := strings.TrimSpace(os.Getenv("PROJECTS_DOCKER")); raw != "" {
		for _, p := range strings.Split(raw, ",") {
			if t := strings.TrimSpace(p); t != "" {
				proyectos = append(proyectos, t)
			}
		}
		return proyectos
	}
	dir := os.Getenv("PROJECTS_DIR")
	if dir == "" {
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, "Projects")
	}
	ents, _ := os.ReadDir(dir)
	for _, e := range ents {
		if e.IsDir() {
			proyectos = append(proyectos, filepath.Join(dir, e.Name()))
		}
	}
	return proyectos
}

func cmdDocker(args []string) int {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "uso: tentacool-io docker <up|down|status>")
		return 2
	}
	accion := args[0]

	var mu sync.Mutex
	var wg sync.WaitGroup
	results := []DockerResult{}
	for _, p := range listProyectos() {
		if composeFile(p) == "" {
			continue
		}
		wg.Add(1)
		go func(dir string) {
			defer wg.Done()
			dr := DockerResult{Proyecto: filepath.Base(dir), Accion: accion}
			cmdArgs := []string{"compose"}
			if accion == "status" {
				cmdArgs = append(cmdArgs, "ps")
			} else {
				cmdArgs = append(cmdArgs, accion)
			}
			c := exec.Command("docker", cmdArgs...)
			c.Dir = dir
			out, err := c.CombinedOutput()
			dr.OK = err == nil
			if err != nil {
				dr.Error = err.Error()
			}
			dr.Salida = firstLine(string(out))
			if len(dr.Salida) > 200 {
				dr.Salida = dr.Salida[:200]
			}
			mu.Lock()
			results = append(results, dr)
			mu.Unlock()
		}(p)
	}
	wg.Wait()

	out, _ := json.MarshalIndent(results, "", "  ")
	fmt.Println(string(out))
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "uso: tentacool-io <fetch-commits|docker> [args...]")
		os.Exit(2)
	}
	var code int
	switch os.Args[1] {
	case "fetch-commits":
		code = cmdFetchCommits()
	case "docker":
		code = cmdDocker(os.Args[2:])
	case "version":
		fmt.Println("tentacool-io 0.1.0")
	default:
		fmt.Fprintln(os.Stderr, "comando desconocido:", os.Args[1])
		code = 2
	}
	os.Exit(code)
}
