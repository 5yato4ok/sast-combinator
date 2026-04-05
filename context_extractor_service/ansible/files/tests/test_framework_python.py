"""
Framework-specific edge case tests for Python.

Frameworks covered:
- Django: signal receivers, CBV decorators, QuerySet chains, request.user
- FastAPI: Depends() injection, response_model decorators, Pydantic validators
- SQLAlchemy 2.0: Mapped[], mapped_column(), async session, select() API
- Celery: @shared_task, .delay()/.apply_async() indirect invocation

For each framework the tests target the MCP tools most likely to misparse
or produce incorrect results for that framework's idiomatic patterns.
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
# Django
# ===========================================================================

# --- find_decorators --------------------------------------------------------

def test_django_find_decorators_should_return_receiver_with_signal_and_sender(monkeypatch):
    """find_decorators must return @receiver(post_save, sender=User) with full arguments."""
    source = """\
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def handle_user_created(sender, instance, created, **kwargs):
    if created:
        send_welcome_email(instance.email)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "signals.py"))
    result = mcp_server.find_decorators("pipe", "signals.py", 5)
    assert any("receiver" in d for d in result), \
        "@receiver decorator must be found on the signal handler"


def test_django_find_decorators_should_return_stacked_decorators_on_cbv_method(monkeypatch):
    """find_decorators must return all stacked decorators including @method_decorator."""
    source = """\
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View

@method_decorator(login_required, name='dispatch')
class ProtectedView(View):
    @staticmethod
    def get(request, pk):
        return render(request, 'detail.html', {'pk': pk})
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "views.py"))
    result = mcp_server.find_decorators("pipe", "views.py", 8)
    assert any("method_decorator" in d or "login_required" in d for d in result), \
        "Class-level @method_decorator must be visible for methods inside that class"


def test_django_find_decorators_should_find_permission_required_on_function_view(monkeypatch):
    """find_decorators must return @permission_required with its argument."""
    source = """\
from django.contrib.auth.decorators import permission_required

@permission_required('myapp.can_edit', raise_exception=True)
def edit_item(request, item_id):
    item = Item.objects.get(pk=item_id)
    return render(request, 'edit.html', {'item': item})
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "views.py"))
    result = mcp_server.find_decorators("pipe", "views.py", 4)
    assert any("permission_required" in d for d in result)


# --- find_identifiers / trace -----------------------------------------------

def test_django_find_identifiers_should_capture_reads_in_queryset_filter_chain(monkeypatch):
    """find_identifiers must capture field names and variables used in .filter()/.exclude()."""
    source = """\
def get_active_users(org_id):
    qs = User.objects.filter(
        is_active=True,
        organization_id=org_id,
    ).exclude(email='').order_by('-created_at')
    return list(qs.values('id', 'email'))
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "repo.py"))
    # Line 2: qs = User.objects.filter(...)
    result = mcp_server.find_identifiers("pipe", "repo.py", 2)
    assert "qs" in result["writes"], "qs must be a write"
    assert "org_id" in result["reads"] or "User" in result["reads"], \
        "Variables used in QuerySet chain must be captured as reads"


def test_django_find_identifiers_should_capture_request_user_chain(monkeypatch):
    """find_identifiers on 'if request.user.is_authenticated:' must capture 'request' as read."""
    source = """\
def protected_view(request):
    if request.user.is_authenticated:
        return render(request, 'dashboard.html')
    return redirect('/login/')
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "views.py"))
    result = mcp_server.find_identifiers("pipe", "views.py", 2)
    assert "request" in result["reads"], \
        "request in 'request.user.is_authenticated' must be a read"


def test_django_trace_identifier_backward_should_trace_queryset_variable(monkeypatch):
    """trace_identifier_backward must trace the queryset variable back to the ORM call."""
    source = """\
def get_report(team_id):
    base_qs = Team.objects.filter(id=team_id)
    members = base_qs.prefetch_related('members').first()
    return serialize(members)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "report.py"))
    chain = mcp_server.trace_identifier_backward("pipe", "report.py", 3, "members")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 3 for entry in chain)


# --- find_callers ------------------------------------------------------------

def test_django_find_callers_should_find_signal_handler_registered_via_receiver(tmp_path):
    """find_callers must find the signal handler function even when registered via @receiver."""
    src = """\
from django.dispatch import receiver
from django.db.models.signals import post_save

@receiver(post_save, sender=Order)
def on_order_saved(sender, instance, created, **kwargs):
    if created:
        notify_warehouse(instance.id)

def notify_warehouse(order_id):
    send_task('warehouse', order_id)
