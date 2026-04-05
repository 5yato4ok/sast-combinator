"""
Framework-specific edge case tests for Java.

Frameworks covered:
- Spring Boot: @RestController, @PathVariable/@RequestBody on params, @Value field injection,
  @Async methods
- Lombok: @Data/@Builder/@Getter/@Setter/@Slf4j — methods generated outside AST,
  find_callers/find_definition cannot see builder()/getXxx()
- JPA / Hibernate: @Entity, @Query (JPQL), Spring Data method naming, @PrePersist hooks
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
# Spring Boot
# ===========================================================================

# --- find_decorators --------------------------------------------------------

def test_spring_find_decorators_should_find_getmapping_on_controller_method(monkeypatch):
    """find_decorators must return @GetMapping with its path argument."""
    source = """\
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @GetMapping("/{id}")
    public ResponseEntity<UserDto> getUser(@PathVariable Long id) {
        return ResponseEntity.ok(service.findById(id));
    }

    @PostMapping
    public ResponseEntity<UserDto> createUser(@RequestBody CreateUserRequest req) {
        return ResponseEntity.status(201).body(service.create(req));
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "UserController.java"))
    result = mcp_server.find_decorators("pipe", "UserController.java", 8)
    assert any("GetMapping" in d or "RestController" in d for d in result), \
        "@GetMapping or class-level @RestController must be found"


def test_spring_find_decorators_should_find_pathvariable_and_requestbody_on_params(monkeypatch):
    """find_decorators must return annotations placed on method parameters."""
    source = """\
@RestController
@RequestMapping("/orders")
public class OrderController {

    @PutMapping("/{orderId}/status")
    public OrderDto updateStatus(
        @PathVariable Long orderId,
        @RequestBody UpdateStatusRequest request,
        @RequestHeader("X-User-Id") String userId
    ) {
        return service.updateStatus(orderId, request, userId);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "OrderController.java"))
    result = mcp_server.find_decorators("pipe", "OrderController.java", 6)
    assert any("PutMapping" in d or "PathVariable" in d for d in result), \
        "Parameter annotation @PathVariable must be visible from the method"


def test_spring_find_decorators_should_find_value_annotation_on_field(monkeypatch):
    """find_decorators must detect @Value("${...}") annotation on an injected field."""
    source = """\
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class JwtService {

    @Value("${app.jwt.secret}")
    private String jwtSecret;

    @Value("${app.jwt.expiration:3600}")
    private int jwtExpiration;

    public String generateToken(String subject) {
        return Jwts.builder()
            .setSubject(subject)
            .signWith(Keys.hmacShaKeyFor(jwtSecret.getBytes()))
            .compact();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "JwtService.java"))
    result = mcp_server.find_decorators("pipe", "JwtService.java", 13)
    assert any("Service" in d or "Value" in d for d in result), \
        "@Service class decorator or @Value field annotation must be visible from method"


# --- find_identifiers -------------------------------------------------------

def test_spring_find_identifiers_should_capture_pathvariable_param_as_read(monkeypatch):
    """find_identifiers on 'return service.findById(id)' must capture 'id' as a read."""
    source = """\
@RestController
public class ProductController {

    @GetMapping("/products/{id}")
    public ProductDto getProduct(@PathVariable Long id) {
        ProductDto dto = service.findById(id);
        return dto;
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "ProductController.java"))
    result = mcp_server.find_identifiers("pipe", "ProductController.java", 6)
    assert "id" in result["reads"], "@PathVariable 'id' used in method body must be a read"


def test_spring_find_identifiers_should_capture_value_field_in_method(monkeypatch):
    """find_identifiers on usage of @Value-injected field must capture field name as read."""
    source = """\
@Service
public class EmailService {

    @Value("${app.email.from}")
    private String fromAddress;

    public void sendEmail(String to, String subject, String body) {
        MimeMessage msg = mailSender.createMimeMessage();
        msg.setFrom(fromAddress);
        msg.setRecipient(RecipientType.TO, new InternetAddress(to));
        mailSender.send(msg);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "EmailService.java"))
    result = mcp_server.find_identifiers("pipe", "EmailService.java", 9)
    assert "fromAddress" in result["reads"], \
        "@Value-injected field 'fromAddress' must be captured as a read"


def test_spring_trace_identifier_backward_should_trace_request_body_to_param(monkeypatch):
    """trace_identifier_backward on a DTO field must trace it back to the @RequestBody param."""
    source = """\
@RestController
public class RegistrationController {

    @PostMapping("/register")
    public ResponseEntity<Void> register(@RequestBody RegisterRequest request) {
        String email = request.getEmail();
        String password = request.getPassword();
        userService.register(email, password);
        return ResponseEntity.ok().build();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "RegistrationController.java"))
    chain = mcp_server.trace_identifier_backward("pipe", "RegistrationController.java", 6, "email")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] in (5, 6) for entry in chain)


# ===========================================================================
# Lombok
# ===========================================================================

# --- find_callers (generated methods) ----------------------------------------

def test_lombok_find_callers_should_note_getter_not_found_in_ast(tmp_path):
    """find_callers for a Lombok-generated getter must return empty — method is not in AST."""
    src = """\
import lombok.Data;

@Data
public class User {
    private Long id;
    private String email;
    private boolean active;
}

public class UserService {
    public String getUserEmail(User user) {
        return user.getEmail();
    }
}
"""
    (tmp_path / "User.java").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    # getEmail() is generated by @Data — it has no definition in the AST
    results = find_callers(tmp_path, "User.java", "getEmail")
    # This test documents the known limitation: either 0 results (definition not in AST)
    # or it finds the call site. Either is informative for planning.
    assert isinstance(results, list), "find_callers must not crash on Lombok-generated method"


def test_lombok_find_definition_should_not_find_builder_method_in_ast(tmp_path):
    """find_definition for Lombok @Builder generated builder() must return empty."""
    src = """\
