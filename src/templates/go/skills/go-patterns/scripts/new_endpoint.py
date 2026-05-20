"""Generate a Go (chi) HTTP handler scaffold per `references/anatomy.md`.

PURPOSE:      Emit handler + dto + service + test stubs in one shot.
INPUT:        --domain <name>   — internal/<domain>/.
              [--root <dir>]    — defaults to repo root (cwd).
OUTPUT:       Four files: handler.go, dto.go, service.go, handler_test.go
              under `internal/<domain>/`. Skipped if the file already
              exists.
DEPENDENCIES: stdlib only.
NOTES:        Idempotent — refuses to overwrite existing files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-") if part)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--domain", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    pkg_dir = Path(args.root) / "internal" / args.domain
    pkg_dir.mkdir(parents=True, exist_ok=True)
    pkg_name = args.domain.replace("-", "")
    type_name = _pascal(args.domain)

    files = {
        pkg_dir / "dto.go": (
            f"package {pkg_name}\n\n"
            f"// {type_name}Request is the wire format for create requests.\n"
            f"type {type_name}Request struct {{\n"
            f"    // TODO: fields\n"
            f"}}\n\n"
            f"// {type_name}Response is the wire format for create responses.\n"
            f"type {type_name}Response struct {{\n"
            f"    // TODO: fields\n"
            f"}}\n"
        ),
        pkg_dir / "service.go": (
            f"package {pkg_name}\n\n"
            f'import "context"\n\n'
            f"// Service holds business logic for {pkg_name}.\n"
            f"type Service struct {{\n"
            f"    // TODO: repo deps\n"
            f"}}\n\n"
            f"func NewService() *Service {{ return &Service{{}} }}\n\n"
            f"func (s *Service) Create(ctx context.Context, req {type_name}Request) ({type_name}Response, error) {{\n"
            f"    // TODO: business logic\n"
            f"    return {type_name}Response{{}}, nil\n"
            f"}}\n"
        ),
        pkg_dir / "handler.go": (
            f"package {pkg_name}\n\n"
            f"import (\n"
            f'    "encoding/json"\n'
            f'    "net/http"\n'
            f")\n\n"
            f"type Handler struct {{ Service *Service }}\n\n"
            f"func NewHandler(s *Service) *Handler {{ return &Handler{{Service: s}} }}\n\n"
            f"func (h *Handler) Create(w http.ResponseWriter, r *http.Request) {{\n"
            f"    var req {type_name}Request\n"
            f"    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {{\n"
            f"        http.Error(w, err.Error(), http.StatusBadRequest)\n"
            f"        return\n"
            f"    }}\n"
            f"    resp, err := h.Service.Create(r.Context(), req)\n"
            f"    if err != nil {{\n"
            f"        http.Error(w, err.Error(), http.StatusInternalServerError)\n"
            f"        return\n"
            f"    }}\n"
            f'    w.Header().Set("Content-Type", "application/json")\n'
            f"    w.WriteHeader(http.StatusCreated)\n"
            f"    _ = json.NewEncoder(w).Encode(resp)\n"
            f"}}\n"
        ),
        pkg_dir / "handler_test.go": (
            f"package {pkg_name}\n\n"
            f"import (\n"
            f'    "net/http"\n'
            f'    "net/http/httptest"\n'
            f'    "strings"\n'
            f'    "testing"\n'
            f")\n\n"
            f"func TestCreate_ReturnsCreated(t *testing.T) {{\n"
            f"    h := NewHandler(NewService())\n"
            f'    req := httptest.NewRequest(http.MethodPost, "/{args.domain}/", strings.NewReader("{{}}"))\n'
            f"    rr := httptest.NewRecorder()\n"
            f"    h.Create(rr, req)\n"
            f"    if rr.Code != http.StatusCreated {{\n"
            f'        t.Fatalf("want 201, got %d", rr.Code)\n'
            f"    }}\n"
            f"}}\n"
        ),
    }

    for path in files:
        if path.exists():
            print(f"ERROR: refuse to overwrite existing file: {path}", file=sys.stderr)
            return 1

    for path, body in files.items():
        path.write_text(body, encoding="utf-8")
        print(f"OK: wrote {path}")
    print(f"INFO: register the handler in cmd/<service>/main.go (chi router)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