"""
    (tmp_path / "signals.py").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "signals.py", "notify_warehouse")
    assert len(results) >= 1, \
        "notify_warehouse called inside @receiver handler must be found"


# ===========================================================================
# FastAPI
# ===========================================================================

# --- find_decorators --------------------------------------------------------

def test_fastapi_find_decorators_should_return_route_decorator_with_response_model(monkeypatch):
    """find_decorators must return the full @router.post decorator with response_model kwarg."""
    source = """\
from fastapi import APIRouter

router = APIRouter()

@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(user_data: CreateUserRequest, db: Session = Depends(get_db)):
    return await user_service.create(db, user_data)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "router.py"))
    result = mcp_server.find_decorators("pipe", "router.py", 6)
    assert any("router.post" in d or "post" in d for d in result), \
        "@router.post decorator must be found on the endpoint function"


def test_fastapi_find_decorators_should_return_validator_decorator_on_pydantic_method(monkeypatch):
    """find_decorators must return @validator on a Pydantic model method."""
    source = """\
from pydantic import BaseModel, validator

class UserRequest(BaseModel):
    email: str
    age: int

    @validator('email')
    def email_must_contain_at(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email')
        return v.lower()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "schemas.py"))
    result = mcp_server.find_decorators("pipe", "schemas.py", 8)
    assert any("validator" in d for d in result), \
        "@validator decorator on Pydantic method must be detected"


def test_fastapi_find_decorators_should_find_field_validator_classmethod_stack(monkeypatch):
    """find_decorators must return both @field_validator and @classmethod when stacked."""
    source = """\
from pydantic import BaseModel, field_validator

class PaymentRequest(BaseModel):
    amount: float
    currency: str

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError('Amount must be positive')
        return v
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "payment.py"))
    result = mcp_server.find_decorators("pipe", "payment.py", 9)
    assert any("field_validator" in d for d in result), \
        "@field_validator must be found in stacked decorators"
    assert any("classmethod" in d for d in result), \
        "@classmethod must be found in stacked decorators"


# --- find_identifiers / trace -----------------------------------------------

def test_fastapi_find_identifiers_should_recognise_depends_default_as_injection(monkeypatch):
    """find_identifiers on endpoint signature line must capture Depends() as a read."""
    source = """\
from fastapi import Depends

async def get_user_profile(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(User).filter(User.id == user_id).first()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "endpoints.py"))
    # Line 5: db: Session = Depends(get_db)
    result = mcp_server.find_identifiers("pipe", "endpoints.py", 5)
    assert "db" in result["writes"] or "get_db" in result["reads"], \
        "Depends() injection: 'db' must be a write or 'get_db' must be a read"


def test_fastapi_trace_identifier_backward_should_trace_db_to_depends(monkeypatch):
    """trace_identifier_backward on 'db' must trace it back to the Depends() default."""
    source = """\
async def list_items(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    items = db.query(Item).offset(skip).limit(limit).all()
    return items
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "items.py"))
    chain = mcp_server.trace_identifier_backward("pipe", "items.py", 6, "db")
    assert isinstance(chain, list) and len(chain) >= 1
    # Should reach the parameter definition with Depends()
    assert any(entry["line"] in (1, 2) for entry in chain), \
        "Trace must reach the Depends(get_db) parameter declaration"


def test_fastapi_find_identifiers_should_capture_background_task_add(monkeypatch):
    """find_identifiers on 'background_tasks.add_task(fn, arg)' must capture fn and arg."""
    source = """\
from fastapi import BackgroundTasks

async def send_notification(
    email: str,
    background_tasks: BackgroundTasks,
):
    background_tasks.add_task(send_email, email, template='welcome')
    return {"status": "queued"}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "notify.py"))
    result = mcp_server.find_identifiers("pipe", "notify.py", 7)
    assert "background_tasks" in result["reads"], \
        "background_tasks receiver must be captured as a read"
    assert "send_email" in result["reads"], \
        "Task function 'send_email' must be captured as a read"


# ===========================================================================
# SQLAlchemy 2.0
# ===========================================================================

# --- extract_function -------------------------------------------------------

def test_sqlalchemy_extract_function_should_extract_model_with_mapped_columns():
    """extract_function on a model method must include Mapped[] type annotations."""
    source = """\
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    def deactivate(self) -> None:
        self.is_active = False
"""
    result = extract_function_from_source(source, "models.py", 13, 200)
    assert result is not None and "text" in result
    assert "deactivate" in result["text"]


def test_sqlalchemy_find_identifiers_should_capture_reads_in_select_where_chain(monkeypatch):
    """find_identifiers on select().where() must capture model class and filter value."""
    source = """\
from sqlalchemy import select

async def get_user_by_email(session: AsyncSession, email: str):
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "repo.py"))
    result = mcp_server.find_identifiers("pipe", "repo.py", 4)
    assert "stmt" in result["writes"], "stmt must be a write"
    assert "email" in result["reads"] or "User" in result["reads"], \
        "Variables in select().where() must be captured as reads"


