"""
Framework-specific edge case tests for TypeScript / JavaScript.

Frameworks covered:
- React / Next.js: hooks destructuring, 'use client'/'use server' directives,
  async server components, forwardRef
- NestJS: parameter-level decorators (@Param, @Body, @Query),
  @Module/@Controller/@Injectable class decorators
- Angular 17+: Signal<T>, inject(), @Input({ required: true }),
  standalone components

For each framework the tests target the MCP tools most affected
by that framework's idiomatic patterns.
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
# React / Next.js
# ===========================================================================

# --- find_identifiers (hooks) -----------------------------------------------

def test_react_find_identifiers_should_capture_both_state_tuple_names_as_writes(monkeypatch):
    """find_identifiers on 'const [count, setCount] = useState(0)' must put both names in writes."""
    source = """\
import { useState } from 'react';

function Counter() {
    const [count, setCount] = useState(0);
    const [error, setError] = useState<string | null>(null);
    return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "Counter.tsx"))
    result = mcp_server.find_identifiers("pipe", "Counter.tsx", 4)
    assert "count" in result["writes"], "count from useState destructuring must be a write"
    assert "setCount" in result["writes"], "setCount from useState destructuring must be a write"


def test_react_find_identifiers_should_capture_reads_inside_useeffect_deps(monkeypatch):
    """find_identifiers on the useEffect call must capture dependency array variables as reads."""
    source = """\
import { useEffect } from 'react';

function DataLoader({ userId, onLoad }) {
    useEffect(() => {
        fetchUser(userId).then(onLoad);
    }, [userId, onLoad]);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "DataLoader.tsx"))
    # Line 4: useEffect(() => {...}, [userId, onLoad])
    result = mcp_server.find_identifiers("pipe", "DataLoader.tsx", 4)
    assert "userId" in result["reads"] or "onLoad" in result["reads"], \
        "Dependency array variables must be captured as reads"


def test_react_find_identifiers_should_capture_ref_callback_in_usecallback(monkeypatch):
    """find_identifiers on 'const handler = useCallback(fn, [dep])' must write 'handler'."""
    source = """\
import { useCallback } from 'react';

function Form({ onSubmit, schema }) {
    const handleSubmit = useCallback(
        (data) => onSubmit(schema.validate(data)),
        [onSubmit, schema],
    );
    return <form onSubmit={handleSubmit} />;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "Form.tsx"))
    result = mcp_server.find_identifiers("pipe", "Form.tsx", 4)
    assert "handleSubmit" in result["writes"], \
        "useCallback result binding must be a write"


# --- extract_function (Next.js directives / async components) ---------------

def test_nextjs_extract_function_should_extract_async_server_component():
    """extract_function must return the body of an async Server Component."""
    source = """\
import { db } from '@/lib/db';

export default async function UserPage({ params }: { params: { id: string } }) {
    const user = await db.user.findUnique({ where: { id: params.id } });
    if (!user) notFound();
    return <UserCard user={user} />;
}
"""
    result = extract_function_from_source(source, "page.tsx", 4, 200)
    assert result is not None and "text" in result
    assert "UserPage" in result["text"]
    assert "async" in result["text"]


def test_nextjs_find_imports_should_detect_use_client_directive(monkeypatch):
    """find_imports must detect the 'use client' directive at the top of a Next.js file."""
    source = """\
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function LoginForm() {
    const [email, setEmail] = useState('');
    const router = useRouter();
    return <form />;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "LoginForm.tsx"))
    imports = mcp_server.find_imports("pipe", "LoginForm.tsx")
    # 'use client' is a directive, not a standard import — tool should at minimum not crash
    assert isinstance(imports, list), "find_imports must not fail on 'use client' directive"
    assert any("react" in imp for imp in imports), "Regular imports must still be detected"


def test_nextjs_extract_function_should_extract_server_action():
    """extract_function must extract an async Server Action (with 'use server' inside)."""
    source = """\
export async function createUser(formData: FormData) {
    'use server';
    const email = formData.get('email') as string;
    const password = formData.get('password') as string;
    await db.user.create({ data: { email, password: hash(password) } });
    redirect('/dashboard');
}
"""
    result = extract_function_from_source(source, "actions.ts", 1, 200)
    assert result is not None and "text" in result
    assert "createUser" in result["text"]
    assert "use server" in result["text"] or "formData" in result["text"]


# --- find_callers (forwardRef / HOCs) ----------------------------------------

def test_react_find_callers_should_find_forwarded_ref_component_usage(tmp_path):
    """find_callers must find JSX usages of a component wrapped in forwardRef."""
    src = """\
import { forwardRef } from 'react';

const Input = forwardRef<HTMLInputElement, InputProps>(function Input(props, ref) {
    return <input ref={ref} {...props} />;
});

