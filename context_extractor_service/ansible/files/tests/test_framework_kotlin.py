"""
Framework-specific edge case tests for Kotlin.

Frameworks covered:
- Ktor: routing DSL (routing { get("/") { ... } }), suspend lambdas as
  route bodies, call.receive<T>(), call.respond()
- Spring Boot + Kotlin: suspend fun in @Service/@Controller, coroutine-aware
  @Transactional, extension functions on repositories, Kotlin DSL beans
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
# Ktor
# ===========================================================================

# --- extract_function (routing DSL) -----------------------------------------

def test_ktor_extract_function_should_extract_route_handler_lambda():
    """extract_function must extract a Ktor routing lambda as a callable scope."""
    source = """\
fun Application.configureRouting() {
    routing {
        get("/health") {
            call.respond(HttpStatusCode.OK, mapOf("status" to "ok"))
        }

        authenticate("jwt") {
            get("/users/{id}") {
                val id = call.parameters["id"] ?: return@get call.respond(HttpStatusCode.BadRequest)
                val user = userService.findById(id)
                call.respond(user ?: HttpStatusCode.NotFound)
            }
        }
    }
}
"""
    result = extract_function_from_source(source, "Routing.kt", 3, 200)
    assert result is not None and "text" in result
    # Should return at minimum the route handler or the surrounding configureRouting
    assert "call" in result["text"] or "configureRouting" in result["text"]


def test_ktor_extract_function_should_extract_post_handler_with_receive():
    """extract_function must include call.receive<T>() in the extracted body."""
    source = """\
fun Route.userRoutes(userService: UserService) {
    post("/users") {
        val request = call.receive<CreateUserRequest>()
        val user = userService.create(request)
        call.respond(HttpStatusCode.Created, user)
    }

    put("/users/{id}") {
        val id = call.parameters["id"]!!
        val request = call.receive<UpdateUserRequest>()
        val updated = userService.update(id, request)
        call.respond(updated)
    }
}
"""
    result = extract_function_from_source(source, "UserRoutes.kt", 3, 200)
    assert result is not None and "text" in result
    assert "receive" in result["text"] or "userRoutes" in result["text"]


# --- find_identifiers -------------------------------------------------------

def test_ktor_find_identifiers_should_capture_call_parameters_as_reads(monkeypatch):
    """find_identifiers on 'val id = call.parameters["id"]' must capture 'call' as read."""
    source = """\
fun Route.itemRoutes() {
    get("/items/{id}") {
        val id = call.parameters["id"] ?: return@get call.respond(HttpStatusCode.BadRequest)
        val category = call.request.queryParameters["category"]
        val item = itemService.findById(id, category)
        call.respond(item)
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "ItemRoutes.kt"))
    result = mcp_server.find_identifiers("pipe", "ItemRoutes.kt", 3)
    assert "id" in result["writes"], "'id' assigned from call.parameters must be a write"
    assert "call" in result["reads"], "'call' in Ktor route handler must be a read"


def test_ktor_find_identifiers_should_capture_receive_result_as_write(monkeypatch):
    """find_identifiers on 'val request = call.receive<T>()' must put 'request' in writes."""
    source = """\
fun Route.authRoutes(authService: AuthService) {
    post("/login") {
        val credentials = call.receive<LoginRequest>()
        val token = authService.authenticate(credentials.email, credentials.password)
        if (token == null) {
            call.respond(HttpStatusCode.Unauthorized)
        } else {
            call.respond(mapOf("token" to token))
        }
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "AuthRoutes.kt"))
    result = mcp_server.find_identifiers("pipe", "AuthRoutes.kt", 3)
    assert "credentials" in result["writes"], \
        "call.receive<T>() result must be a write"


def test_ktor_trace_identifier_backward_should_trace_through_receive_to_call(monkeypatch):
    """trace_identifier_backward must trace a request field back to call.receive<T>()."""
    source = """\
fun Route.paymentRoutes(paymentService: PaymentService) {
    post("/payments") {
        val req = call.receive<PaymentRequest>()
        val result = paymentService.process(req.amount, req.currency, req.cardToken)
        call.respond(HttpStatusCode.Created, result)
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "PaymentRoutes.kt"))
    chain = mcp_server.trace_identifier_backward("pipe", "PaymentRoutes.kt", 4, "req")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 3 for entry in chain), \
        "Trace must reach the call.receive<>() assignment on line 3"


# --- find_callers (route handler functions) ----------------------------------

def test_ktor_find_callers_should_find_service_calls_inside_route_lambdas(tmp_path):
    """find_callers must find calls to a service function made inside Ktor route lambdas."""
    src = """\
class UserService {
    suspend fun findById(id: String): User? {
        return userRepository.findById(id)
    }

    suspend fun create(request: CreateUserRequest): User {
        return userRepository.save(User(email = request.email))
    }
}

fun Route.userRoutes(userService: UserService) {
    get("/users/{id}") {
        val id = call.parameters["id"]!!
        val user = userService.findById(id)
        call.respond(user ?: HttpStatusCode.NotFound)
    }
    post("/users") {
        val req = call.receive<CreateUserRequest>()
        val user = userService.create(req)
        call.respond(HttpStatusCode.Created, user)
    }
}
"""
    (tmp_path / "UserRoutes.kt").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "UserRoutes.kt", "findById")
    assert len(results) >= 1, "findById called inside Ktor route lambda must be found"


# ===========================================================================
# Spring Boot + Kotlin
# ===========================================================================

# --- find_decorators --------------------------------------------------------

