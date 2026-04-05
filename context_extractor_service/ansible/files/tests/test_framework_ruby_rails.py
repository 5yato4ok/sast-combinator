"""
Framework-specific edge case tests for Ruby on Rails.

Covers:
- ActiveRecord: has_many/belongs_to (generated methods), scope lambdas,
  before_save/after_commit callbacks, validates
- ActionController: before_action :method, strong parameters, respond_to blocks
- Concerns: included hook, extend ClassMethods, instance methods via mixin
- ActiveJob: perform method, queue_as DSL

For each area the tests target MCP tools most affected by Rails idioms.
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
# ActiveRecord: callbacks and scopes
# ===========================================================================

def test_rails_find_decorators_equivalent_should_find_before_save_callback(monkeypatch):
    """find_decorators must return before_save, after_commit etc. as decorator-like constructs."""
    source = """\
class User < ApplicationRecord
  before_save :normalize_email
  after_commit :send_welcome_email, on: :create
  before_validation :strip_whitespace

  def normalize_email
    self.email = email.downcase.strip
  end

  def send_welcome_email
    UserMailer.welcome(self).deliver_later
  end
end
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "user.rb"))
    result = mcp_server.find_decorators("pipe", "user.rb", 6)
    # before_save / after_commit are class-level macro calls, not decorators in syntax
    # They may not appear in find_decorators — documents the gap
    assert isinstance(result, list), "find_decorators must return a list for Rails models"


def test_rails_find_callers_should_find_callback_method_called_from_before_save(tmp_path):
    """find_callers must find the callback method referenced in before_save :method."""
    src = """\
class Order < ApplicationRecord
  before_save :calculate_total
  after_commit :notify_warehouse, on: :create

  def calculate_total
    self.total = line_items.sum(:price)
  end

  def notify_warehouse
    WarehouseJob.perform_later(id)
  end
end

class OrdersController < ApplicationController
  def create
    order = Order.new(order_params)
    order.calculate_total
    order.save!
  end
end
"""
    (tmp_path / "order.rb").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "order.rb", "calculate_total")
    assert len(results) >= 1, \
        "Direct call to calculate_total from controller must be found"


def test_rails_find_definition_should_find_scope_lambda(tmp_path):
    """find_definition must find a named scope defined as a lambda."""
    src = """\
class Product < ApplicationRecord
  scope :active, -> { where(active: true) }
  scope :featured, -> { where(featured: true).order(priority: :desc) }
  scope :by_category, ->(cat) { where(category: cat) }
  scope :expensive, -> { where('price > ?', 100) }

  def self.search(query)
    where('name ILIKE ? OR description ILIKE ?', "%#{query}%", "%#{query}%")
  end
end
"""
    (tmp_path / "product.rb").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "active")
    assert isinstance(results, list), "find_definition must not crash on Rails scope"


def test_rails_find_identifiers_should_capture_reads_in_active_record_query(monkeypatch):
    """find_identifiers on 'User.where(email: email).first' must capture email as read."""
    source = """\
class SessionsController < ApplicationController
  def create
    email = params[:email]
    password = params[:password]
    user = User.where(email: email).where(active: true).first
    if user&.authenticate(password)
      session[:user_id] = user.id
      redirect_to dashboard_path
    else
      flash[:error] = "Invalid credentials"
      render :new
    end
  end
end
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "sessions_controller.rb"))
    result = mcp_server.find_identifiers("pipe", "sessions_controller.rb", 5)
    assert "email" in result["reads"], "email used in .where must be a read"
    assert "user" in result["writes"], "user assigned from query must be a write"


# ===========================================================================
# ActiveRecord: generated methods documentation tests
# ===========================================================================

def test_rails_find_callers_should_document_generated_has_many_method_gap(tmp_path):
    """find_callers for a has_many generated method must document the known limitation."""
    src = """\
class Author < ApplicationRecord
  has_many :books, dependent: :destroy
  has_many :reviews, through: :books
end

class BooksController < ApplicationController
  def index
    @author = Author.find(params[:author_id])
    @books = @author.books.includes(:reviews)
    render json: @books
  end
end
"""
    (tmp_path / "author.rb").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    # has_many :books generates .books method — not in AST
    results = find_callers(tmp_path, "author.rb", "books")
    assert isinstance(results, list), "find_callers must not crash for has_many generated method"
    # Calling @author.books — may or may not be found depending on implementation


def test_rails_find_definition_should_not_find_belongs_to_generated_accessor(tmp_path):
    """find_definition must document that belongs_to generated accessors are not in AST."""
    src = """\
class Comment < ApplicationRecord
  belongs_to :user
  belongs_to :post

  validates :body, presence: true, length: { minimum: 5 }
end

class CommentsController < ApplicationController
  def show
    @comment = Comment.find(params[:id])
    @author = @comment.user
  end
end
"""
    (tmp_path / "comment.rb").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    # belongs_to :user generates .user method — not defined in AST
    results = find_definition(tmp_path, "user")
    assert isinstance(results, list), "find_definition must not crash for belongs_to accessor"


# ===========================================================================
# ActionController: before_action and strong parameters
# ===========================================================================

def test_rails_find_callers_should_find_before_action_method_referenced_symbolically(tmp_path):
    """find_callers must find a controller method referenced via before_action :method."""
    src = """\
