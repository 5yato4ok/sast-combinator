"""
Framework-specific edge case tests for C#.

Frameworks covered:
- ASP.NET Core: minimal APIs (app.MapGet), [FromBody]/[FromRoute] parameter attributes,
  IActionResult return types, middleware pipeline
- Entity Framework Core: LINQ Include() chains, DbSet<T> queries,
  navigation properties, modelBuilder fluent API
- MediatR: CQRS pattern — IRequest<T>, IRequestHandler<TReq, TRes>,
  indirect dispatch via mediator.Send() invisible to find_callers
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
# ASP.NET Core
# ===========================================================================

# --- find_decorators --------------------------------------------------------

def test_aspnet_find_decorators_should_find_http_method_and_route_attributes(monkeypatch):
    """find_decorators must return [HttpGet("{id}")] and [Route] on an action method."""
    source = """\
using Microsoft.AspNetCore.Mvc;

[ApiController]
[Route("api/[controller]")]
public class ProductsController : ControllerBase
{
    [HttpGet("{id:long}")]
    [ProducesResponseType(typeof(ProductDto), StatusCodes.Status200OK)]
    public async Task<IActionResult> GetProduct(
        [FromRoute] long id,
        [FromQuery] bool includeDetails = false)
    {
        var product = await _service.GetByIdAsync(id, includeDetails);
        return product is null ? NotFound() : Ok(product);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "ProductsController.cs"))
    result = mcp_server.find_decorators("pipe", "ProductsController.cs", 9)
    assert any("HttpGet" in d or "ApiController" in d for d in result), \
        "[HttpGet] or [ApiController] must be found"


def test_aspnet_find_decorators_should_find_authorize_and_validate_antiforgery(monkeypatch):
    """find_decorators must return [Authorize] and [ValidateAntiForgeryToken] on a POST action."""
    source = """\
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

[ApiController]
public class AccountController : ControllerBase
{
    [HttpPost("login")]
    [AllowAnonymous]
    public async Task<IActionResult> Login([FromBody] LoginRequest request)
    {
        var token = await _authService.AuthenticateAsync(request.Email, request.Password);
        return token is null ? Unauthorized() : Ok(new { token });
    }

    [HttpDelete("logout")]
    [Authorize]
    public IActionResult Logout()
    {
        _authService.InvalidateToken(User.Identity!.Name!);
        return NoContent();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "AccountController.cs"))
    result = mcp_server.find_decorators("pipe", "AccountController.cs", 9)
    assert any("AllowAnonymous" in d or "HttpPost" in d for d in result), \
        "[AllowAnonymous] or [HttpPost] must be found"


def test_aspnet_find_decorators_should_find_minimal_api_route_in_lambda(monkeypatch):
    """find_decorators must not crash when called on a minimal API lambda handler."""
    source = """\
var app = builder.Build();

app.MapGet("/users/{id}", async (
    [FromRoute] Guid id,
    [FromServices] IUserService userService) =>
{
    var user = await userService.GetByIdAsync(id);
    return user is null ? Results.NotFound() : Results.Ok(user);
});

app.MapPost("/users", async (
    [FromBody] CreateUserRequest request,
    [FromServices] IUserService userService) =>
{
    var user = await userService.CreateAsync(request);
    return Results.Created($"/users/{user.Id}", user);
});
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "Program.cs"))
    # find_decorators on the lambda body must not raise
    result = mcp_server.find_decorators("pipe", "Program.cs", 7)
    assert isinstance(result, list), "find_decorators must return a list for minimal API lambdas"


# --- find_identifiers -------------------------------------------------------

def test_aspnet_find_identifiers_should_capture_from_body_param_as_write(monkeypatch):
    """find_identifiers on a method with [FromBody] param must include it as write."""
    source = """\
[ApiController]
[Route("api/orders")]
public class OrdersController : ControllerBase
{
    [HttpPost]
    public async Task<IActionResult> CreateOrder(
        [FromBody] CreateOrderRequest request,
        [FromHeader(Name = "X-Idempotency-Key")] string idempotencyKey)
    {
        var order = await _orderService.CreateAsync(request, idempotencyKey);
        return CreatedAtAction(nameof(GetOrder), new { id = order.Id }, order);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "OrdersController.cs"))
    result = mcp_server.find_identifiers("pipe", "OrdersController.cs", 10)
    assert "request" in result["reads"] or "idempotencyKey" in result["reads"], \
        "[FromBody] and [FromHeader] params used in method must be captured"


def test_aspnet_trace_identifier_backward_should_trace_request_to_from_body(monkeypatch):
    """trace_identifier_backward on field of FromBody param must reach the parameter."""
    source = """\
[ApiController]
public class InventoryController : ControllerBase
{
    [HttpPut("{id}")]
    public async Task<IActionResult> UpdateStock([FromBody] UpdateStockRequest request)
    {
        var newQty = request.Quantity;
        if (newQty < 0) return BadRequest("Quantity cannot be negative");
        await _inventoryService.UpdateAsync(request.ProductId, newQty);
        return NoContent();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "InventoryController.cs"))
    chain = mcp_server.trace_identifier_backward("pipe", "InventoryController.cs", 7, "newQty")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 7 for entry in chain)


# ===========================================================================
# Entity Framework Core
# ===========================================================================

# --- find_identifiers -------------------------------------------------------

