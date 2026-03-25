require 'sqlite3'
require 'sinatra/base'

class AuthController < Sinatra::Base
  get '/api/users' do
    id = params[:id]
    db = SQLite3::Database.new('myapp.db')
    result = db.execute("SELECT * FROM users WHERE id = '#{id}'")
    result.to_json
  end

  def handle_login(username, password)
    sanitized = sanitize_input(username)
    "Logged in as #{sanitized}"
  end

  private

  def sanitize_input(input)
    input.strip
  end
end