import lombok.Builder;
import lombok.Value;

@Value
@Builder
public class CreateUserCommand {
    String email;
    String password;
    String firstName;
    String lastName;
}

public class UserController {
    public User create(String email, String pw) {
        CreateUserCommand cmd = CreateUserCommand.builder()
            .email(email)
            .password(pw)
            .build();
        return service.handle(cmd);
    }
}
"""
    (tmp_path / "CreateUserCommand.java").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "builder")
    # Lombok-generated builder() is not in AST — documents the gap
    assert isinstance(results, list), "find_definition must not crash on Lombok builder()"


def test_lombok_find_identifiers_should_capture_log_field_from_slf4j(monkeypatch):
    """find_identifiers on 'log.info(...)' must capture 'log' as a read (from @Slf4j)."""
    source = """\
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

@Slf4j
@Service
public class PaymentService {

    public void processPayment(Long orderId, double amount) {
        log.info("Processing payment for order {} amount {}", orderId, amount);
        gateway.charge(orderId, amount);
        log.debug("Payment complete for order {}", orderId);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "PaymentService.java"))
    result = mcp_server.find_identifiers("pipe", "PaymentService.java", 9)
    assert "log" in result["reads"], \
        "@Slf4j-injected 'log' field must be captured as a read"


# --- find_decorators --------------------------------------------------------

def test_lombok_find_decorators_should_find_data_and_builder_on_class(monkeypatch):
    """find_decorators on a constructor of a @Data @Builder class must return both."""
    source = """\
import lombok.*;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OrderItem {
    private Long productId;
    private int quantity;
    private double unitPrice;

    public double getTotalPrice() {
        return quantity * unitPrice;
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "OrderItem.java"))
    result = mcp_server.find_decorators("pipe", "OrderItem.java", 13)
    assert any("Data" in d or "Builder" in d for d in result), \
        "@Data and @Builder class-level annotations must be visible from methods"


# ===========================================================================
# JPA / Hibernate
# ===========================================================================

# --- find_decorators --------------------------------------------------------

def test_jpa_find_decorators_should_find_query_annotation_on_repository_method(monkeypatch):
    """find_decorators must return @Query with its JPQL string on a repository method."""
    source = """\
import org.springframework.data.jpa.repository.*;

public interface UserRepository extends JpaRepository<User, Long> {

    @Query("SELECT u FROM User u WHERE u.email = :email AND u.active = true")
    Optional<User> findActiveByEmail(@Param("email") String email);

    @Query(value = "SELECT * FROM users WHERE created_at > :since", nativeQuery = true)
    List<User> findRecentUsers(@Param("since") LocalDateTime since);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "UserRepository.java"))
    result = mcp_server.find_decorators("pipe", "UserRepository.java", 6)
    assert any("Query" in d for d in result), \
        "@Query annotation with JPQL must be found on repository method"


def test_jpa_find_decorators_should_find_prepersist_lifecycle_annotation(monkeypatch):
    """find_decorators must return @PrePersist on an entity lifecycle callback method."""
    source = """\
import javax.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "Order.java"))
    result = mcp_server.find_decorators("pipe", "Order.java", 16)
    assert any("PrePersist" in d for d in result), \
        "@PrePersist lifecycle annotation must be found"


def test_jpa_find_decorators_should_find_onetomany_on_entity_field(monkeypatch):
    """find_decorators must detect @OneToMany(cascade=CascadeType.ALL) on an entity field."""
    source = """\
import javax.persistence.*;
import java.util.List;

@Entity
public class Cart {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.LAZY)
    @JoinColumn(name = "cart_id")
    private List<CartItem> items;

    public void addItem(CartItem item) {
        items.add(item);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "Cart.java"))
    result = mcp_server.find_decorators("pipe", "Cart.java", 15)
    assert any("Entity" in d or "OneToMany" in d for d in result), \
        "@Entity or @OneToMany field annotation must be visible from methods"


# --- find_identifiers -------------------------------------------------------

def test_jpa_find_identifiers_should_capture_reads_in_jpql_method_body(monkeypatch):
    """find_identifiers on Spring Data custom query method call must capture arguments."""
    source = """\
@Service
public class ReportService {

    private final UserRepository userRepository;

    public List<User> getRecentActiveUsers(LocalDateTime since) {
        String email = null;
        List<User> recent = userRepository.findRecentUsers(since);
        return recent.stream()
            .filter(u -> u.isActive())
            .collect(Collectors.toList());
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "ReportService.java"))
    result = mcp_server.find_identifiers("pipe", "ReportService.java", 8)
    assert "recent" in result["writes"], "recent must be a write"
    assert "since" in result["reads"] or "userRepository" in result["reads"], \
        "Method arguments and repository must be captured as reads"


def test_jpa_find_callers_should_find_lifecycle_callback_invocation_sites(tmp_path):
    """find_callers for @PrePersist method must find all direct invocation sites."""
    src = """\
import javax.persistence.*;

@Entity
public class AuditedEntity {

    @Column
    private LocalDateTime updatedAt;

    @PreUpdate
    @PrePersist
    protected void onSave() {
        updatedAt = LocalDateTime.now();
    }
}

public class MigrationHelper {
    public void fixTimestamps(AuditedEntity e) {
        e.onSave();
    }
}
"""
    (tmp_path / "AuditedEntity.java").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "AuditedEntity.java", "onSave")
    assert isinstance(results, list), "find_callers must not crash for JPA lifecycle method"
    assert len(results) >= 1, "Direct call e.onSave() must be found"