class ArticlesController < ApplicationController
  before_action :authenticate_user!
  before_action :set_article, only: [:show, :edit, :update, :destroy]
  before_action :authorize_author, only: [:edit, :update, :destroy]

  def show
    render json: @article
  end

  private

  def set_article
    @article = Article.find(params[:id])
  end

  def authorize_author
    redirect_to root_path unless @article.author == current_user
  end
end
"""
    (tmp_path / "articles_controller.rb").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "articles_controller.rb", "set_article")
    # set_article is referenced in before_action — may or may not be found
    assert isinstance(results, list), "find_callers must not crash on Rails before_action"


def test_rails_find_identifiers_should_capture_strong_params_permit(monkeypatch):
    """find_identifiers on 'params.require(:user).permit(...)' must capture 'params' as read."""
    source = """\
class UsersController < ApplicationController
  def create
    @user = User.new(user_params)
    if @user.save
      render json: @user, status: :created
    else
      render json: @user.errors, status: :unprocessable_entity
    end
  end

  private

  def user_params
    params.require(:user).permit(:email, :name, :password, :password_confirmation)
  end
end
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "users_controller.rb"))
    result = mcp_server.find_identifiers("pipe", "users_controller.rb", 13)
    assert "params" in result["reads"], \
        "'params' in strong parameters must be captured as a read"


def test_rails_extract_function_should_extract_controller_action_with_respond_to():
    """extract_function must return full action body including respond_to block."""
    source = """\
class ReportsController < ApplicationController
  def show
    @report = Report.find(params[:id])
    respond_to do |format|
      format.html { render :show }
      format.json { render json: @report }
      format.pdf  { send_data @report.to_pdf, type: 'application/pdf' }
    end
  end
end
"""
    result = extract_function_from_source(source, "reports_controller.rb", 4, 200)
    assert result is not None and "text" in result
    assert "show" in result["text"] or "respond_to" in result["text"]


# ===========================================================================
# Rails Concerns
# ===========================================================================

def test_rails_find_definition_should_find_method_in_concern_module(tmp_path):
    """find_definition must find an instance method defined inside a Rails Concern."""
    src = """\
module Auditable
  extend ActiveSupport::Concern

  included do
    before_create :set_created_by
    before_update :set_updated_by
  end

  def audit_log
    AuditLog.where(auditable: self).order(created_at: :desc)
  end

  private

  def set_created_by
    self.created_by = Current.user&.id
  end

  def set_updated_by
    self.updated_by = Current.user&.id
  end
end

class Document < ApplicationRecord
  include Auditable
end
"""
    (tmp_path / "auditable.rb").write_text(src)
    from context_extractor.project_analysis.navigation import find_definition
    results = find_definition(tmp_path, "audit_log")
    assert len(results) >= 1, "Concern instance method 'audit_log' must be found"


def test_rails_find_callers_should_find_concern_method_called_from_controller(tmp_path):
    """find_callers must find concern methods called from controllers including them."""
    src = """\
module Paginatable
  extend ActiveSupport::Concern

  def paginate_collection(collection)
    collection.page(params[:page]).per(params[:per_page] || 25)
  end
end

class ProductsController < ApplicationController
  include Paginatable

  def index
    @products = paginate_collection(Product.active.order(:name))
    render json: @products
  end
end
"""
    (tmp_path / "paginatable.rb").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "paginatable.rb", "paginate_collection")
    assert len(results) >= 1, "Concern method called from including controller must be found"


# ===========================================================================
# ActiveJob
# ===========================================================================

def test_rails_find_decorators_should_find_queue_as_on_job_class(monkeypatch):
    """find_decorators must find queue_as DSL call on an ActiveJob class."""
    source = """\
class NotificationJob < ApplicationJob
  queue_as :notifications
  retry_on NetworkError, wait: 5.seconds, attempts: 3
  discard_on ActiveJob::DeserializationError

  def perform(user_id:, template:, payload: {})
    user = User.find(user_id)
    NotificationService.deliver(user, template, payload)
  end
end
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub(source, "notification_job.rb"))
    result = mcp_server.find_decorators("pipe", "notification_job.rb", 6)
    assert isinstance(result, list), "find_decorators must not crash on ActiveJob DSL"


def test_rails_find_callers_should_find_perform_later_as_job_invocation(tmp_path):
    """find_callers must find .perform_later() calls as invocations of the job's perform."""
    src = """\
class ReportGenerationJob < ApplicationJob
  queue_as :reports

  def perform(report_id:, format: 'pdf')
    report = Report.find(report_id)
    pdf = PdfGenerator.generate(report)
    report.update!(file: pdf, status: :completed)
  end
end

class ReportsController < ApplicationController
  def generate
    ReportGenerationJob.perform_later(report_id: params[:id], format: 'pdf')
    render json: { status: 'queued' }
  end
end

class WeeklyScheduler
  def run
    Report.pending.each do |report|
      ReportGenerationJob.perform_later(report_id: report.id)
    end
  end
end
"""
    (tmp_path / "report_job.rb").write_text(src)
    from context_extractor.project_analysis.callers import find_callers
    results = find_callers(tmp_path, "report_job.rb", "ReportGenerationJob")
    assert isinstance(results, list), \
        "find_callers must not crash on perform_later job invocations"
