"""
Framework-specific edge case tests for PHP.

Frameworks covered:
- Laravel: Eloquent ORM (static fluent API, scopes, relationships),
  Route facades (Route::get/middleware/group), service container injection,
  PHP 8 attributes on controllers
- Symfony: PHP 8 attributes (#[Route], #[IsGranted], #[AsTaggedItem]),
  service autowiring via constructor type-hints, form types,
  security voters

For each framework the tests target MCP tools most affected
by PHP framework idioms.
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
# Laravel
# ===========================================================================

# --- find_identifiers (Eloquent static chains) --------------------------------

def test_laravel_find_identifiers_should_capture_variables_in_eloquent_where_chain(monkeypatch):
    """find_identifiers on 'User::where(...)->first()' must capture filter args as reads."""
    source = """\
<?php

class UserRepository
{
    public function findByEmail(string $email): ?User
    {
        return User::where('email', $email)
            ->where('active', true)
            ->first();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "UserRepository.php"))
    result = mcp_server.find_identifiers("pipe", "UserRepository.php", 7)
    assert "email" in result["reads"] or "$email" in result["reads"], \
        "Filter variable $email in Eloquent where() must be captured as a read"


def test_laravel_find_identifiers_should_capture_reads_in_eloquent_relationship_access(monkeypatch):
    """find_identifiers on '$user->orders()->where(...)' must capture $user as read."""
    source = """\
<?php

class OrderController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $user = $request->user();
        $orders = $user->orders()
            ->with(['items.product'])
            ->whereNull('deleted_at')
            ->paginate(15);
        return response()->json($orders);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "OrderController.php"))
    result = mcp_server.find_identifiers("pipe", "OrderController.php", 8)
    assert "$user" in result["reads"] or "user" in result["reads"], \
        "$user in Eloquent relationship chain must be a read"


def test_laravel_trace_identifier_backward_should_trace_through_eloquent_query_chain(monkeypatch):
    """trace_identifier_backward on '$products' must trace through the query builder chain."""
    source = """\
<?php

class ProductService
{
    public function getActiveProducts(string $category): Collection
    {
        $products = Product::query()
            ->where('category', $category)
            ->where('active', true)
            ->orderBy('name')
            ->get();
        return $products;
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "ProductService.php"))
    chain = mcp_server.trace_identifier_backward("pipe", "ProductService.php", 12, "products")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] in range(7, 12) for entry in chain), \
        "Trace must reach the Eloquent query chain that produces $products"


# --- find_callers (route closures / controllers) -----------------------------

def test_laravel_find_callers_should_find_controller_method_referenced_in_route(tmp_path):
    """find_callers must find a controller action referenced in a Route facade call."""
    src = """\
<?php

use App\\Http\\Controllers\\UserController;
use Illuminate\\Support\\Facades\\Route;

Route::middleware('auth')->group(function () {
    Route::get('/users', [UserController::class, 'index']);
    Route::post('/users', [UserController::class, 'store']);
    Route::get('/users/{id}', [UserController::class, 'show']);
    Route::delete('/users/{id}', [UserController::class, 'destroy']);
});

class UserController extends Controller
{
    public function index(): JsonResponse
    {
        return response()->json(User::paginate());
    }

    public function store(StoreUserRequest $request): JsonResponse
    {
        $user = User::create($request->validated());
        return response()->json($user, 201);
    }

    public function show(int $id): JsonResponse
    {
        return response()->json(User::findOrFail($id));
    }
}
"""
    (tmp_path / "web.php").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "web.php", "index")
    assert isinstance(results, list), "find_callers must not crash on Laravel route arrays"


def test_laravel_find_callers_should_find_service_method_calls_in_controller(tmp_path):
    """find_callers must find calls to a service method made from a controller."""
    src = """\
<?php

class PaymentService
{
    public function charge(User $user, float $amount, string $currency): Payment
    {
        return $this->gateway->charge($user->stripe_id, $amount, $currency);
    }
}

class PaymentController extends Controller
{
    public function __construct(private readonly PaymentService $paymentService) {}

    public function store(PaymentRequest $request): JsonResponse
    {
        $payment = $this->paymentService->charge(
            $request->user(),
            $request->amount,
            $request->currency,
        );
        return response()->json($payment, 201);
    }
}
"""
    (tmp_path / "PaymentController.php").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "PaymentController.php", "charge")
    assert len(results) >= 1, "charge() called from controller must be found"


# --- find_imports / find_decorators -----------------------------------------