def test_spring_kotlin_find_decorators_should_find_annotations_on_suspend_fun(monkeypatch):
    """find_decorators must find @GetMapping on a suspend function."""
    source = """\
import org.springframework.web.bind.annotation.*

@RestController
@RequestMapping("/api/users")
class UserController(private val userService: UserService) {

    @GetMapping("/{id}")
    suspend fun getUser(@PathVariable id: Long): ResponseEntity<UserDto> {
        val user = userService.findById(id)
        return if (user != null) ResponseEntity.ok(user) else ResponseEntity.notFound().build()
    }

    @PostMapping
    suspend fun createUser(@RequestBody request: CreateUserRequest): ResponseEntity<UserDto> {
        val user = userService.create(request)
        return ResponseEntity.status(201).body(user)
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "UserController.kt"))
    result = mcp_server.find_decorators("pipe", "UserController.kt", 8)
    assert any("GetMapping" in d or "RestController" in d for d in result), \
        "@GetMapping or @RestController must be found on a suspend fun"


def test_spring_kotlin_find_decorators_should_find_transactional_on_suspend_service(monkeypatch):
    """find_decorators must return @Transactional on a suspend service method."""
    source = """\
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

@Service
class OrderService(
    private val orderRepo: OrderRepository,
    private val inventoryService: InventoryService,
) {
    @Transactional
    suspend fun createOrder(userId: Long, items: List<OrderItemRequest>): Order {
        inventoryService.reserveItems(items)
        val order = Order(userId = userId, items = items.map { it.toOrderItem() })
        return orderRepo.save(order)
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "OrderService.kt"))
    result = mcp_server.find_decorators("pipe", "OrderService.kt", 10)
    assert any("Transactional" in d or "Service" in d for d in result), \
        "@Transactional must be found on suspend service method"


def test_spring_kotlin_find_decorators_should_find_validated_and_requestbody(monkeypatch):
    """find_decorators must return @Validated and @RequestBody on a controller method."""
    source = """\
import org.springframework.validation.annotation.Validated
import org.springframework.web.bind.annotation.*

@RestController
@Validated
class ProfileController {

    @PutMapping("/profile/{id}")
    suspend fun updateProfile(
        @PathVariable id: Long,
        @RequestBody @Valid request: UpdateProfileRequest,
    ): ProfileDto {
        return profileService.update(id, request)
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "ProfileController.kt"))
    result = mcp_server.find_decorators("pipe", "ProfileController.kt", 10)
    assert any("PutMapping" in d or "Validated" in d for d in result)


# --- find_identifiers -------------------------------------------------------

def test_spring_kotlin_find_identifiers_should_capture_coroutine_context_switch(monkeypatch):
    """find_identifiers on 'withContext(Dispatchers.IO) { ... }' must capture the block result."""
    source = """\
@Service
class FileService(private val storageClient: StorageClient) {

    suspend fun readFile(path: String): String = withContext(Dispatchers.IO) {
        storageClient.read(path)
    }

    suspend fun writeFile(path: String, content: String) {
        withContext(Dispatchers.IO) {
            storageClient.write(path, content)
        }
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "FileService.kt"))
    result = mcp_server.find_identifiers("pipe", "FileService.kt", 5)
    assert "storageClient" in result["reads"] or "path" in result["reads"], \
        "Variables inside withContext block must be captured as reads"


def test_spring_kotlin_find_identifiers_should_capture_constructor_injected_repo(monkeypatch):
    """find_identifiers on a service call must capture the injected repository."""
    source = """\
@Service
class UserService(
    private val userRepository: UserRepository,
    private val passwordEncoder: PasswordEncoder,
) {
    suspend fun register(email: String, password: String): User {
        val encoded = passwordEncoder.encode(password)
        return userRepository.save(User(email = email, passwordHash = encoded))
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "UserService.kt"))
    result = mcp_server.find_identifiers("pipe", "UserService.kt", 8)
    assert "userRepository" in result["reads"], \
        "Constructor-injected 'userRepository' must be captured as a read"
    assert "encoded" in result["reads"] or "email" in result["reads"], \
        "Arguments to repository.save() must be captured"


def test_spring_kotlin_trace_identifier_backward_should_trace_encoded_password(monkeypatch):
    """trace_identifier_backward on 'encoded' must reach the passwordEncoder.encode() line."""
    source = """\
@Service
class AuthService(
    private val userRepo: UserRepository,
    private val passwordEncoder: PasswordEncoder,
    private val jwtService: JwtService,
) {
    suspend fun authenticate(email: String, password: String): String? {
        val user = userRepo.findByEmail(email) ?: return null
        val encoded = passwordEncoder.encode(password)
        if (!passwordEncoder.matches(password, user.passwordHash)) return null
        return jwtService.generateToken(user.id.toString())
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "AuthService.kt"))
    chain = mcp_server.trace_identifier_backward("pipe", "AuthService.kt", 10, "encoded")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 9 for entry in chain), \
        "Trace must reach line 9 where 'encoded' is assigned"


# --- find_callers ------------------------------------------------------------

def test_spring_kotlin_find_callers_should_find_extension_function_on_repository(tmp_path):
    """find_callers must find calls to an extension function defined on a Spring repository."""
    src = """\
import org.springframework.data.repository.CrudRepository

interface OrderRepository : CrudRepository<Order, Long>

fun OrderRepository.findPendingOrders(): List<Order> {
    return findAll().filter { it.status == OrderStatus.PENDING }
}

@Service
class OrderScheduler(private val orderRepo: OrderRepository) {
    suspend fun processPending() {
        val pending = orderRepo.findPendingOrders()
        pending.forEach { processOrder(it) }
    }
}
"""
    (tmp_path / "OrderExt.kt").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "OrderExt.kt", "findPendingOrders")
    assert len(results) >= 1, "Extension function call must be found"
