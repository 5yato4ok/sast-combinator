"""
Framework-specific edge case tests for Go.

Frameworks covered:
- Gin: gin.Context as handler argument, c.ShouldBindJSON/c.JSON,
  router.Use(middleware) — middleware function reference
- GORM: struct field tags, fluent query chains .Where().First(),
  hooks BeforeCreate/AfterFind
- gRPC: generated service interfaces, unary/stream interceptors,
  grpc.UnaryInterceptor registration
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.extract import extract_function_from_source


def _stub(source: str, fname: str):
    def _reader(_pid: str, _fp: str):
        return source, Path(fname)
    return _reader


# ===========================================================================
# Gin
# ===========================================================================

# --- find_identifiers -------------------------------------------------------

def test_gin_find_identifiers_should_capture_context_and_dto_in_bind_call(monkeypatch):
    """find_identifiers on 'c.ShouldBindJSON(&dto)' must capture 'c' and 'dto' as reads."""
    source = """\
func CreateUser(c *gin.Context) {
    var dto CreateUserRequest
    if err := c.ShouldBindJSON(&dto); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    user, err := userService.Create(c.Request.Context(), dto)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusCreated, user)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "handlers.go"))
    result = mcp_server.find_identifiers("pipe", "handlers.go", 3)
    assert "c" in result["reads"], "gin.Context 'c' must be a read"
    assert "dto" in result["reads"] or "err" in result["writes"], \
        "Bind target or error variable must be captured"


def test_gin_find_identifiers_should_capture_response_variables_in_json_call(monkeypatch):
    """find_identifiers on 'c.JSON(http.StatusOK, response)' must capture 'response' as read."""
    source = """\
func GetOrder(c *gin.Context) {
    id := c.Param("id")
    order, err := orderService.FindByID(c.Request.Context(), id)
    if err != nil {
        c.JSON(http.StatusNotFound, gin.H{"error": "not found"})
        return
    }
    response := toOrderResponse(order)
    c.JSON(http.StatusOK, response)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "order_handler.go"))
    result = mcp_server.find_identifiers("pipe", "order_handler.go", 9)
    assert "response" in result["reads"], \
        "'response' passed to c.JSON must be captured as a read"
    assert "c" in result["reads"], "gin.Context 'c' must be a read"


def test_gin_trace_identifier_backward_should_trace_param_through_handler(monkeypatch):
    """trace_identifier_backward on 'id' must reach the c.Param() call."""
    source = """\
func DeleteItem(c *gin.Context) {
    id := c.Param("id")
    userID := c.GetString("user_id")
    if err := itemService.Delete(c.Request.Context(), id, userID); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.Status(http.StatusNoContent)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "item_handler.go"))
    chain = mcp_server.trace_identifier_backward("pipe", "item_handler.go", 4, "id")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 2 for entry in chain), \
        "Trace must reach line 2 where 'id' is assigned from c.Param()"


# --- find_callers (middleware registration) ----------------------------------

def test_gin_find_callers_should_find_middleware_passed_to_router_use(tmp_path):
    """find_callers must find the middleware function referenced in router.Use()."""
    src = """\
package main

import "github.com/gin-gonic/gin"

func AuthMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        token := c.GetHeader("Authorization")
        if token == "" {
            c.AbortWithStatus(401)
            return
        }
        c.Next()
    }
}

func LoggingMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        start := time.Now()
        c.Next()
        log.Printf("request took %v", time.Since(start))
    }
}

func main() {
    r := gin.Default()
    r.Use(AuthMiddleware())
    r.Use(LoggingMiddleware())
    r.Run(":8080")
}
"""
    (tmp_path / "main.go").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "main.go", "AuthMiddleware")
    assert len(results) >= 1, "AuthMiddleware referenced in router.Use() must be found"


# --- extract_function -------------------------------------------------------

def test_gin_extract_function_should_extract_handler_with_multiple_early_returns():
    """extract_function must return the full handler including multiple error-return branches."""
    source = """\
func UpdateProfile(c *gin.Context) {
    userID := c.GetString("user_id")
    if userID == "" {
        c.JSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
        return
    }
    var req UpdateProfileRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    updated, err := profileService.Update(c.Request.Context(), userID, req)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, updated)
}
"""
    result = extract_function_from_source(source, "profile_handler.go", 12, 200)
    assert result is not None and "text" in result
    assert "UpdateProfile" in result["text"]


# ===========================================================================
# GORM
# ===========================================================================

# --- find_identifiers -------------------------------------------------------

def test_gorm_find_identifiers_should_capture_variables_in_where_chain(monkeypatch):
    """find_identifiers on 'db.Where(...).First(&user)' must capture email and user."""
    source = """\
func FindUserByEmail(db *gorm.DB, email string) (*User, error) {
    var user User
    result := db.Where("email = ? AND active = ?", email, true).First(&user)
    if result.Error != nil {
        return nil, result.Error
    }
    return &user, nil
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "user_repo.go"))
    result = mcp_server.find_identifiers("pipe", "user_repo.go", 3)
    assert "result" in result["writes"], "result must be a write"
    assert "email" in result["reads"] or "db" in result["reads"], \
        "Variables in GORM .Where() chain must be captured as reads"


def test_gorm_find_identifiers_should_capture_struct_tags_are_not_misread(monkeypatch):
    """find_identifiers on a struct field with GORM tags must not crash or produce garbage."""
    source = """\