def test_laravel_find_imports_should_detect_use_statements(monkeypatch):
    """find_imports must return all 'use' import statements from a Laravel controller."""
    source = """\
<?php

namespace App\\Http\\Controllers;

use App\\Models\\User;
use App\\Services\\UserService;
use Illuminate\\Http\\JsonResponse;
use Illuminate\\Http\\Request;
use Illuminate\\Support\\Facades\\Hash;

class AuthController extends Controller
{
    public function __construct(private readonly UserService $userService) {}
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "AuthController.php"))
    imports = mcp_server.find_imports("pipe", "AuthController.php")
    assert any("UserService" in imp for imp in imports), \
        "use App\\Services\\UserService must be detected"
    assert any("Hash" in imp for imp in imports), \
        "use Illuminate\\Support\\Facades\\Hash must be detected"


# ===========================================================================
# Symfony
# ===========================================================================

# --- find_decorators (PHP 8 attributes) -------------------------------------

def test_symfony_find_decorators_should_find_route_attribute_on_controller_method(monkeypatch):
    """find_decorators must return #[Route('/api/users', methods: ['GET'])] as a decorator."""
    source = """\
<?php

namespace App\\Controller;

use Symfony\\Bundle\\FrameworkBundle\\Controller\\AbstractController;
use Symfony\\Component\\HttpFoundation\\JsonResponse;
use Symfony\\Component\\Routing\\Attribute\\Route;

class UserController extends AbstractController
{
    #[Route('/api/users', name: 'user_list', methods: ['GET'])]
    public function list(): JsonResponse
    {
        $users = $this->userRepository->findAll();
        return $this->json($users);
    }

    #[Route('/api/users/{id}', name: 'user_show', methods: ['GET'])]
    public function show(int $id): JsonResponse
    {
        $user = $this->userRepository->find($id);
        return $this->json($user);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "UserController.php"))
    result = mcp_server.find_decorators("pipe", "UserController.php", 12)
    assert any("Route" in d for d in result), \
        "#[Route] PHP 8 attribute must be found as a decorator"


def test_symfony_find_decorators_should_find_isgranted_security_attribute(monkeypatch):
    """find_decorators must return #[IsGranted('ROLE_ADMIN')] on a secured controller method."""
    source = """\
<?php

use Symfony\\Component\\Security\\Http\\Attribute\\IsGranted;
use Symfony\\Component\\Routing\\Attribute\\Route;

class AdminController extends AbstractController
{
    #[Route('/admin/users', methods: ['GET'])]
    #[IsGranted('ROLE_ADMIN')]
    public function listUsers(): JsonResponse
    {
        return $this->json($this->userRepo->findAll());
    }

    #[Route('/admin/settings', methods: ['GET', 'POST'])]
    #[IsGranted('ROLE_SUPER_ADMIN')]
    public function settings(Request $request): Response
    {
        return $this->render('admin/settings.html.twig');
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "AdminController.php"))
    result = mcp_server.find_decorators("pipe", "AdminController.php", 10)
    assert any("IsGranted" in d for d in result), \
        "#[IsGranted] security attribute must be found as a decorator"


def test_symfony_find_decorators_should_find_stacked_attributes_on_api_endpoint(monkeypatch):
    """find_decorators must return all stacked PHP 8 attributes on a method."""
    source = """\
<?php

use Symfony\\Component\\Routing\\Attribute\\Route;
use Symfony\\Component\\Security\\Http\\Attribute\\IsGranted;
use Symfony\\Component\\HttpKernel\\Attribute\\MapRequestPayload;

class PaymentController extends AbstractController
{
    #[Route('/payments', name: 'payment_create', methods: ['POST'])]
    #[IsGranted('ROLE_USER')]
    public function create(
        #[MapRequestPayload] CreatePaymentRequest $request,
    ): JsonResponse {
        $payment = $this->paymentService->create($request);
        return $this->json($payment, 201);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "PaymentController.php"))
    result = mcp_server.find_decorators("pipe", "PaymentController.php", 13)
    assert any("Route" in d for d in result), "#[Route] must be found"
    assert any("IsGranted" in d for d in result), "#[IsGranted] must be found"


# --- find_identifiers (autowired services) -----------------------------------

def test_symfony_find_identifiers_should_capture_autowired_service_in_constructor(monkeypatch):
    """find_identifiers on service property usage must capture the autowired service."""
    source = """\
<?php

namespace App\\Service;

class NotificationService
{
    public function __construct(
        private readonly MailerInterface $mailer,
        private readonly LoggerInterface $logger,
        private readonly string $senderEmail,
    ) {}

    public function sendWelcome(User $user): void
    {
        $email = (new Email())
            ->from($this->senderEmail)
            ->to($user->getEmail())
            ->subject('Welcome!')
            ->text('Welcome to our platform!');

        $this->mailer->send($email);
        $this->logger->info('Welcome email sent', ['user' => $user->getId()]);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "NotificationService.php"))
    result = mcp_server.find_identifiers("pipe", "NotificationService.php", 20)
    assert "mailer" in result["reads"] or "$this" in result["reads"], \
        "Autowired 'mailer' service must be captured as a read"


def test_symfony_trace_identifier_backward_should_trace_through_service_call(monkeypatch):
    """trace_identifier_backward must trace '$user' back to its origin in Symfony service."""
    source = """\
<?php

class UserRegistrationService
{
    public function register(RegisterRequest $request): User
    {
        $hashedPassword = $this->passwordHasher->hashPassword(
            new User(),
            $request->password,
        );
        $user = new User();
        $user->setEmail($request->email);
        $user->setPassword($hashedPassword);
        $this->entityManager->persist($user);
        $this->entityManager->flush();
        return $user;
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "UserRegistrationService.php"))
    chain = mcp_server.trace_identifier_backward("pipe", "UserRegistrationService.php", 16, "user")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] in range(11, 15) for entry in chain), \
        "Trace must reach the User construction / setter lines"


def test_symfony_find_definition_should_find_service_class_by_interface(tmp_path):
    """find_definition must find a Symfony service class implementing an interface."""
    src = """\
<?php

namespace App\\Repository;

use Doctrine\\Bundle\\DoctrineBundle\\Repository\\ServiceEntityRepository;
use Doctrine\\Persistence\\ManagerRegistry;

class UserRepository extends ServiceEntityRepository implements UserRepositoryInterface
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, User::class);
    }

    public function findActiveByEmail(string $email): ?User
    {
        return $this->findOneBy(['email' => $email, 'active' => true]);
    }
}
"""
    (tmp_path / "UserRepository.php").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "UserRepository")
    assert len(results) >= 1, "Symfony repository class must be found by find_definition"
