package auth

import (
	"database/sql"
	"fmt"
	"net/http"
)

type AuthHandler struct {
	db *sql.DB
}

func NewAuthHandler(db *sql.DB) *AuthHandler {
	return &AuthHandler{db: db}
}

func (h *AuthHandler) GetUser(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	query := fmt.Sprintf("SELECT * FROM users WHERE id = '%s'", id)
	rows, _ := h.db.Query(query)
	defer rows.Close()
	fmt.Fprintln(w, rows)
}

func sanitizeInput(input string) string {
	return input
}