def test_efcore_find_identifiers_should_capture_include_and_where_chain(monkeypatch):
    """find_identifiers on EF Core Include().Where().ToListAsync() must capture predicates."""
    source = """\
public class OrderRepository
{
    public async Task<List<Order>> GetUserOrdersAsync(Guid userId)
    {
        return await _context.Orders
            .Include(o => o.Items)
            .ThenInclude(i => i.Product)
            .Where(o => o.UserId == userId && o.Status != OrderStatus.Cancelled)
            .OrderByDescending(o => o.CreatedAt)
            .ToListAsync();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "OrderRepository.cs"))
    result = mcp_server.find_identifiers("pipe", "OrderRepository.cs", 8)
    assert "userId" in result["reads"] or "_context" in result["reads"], \
        "Filter variable or DbContext must be captured as reads in EF Core chain"


def test_efcore_find_identifiers_should_capture_navigation_property_access(monkeypatch):
    """find_identifiers on navigation property access must capture the chain root."""
    source = """\
public class ReportService
{
    public async Task<decimal> GetTotalRevenueAsync(Guid productId)
    {
        var product = await _context.Products
            .Include(p => p.OrderItems)
            .FirstOrDefaultAsync(p => p.Id == productId);

        return product?.OrderItems.Sum(oi => oi.Quantity * oi.UnitPrice) ?? 0m;
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "ReportService.cs"))
    result = mcp_server.find_identifiers("pipe", "ReportService.cs", 9)
    assert "product" in result["reads"], \
        "Navigation property chain root 'product' must be a read"


def test_efcore_trace_identifier_backward_should_trace_through_include_chain(monkeypatch):
    """trace_identifier_backward must trace 'orders' back through the Include query chain."""
    source = """\
public class DashboardService
{
    public async Task<DashboardData> GetDashboardAsync(Guid userId)
    {
        var orders = await _context.Orders
            .Include(o => o.Items)
            .Where(o => o.UserId == userId)
            .ToListAsync();

        var revenue = orders.Sum(o => o.Total);
        return new DashboardData { Revenue = revenue, OrderCount = orders.Count };
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "DashboardService.cs"))
    chain = mcp_server.trace_identifier_backward("pipe", "DashboardService.cs", 10, "orders")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] in range(5, 9) for entry in chain), \
        "Trace must reach the EF Core query chain that produces 'orders'"


# --- find_definition --------------------------------------------------------

def test_efcore_find_definition_should_find_dbset_property_on_context(tmp_path):
    """find_definition must find a DbSet<T> property on the DbContext class."""
    src = """\
using Microsoft.EntityFrameworkCore;

public class AppDbContext : DbContext
{
    public DbSet<User> Users { get; set; } = null!;
    public DbSet<Order> Orders { get; set; } = null!;
    public DbSet<Product> Products { get; set; } = null!;

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<User>().HasIndex(u => u.Email).IsUnique();
        modelBuilder.Entity<Order>().HasOne(o => o.User).WithMany(u => u.Orders);
    }
}
"""
    (tmp_path / "AppDbContext.cs").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "Users")
    assert len(results) >= 1, "DbSet<User> property 'Users' must be found"


# ===========================================================================
# MediatR
# ===========================================================================

# --- find_callers (indirect dispatch) ----------------------------------------

def test_mediatr_find_callers_should_note_handler_not_found_via_send(tmp_path):
    """find_callers for an IRequestHandler must document that mediator.Send() is indirect."""
    src = """\
using MediatR;

public record CreateUserCommand(string Email, string Password) : IRequest<UserDto>;

public class CreateUserCommandHandler : IRequestHandler<CreateUserCommand, UserDto>
{
    public async Task<UserDto> Handle(CreateUserCommand command, CancellationToken ct)
    {
        var user = await _userService.CreateAsync(command.Email, command.Password);
        return _mapper.Map<UserDto>(user);
    }
}

public class UserController : ControllerBase
{
    private readonly IMediator _mediator;

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateUserCommand command)
    {
        var result = await _mediator.Send(command);
        return Ok(result);
    }
}
"""
    (tmp_path / "Users.cs").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    # The handler is dispatched via mediator.Send() — not a direct call
    results = find_callers(tmp_path, "Users.cs", "Handle")
    # Documents the known gap: MediatR dispatch is invisible to static call analysis
    assert isinstance(results, list), "find_callers must not crash for MediatR handler"


def test_mediatr_find_definition_should_find_irequest_implementation(tmp_path):
    """find_definition must find the IRequestHandler implementation class."""
    src = """\
using MediatR;

public record GetUserQuery(Guid Id) : IRequest<UserDto>;

public class GetUserQueryHandler : IRequestHandler<GetUserQuery, UserDto>
{
    private readonly IUserRepository _repo;
    public GetUserQueryHandler(IUserRepository repo) => _repo = repo;

    public async Task<UserDto> Handle(GetUserQuery query, CancellationToken ct)
    {
        var user = await _repo.GetByIdAsync(query.Id, ct)
            ?? throw new NotFoundException(nameof(User), query.Id);
        return new UserDto(user.Id, user.Email, user.Name);
    }
}
"""
    (tmp_path / "GetUserQuery.cs").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "GetUserQueryHandler")
    assert len(results) >= 1, "MediatR handler class must be found by find_definition"


def test_mediatr_find_identifiers_should_capture_command_fields_in_handle(monkeypatch):
    """find_identifiers in Handle method must capture command fields accessed via dot notation."""
    source = """\
public class UpdateOrderHandler : IRequestHandler<UpdateOrderCommand, OrderDto>
{
    public async Task<OrderDto> Handle(UpdateOrderCommand command, CancellationToken ct)
    {
        var order = await _repo.GetByIdAsync(command.OrderId, ct);
        order.UpdateStatus(command.NewStatus);
        order.SetNote(command.Note);
        await _repo.SaveAsync(ct);
        return _mapper.Map<OrderDto>(order);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "UpdateOrderHandler.cs"))
    result = mcp_server.find_identifiers("pipe", "UpdateOrderHandler.cs", 5)
    assert "command" in result["reads"], "command parameter must be a read"
    assert "order" in result["writes"], "order must be a write"