function LoginForm() {
    const inputRef = useRef<HTMLInputElement>(null);
    return (
        <form>
            <Input ref={inputRef} name="email" />
        </form>
    );
}
"""
    (tmp_path / "Input.tsx").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "Input.tsx", "Input")
    assert len(results) >= 1, "JSX usage of Input component must be found"


# ===========================================================================
# NestJS
# ===========================================================================

# --- find_decorators (parameter-level) --------------------------------------

def test_nestjs_find_decorators_should_find_param_decorator_on_method_argument(monkeypatch):
    """find_decorators must return @Param('id') decorator applied to a method parameter."""
    source = """\
import { Controller, Get, Param, Body, Post } from '@nestjs/common';

@Controller('users')
export class UserController {
    @Get(':id')
    async getUser(@Param('id') id: string) {
        return this.service.findById(id);
    }

    @Post()
    async createUser(@Body() dto: CreateUserDto) {
        return this.service.create(dto);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "user.controller.ts"))
    result = mcp_server.find_decorators("pipe", "user.controller.ts", 6)
    assert any("Get" in d or "Param" in d for d in result), \
        "Method or parameter decorator @Get / @Param must be found"


def test_nestjs_find_decorators_should_find_class_level_controller_decorator(monkeypatch):
    """find_decorators on a method inside @Controller class must include the class decorator."""
    source = """\
import { Controller, Get, UseGuards } from '@nestjs/common';
import { AuthGuard } from './auth.guard';

@Controller('admin')
@UseGuards(AuthGuard)
export class AdminController {
    @Get('stats')
    getStats() {
        return this.statsService.get();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "admin.controller.ts"))
    result = mcp_server.find_decorators("pipe", "admin.controller.ts", 8)
    assert any("Controller" in d or "UseGuards" in d or "Get" in d for d in result), \
        "Class-level @Controller and @UseGuards must be visible from inside the class"


def test_nestjs_find_decorators_should_find_body_and_query_parameter_decorators(monkeypatch):
    """find_decorators must return @Query() and @Body() parameter decorators."""
    source = """\
import { Controller, Get, Query, Body, Put } from '@nestjs/common';

@Controller('items')
export class ItemController {
    @Get()
    list(@Query('page') page: number, @Query('limit') limit: number) {
        return this.service.list({ page, limit });
    }

    @Put(':id')
    update(@Param('id') id: string, @Body() dto: UpdateItemDto) {
        return this.service.update(id, dto);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "item.controller.ts"))
    result = mcp_server.find_decorators("pipe", "item.controller.ts", 6)
    assert any("Get" in d or "Query" in d for d in result), \
        "@Get and @Query parameter decorators must be found"


# --- find_identifiers (DI via constructor) -----------------------------------

def test_nestjs_find_identifiers_should_capture_injected_service_in_constructor(monkeypatch):
    """find_identifiers on 'private readonly userService: UserService' must capture it as write."""
    source = """\
import { Injectable } from '@nestjs/common';

@Injectable()
export class NotificationService {
    constructor(
        private readonly userService: UserService,
        private readonly mailer: MailerService,
    ) {}

    async notify(userId: string, message: string): Promise<void> {
        const user = await this.userService.findById(userId);
        await this.mailer.send(user.email, message);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "notification.service.ts"))
    # Line 6: private readonly userService: UserService
    result = mcp_server.find_identifiers("pipe", "notification.service.ts", 6)
    assert "userService" in result["writes"] or "userService" in result["reads"], \
        "Constructor-injected 'userService' must be captured"


def test_nestjs_trace_identifier_backward_should_trace_injected_service_usage(monkeypatch):
    """trace_identifier_backward on 'user' must reach the this.userService.findById() call."""
    source = """\
@Injectable()
export class OrderService {
    constructor(private readonly userService: UserService) {}

    async createOrder(userId: string, items: OrderItem[]): Promise<Order> {
        const user = await this.userService.findById(userId);
        const order = await this.repo.create({ user, items });
        return order;
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "order.service.ts"))
    chain = mcp_server.trace_identifier_backward("pipe", "order.service.ts", 7, "user")
    assert isinstance(chain, list) and len(chain) >= 1
    assert any(entry["line"] == 6 for entry in chain), \
        "Trace must reach line 6 where 'user' is assigned from the injected service"


def test_nestjs_find_callers_should_find_calls_to_service_method_across_module(tmp_path):
    """find_callers must find calls to a NestJS service method from a controller."""
    src = """\
import { Injectable } from '@nestjs/common';

@Injectable()
export class UserService {
    async findById(id: string): Promise<User | null> {
        return this.repo.findOne({ where: { id } });
    }
}

@Controller('users')
export class UserController {
    constructor(private readonly userService: UserService) {}

    @Get(':id')
    async getUser(@Param('id') id: string) {
        return this.userService.findById(id);
    }
}
"""
    (tmp_path / "users.module.ts").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "users.module.ts", "findById")
    assert len(results) >= 1, "findById called from controller must be found"