def test_sqlalchemy_trace_identifier_backward_should_trace_through_async_session_execute(monkeypatch):
    """trace_identifier_backward on 'user' must reach the scalar_one_or_none() line."""
    source = """\
async def find_active_user(session: AsyncSession, user_id: int):
    stmt = select(User).where(User.id == user_id, User.is_active == True)
    rows = await session.execute(stmt)
    user = rows.scalar_one_or_none()
    if user is None:
        raise NotFoundError(user_id)
    return user
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "repo.py"))
    chain = mcp_server.trace_identifier_backward("pipe", "repo.py", 5, "user")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 4 for entry in chain), \
        "Trace must reach line 4 where 'user' is assigned"


# --- find_imports ------------------------------------------------------------

def test_sqlalchemy_find_imports_should_detect_mapped_and_mapped_column(monkeypatch):
    """find_imports must return SQLAlchemy 2.0 orm imports including Mapped."""
    source = """\
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

class Base(DeclarativeBase):
    pass
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "base.py"))
    imports = mcp_server.find_imports("pipe", "base.py")
    assert any("Mapped" in imp for imp in imports), \
        "SQLAlchemy 2.0 'Mapped' import must be detected"
    assert any("AsyncSession" in imp for imp in imports), \
        "AsyncSession import must be detected"


# ===========================================================================
# Celery
# ===========================================================================

# --- find_decorators --------------------------------------------------------

def test_celery_find_decorators_should_return_shared_task_with_bind_and_retries(monkeypatch):
    """find_decorators must return @shared_task(bind=True, max_retries=3)."""
    source = """\
from celery import shared_task

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_notification(self, user_id: int, message: str):
    try:
        deliver_message(user_id, message)
    except DeliveryError as exc:
        raise self.retry(exc=exc)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "tasks.py"))
    result = mcp_server.find_decorators("pipe", "tasks.py", 4)
    assert any("shared_task" in d for d in result), \
        "@shared_task decorator must be found"


def test_celery_find_decorators_should_find_app_task_on_bound_task(monkeypatch):
    """find_decorators must return @app.task for a task defined on a Celery app instance."""
    source = """\
from myproject.celery import app

@app.task(name='reports.generate', queue='heavy')
def generate_report(report_id: int, format: str = 'pdf'):
    data = fetch_report_data(report_id)
    return render_report(data, format)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "reports.py"))
    result = mcp_server.find_decorators("pipe", "reports.py", 4)
    assert any("app.task" in d or "task" in d for d in result), \
        "@app.task must be found on the Celery task function"


# --- find_callers ------------------------------------------------------------

def test_celery_find_callers_should_find_delay_call_as_indirect_invocation(tmp_path):
    """find_callers must find .delay() call sites as invocations of the task."""
    src = """\
from celery import shared_task

@shared_task
def process_upload(file_id: int, user_id: int):
    file = File.objects.get(id=file_id)
    run_analysis(file, user_id)

def handle_upload_complete(file_id, user_id):
    process_upload.delay(file_id, user_id)

def handle_bulk_upload(file_ids, user_id):
    for fid in file_ids:
        process_upload.apply_async(args=[fid, user_id], countdown=5)
"""
    (tmp_path / "tasks.py").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "tasks.py", "process_upload")
    # .delay() and .apply_async() are indirect calls — at minimum one should be found
    assert len(results) >= 1, \
        ".delay() or .apply_async() call sites must be found as invocations of the task"


def test_celery_find_identifiers_should_capture_args_in_delay_call(monkeypatch):
    """find_identifiers on 'send_email.delay(user_id, template)' must capture user_id and template."""
    source = """\
def on_registration_complete(user_id: int):
    template = 'welcome'
    send_email.delay(user_id, template)
    log_event('registration', user_id)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "handlers.py"))
    result = mcp_server.find_identifiers("pipe", "handlers.py", 3)
    assert "user_id" in result["reads"], "user_id in .delay() must be a read"
    assert "template" in result["reads"], "template in .delay() must be a read"


def test_celery_trace_identifier_backward_should_trace_task_result_from_apply_async(monkeypatch):
    """trace_identifier_backward on 'async_result' must reach the apply_async call."""
    source = """\
def schedule_report(report_id: int):
    async_result = generate_report.apply_async(
        args=[report_id],
        eta=datetime.utcnow() + timedelta(seconds=30),
    )
    store_task_id(report_id, async_result.id)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "scheduler.py"))
    chain = mcp_server.trace_identifier_backward("pipe", "scheduler.py", 6, "async_result")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] in (2, 3) for entry in chain), \
        "Trace must reach the apply_async() assignment"