type Product struct {
    gorm.Model
    Name        string  \`gorm:"column:name;not null;size:255"\`
    Price       float64 \`gorm:"column:price;not null"\`
    CategoryID  uint    \`gorm:"column:category_id;index"\`
    Description string  \`gorm:"column:description;type:text"\`
}

func (p *Product) BeforeCreate(tx *gorm.DB) error {
    p.Name = strings.TrimSpace(p.Name)
    return nil
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "product.go"))
    result = mcp_server.find_identifiers("pipe", "product.go", 9)
    assert "p" in result["reads"] or "Name" in result["reads"], \
        "Struct fields accessed in GORM hook must be captured"


def test_gorm_trace_identifier_backward_should_trace_through_query_chain(monkeypatch):
    """trace_identifier_backward on 'user' must trace through the GORM query chain."""
    source = """\
func GetUserWithOrders(db *gorm.DB, userID uint) (*User, error) {
    var user User
    err := db.Preload("Orders.Items").
        Where("id = ?", userID).
        First(&user).Error
    if err != nil {
        return nil, err
    }
    return &user, nil
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "repo.go"))
    chain = mcp_server.trace_identifier_backward("pipe", "repo.go", 7, "user")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] in (2, 3, 4, 5) for entry in chain), \
        "Trace must reach the GORM Preload/Where chain that populates 'user'"


# --- find_callers (GORM hooks) -----------------------------------------------

def test_gorm_find_callers_should_find_before_create_hook_direct_call(tmp_path):
    """find_callers must find direct calls to a GORM BeforeCreate hook."""
    src = """\
package models

import "gorm.io/gorm"

type Subscription struct {
    gorm.Model
    UserID uint
    Plan   string
    Price  float64
}

func (s *Subscription) BeforeCreate(tx *gorm.DB) error {
    if s.Price <= 0 {
        return ErrInvalidPrice
    }
    return nil
}

func MigrateSubscription(db *gorm.DB, s *Subscription) {
    s.BeforeCreate(db)
    db.Create(s)
}
"""
    (tmp_path / "subscription.go").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "subscription.go", "BeforeCreate")
    assert len(results) >= 1, "Direct BeforeCreate call must be found"


# ===========================================================================
# gRPC
# ===========================================================================

# --- extract_function -------------------------------------------------------

def test_grpc_extract_function_should_extract_unary_interceptor():
    """extract_function must return the full body of a gRPC unary interceptor."""
    source = """\
func AuthInterceptor(
    ctx context.Context,
    req interface{},
    info *grpc.UnaryServerInfo,
    handler grpc.UnaryHandler,
) (interface{}, error) {
    token, err := extractToken(ctx)
    if err != nil {
        return nil, status.Error(codes.Unauthenticated, "missing token")
    }
    claims, err := validateToken(token)
    if err != nil {
        return nil, status.Error(codes.Unauthenticated, "invalid token")
    }
    ctx = context.WithValue(ctx, claimsKey{}, claims)
    return handler(ctx, req)
}
"""
    result = extract_function_from_source(source, "interceptor.go", 7, 200)
    assert result is not None and "text" in result
    assert "AuthInterceptor" in result["text"]
    assert "handler" in result["text"]


def test_grpc_find_identifiers_should_capture_context_and_request_in_handler(monkeypatch):
    """find_identifiers on the gRPC handler method must capture ctx and req as reads."""
    source = """\
type UserServiceServer struct {
    repo UserRepository
}

func (s *UserServiceServer) GetUser(ctx context.Context, req *pb.GetUserRequest) (*pb.User, error) {
    user, err := s.repo.FindByID(ctx, req.UserId)
    if err != nil {
        return nil, status.Errorf(codes.NotFound, "user %s not found", req.UserId)
    }
    return toProtoUser(user), nil
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "user_server.go"))
    result = mcp_server.find_identifiers("pipe", "user_server.go", 6)
    assert "ctx" in result["reads"], "ctx must be a read in gRPC handler"
    assert "req" in result["reads"] or "s" in result["reads"], \
        "Request or receiver must be captured as reads"


def test_grpc_find_callers_should_find_interceptor_registered_in_server_options(tmp_path):
    """find_callers must find the interceptor function passed to grpc.NewServer options."""
    src = """\
package main

import (
    "google.golang.org/grpc"
)

func AuthInterceptor(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
    return handler(ctx, req)
}

func LoggingInterceptor(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
    log.Printf("RPC: %s", info.FullMethod)
    return handler(ctx, req)
}

func main() {
    s := grpc.NewServer(
        grpc.UnaryInterceptor(AuthInterceptor),
        grpc.ChainUnaryInterceptor(LoggingInterceptor),
    )
    pb.RegisterUserServiceServer(s, &UserServiceServer{})
}
"""
    (tmp_path / "main.go").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "main.go", "AuthInterceptor")
    assert len(results) >= 1, "AuthInterceptor passed to grpc.UnaryInterceptor must be found"


# --- find_imports ------------------------------------------------------------

def test_grpc_find_imports_should_detect_generated_proto_import(monkeypatch):
    """find_imports must detect imports of generated protobuf packages."""
    source = """\
package server

import (
    "context"
    "google.golang.org/grpc"
    "google.golang.org/grpc/codes"
    "google.golang.org/grpc/status"
    pb "github.com/myapp/gen/proto/user/v1"
)

type Server struct {
    pb.UnimplementedUserServiceServer
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "server.go"))
    imports = mcp_server.find_imports("pipe", "server.go")
    assert any("grpc" in imp for imp in imports), "gRPC import must be detected"
    assert any("proto" in imp or "pb" in imp for imp in imports), \
        "Generated proto package import must be detected"