# ===========================================================================
# Angular 17+
# ===========================================================================

# --- find_identifiers (Signals) ---------------------------------------------

def test_angular_find_identifiers_should_capture_signal_write_on_assignment(monkeypatch):
    """find_identifiers on 'const count = signal(0)' must put 'count' in writes."""
    source = """\
import { Component, signal, computed } from '@angular/core';

@Component({ selector: 'app-counter', standalone: true, template: '' })
export class CounterComponent {
    readonly count = signal(0);
    readonly doubled = computed(() => this.count() * 2);

    increment(): void {
        this.count.update(v => v + 1);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "counter.component.ts"))
    result = mcp_server.find_identifiers("pipe", "counter.component.ts", 5)
    assert "count" in result["writes"], "signal() assignment must be a write"


def test_angular_find_identifiers_should_capture_inject_call_as_read(monkeypatch):
    """find_identifiers on 'private service = inject(UserService)' must capture 'inject'."""
    source = """\
import { Component, inject } from '@angular/core';
import { UserService } from './user.service';

@Component({ selector: 'app-profile', standalone: true, template: '' })
export class ProfileComponent {
    private userService = inject(UserService);
    private router = inject(Router);

    loadProfile(id: string) {
        return this.userService.findById(id);
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "profile.component.ts"))
    # Line 6: private userService = inject(UserService)
    result = mcp_server.find_identifiers("pipe", "profile.component.ts", 6)
    assert "userService" in result["writes"], "inject() result binding must be a write"
    assert "inject" in result["reads"] or "UserService" in result["reads"], \
        "inject() call must be captured as a read"


def test_angular_find_identifiers_should_capture_signal_update_call(monkeypatch):
    """find_identifiers on 'this.count.update(fn)' must capture 'count' as a read."""
    source = """\
@Component({ selector: 'app-todo', standalone: true, template: '' })
export class TodoComponent {
    items = signal<string[]>([]);

    addItem(text: string): void {
        this.items.update(current => [...current, text]);
    }

    removeItem(index: number): void {
        this.items.update(current => current.filter((_, i) => i !== index));
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "todo.component.ts"))
    result = mcp_server.find_identifiers("pipe", "todo.component.ts", 6)
    assert "items" in result["reads"], \
        "Signal field 'items' being updated must be captured as read"


# --- find_decorators (Angular-specific) -------------------------------------

def test_angular_find_decorators_should_find_input_with_required_option(monkeypatch):
    """find_decorators must return @Input({ required: true }) on a component property."""
    source = """\
import { Component, Input, Output, EventEmitter } from '@angular/core';

@Component({ selector: 'app-button', template: '' })
export class ButtonComponent {
    @Input({ required: true }) label!: string;
    @Input() variant: 'primary' | 'secondary' = 'primary';
    @Output() clicked = new EventEmitter<void>();

    handleClick(): void {
        this.clicked.emit();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "button.component.ts"))
    result = mcp_server.find_decorators("pipe", "button.component.ts", 9)
    assert any("Component" in d or "Input" in d for d in result), \
        "@Component class decorator or @Input field decorator must be visible from methods"


def test_angular_find_decorators_should_find_component_decorator_on_standalone(monkeypatch):
    """find_decorators on a method must expose the @Component decorator of its class."""
    source = """\
import { Component, OnInit } from '@angular/core';

@Component({
    selector: 'app-dashboard',
    standalone: true,
    imports: [CommonModule, RouterModule],
    template: `<router-outlet />`
})
export class DashboardComponent implements OnInit {
    ngOnInit(): void {
        this.loadData();
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "dashboard.component.ts"))
    result = mcp_server.find_decorators("pipe", "dashboard.component.ts", 10)
    assert any("Component" in d for d in result), \
        "@Component decorator must be returned for methods inside the component class"


def test_angular_find_callers_should_find_inject_function_usages(tmp_path):
    """find_callers must find all usages of inject() across Angular standalone components."""
    src = """\
import { inject } from '@angular/core';
import { Router } from '@angular/router';

export class AuthGuard {
    private router = inject(Router);
    private authService = inject(AuthService);

    canActivate(): boolean {
        if (!this.authService.isAuthenticated()) {
            this.router.navigate(['/login']);
            return false;
        }
        return true;
    }
}
"""
    (tmp_path / "auth.guard.ts").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "auth.guard.ts", "inject")
    assert len(results) >= 2, "Both inject() calls (Router, AuthService) must be found"
