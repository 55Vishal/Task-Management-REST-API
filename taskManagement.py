from flask import Flask, request, jsonify, make_response, render_template_string, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, create_refresh_token, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import os
import re

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-key')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///tasks.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
jwt = JWTManager(app)

class User(db.Model):
    """
    User model for authentication and task ownership.

    Attributes:
        id: Unique identifier
        username: Unique username for login
        email: User's email address
        password_hash: Hashed password for security
        created_at: Account creation timestamp
        tasks: Relationship to user's tasks
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tasks = db.relationship('Task', backref='user', lazy=True)

    def set_password(self, password):
        """Hash and set the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify the provided password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Convert user object to dictionary for API responses."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat()
        }

class Task(db.Model):
    """
    Task model representing individual tasks in the system.

    Attributes:
        id: Unique identifier
        title: Task title
        description: Detailed task description
        status: Current status (pending, in_progress, completed)
        priority: Task priority (low, medium, high)
        due_date: Optional due date
        created_at: Task creation timestamp
        updated_at: Last update timestamp
        user_id: Foreign key to owning user
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    priority = db.Column(db.String(10), default='medium')
    due_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def to_dict(self):
        """Convert task object to dictionary for API responses."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'priority': self.priority,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

def validate_registration_data(data):
    """
    Validate user registration data.

    Args:
        data: Dictionary containing username, email, password

    Returns:
        dict: {'valid': bool, 'errors': dict of field errors}
    """
    errors = {}

    if not data.get('username'):
        errors['username'] = ['Username is required']
    elif len(data['username']) < 3:
        errors['username'] = ['Username must be at least 3 characters']
    elif not re.match(r'^[a-zA-Z0-9_]+$', data['username']):
        errors['username'] = ['Username can only contain letters, numbers, and underscores']

    if not data.get('email'):
        errors['email'] = ['Email is required']
    elif not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', data['email']):
        errors['email'] = ['Invalid email format']

    if not data.get('password'):
        errors['password'] = ['Password is required']
    elif len(data['password']) < 6:
        errors['password'] = ['Password must be at least 6 characters']

    return {'valid': len(errors) == 0, 'errors': errors}

def validate_task_data(data, update=False):
    """
    Validate task data for creation or update.

    Args:
        data: Dictionary containing task fields
        update: Boolean indicating if this is an update operation

    Returns:
        dict: {'valid': bool, 'errors': dict of field errors}
    """
    errors = {}

    if not update or 'title' in data:
        if not data.get('title'):
            errors['title'] = ['Title is required']
        elif len(data['title']) < 3:
            errors['title'] = ['Title must be at least 3 characters']

    if 'status' in data:
        valid_statuses = ['pending', 'in_progress', 'completed']
        if data['status'] not in valid_statuses:
            errors['status'] = [f'Status must be one of: {", ".join(valid_statuses)}']

    if 'priority' in data:
        valid_priorities = ['low', 'medium', 'high']
        if data['priority'] not in valid_priorities:
            errors['priority'] = [f'Priority must be one of: {", ".join(valid_priorities)}']

    if 'due_date' in data and data['due_date']:
        try:
            datetime.fromisoformat(data['due_date'].replace('Z', '+00:00'))
        except ValueError:
            errors['due_date'] = ['Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)']

    return {'valid': len(errors) == 0, 'errors': errors}

def get_filtered_tasks(user_id, filters):
    """
    Get filtered and sorted tasks for a user.

    Args:
        user_id: ID of the user
        filters: Dictionary containing filter parameters

    Returns:
        SQLAlchemy query object
    """
    query = Task.query.filter_by(user_id=user_id)

    # Apply filters
    if filters.get('status'):
        query = query.filter_by(status=filters['status'])
    if filters.get('priority'):
        query = query.filter_by(priority=filters['priority'])
    if filters.get('search'):
        search_term = f"%{filters['search']}%"
        query = query.filter(
            db.or_(
                Task.title.ilike(search_term),
                Task.description.ilike(search_term)
            )
        )

    # Apply sorting
    sort_by = filters.get('sort_by', 'created_at')
    sort_order = filters.get('sort_order', 'desc')

    if hasattr(Task, sort_by):
        column = getattr(Task, sort_by)
        if sort_order == 'desc':
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())

    return query


@app.route('/api/auth/register', methods=['POST'])
def register():
    """
    Register a new user account.

    Request Body:
        {
            "username": "string",
            "email": "string",
            "password": "string"
        }

    Returns:
        JSON response with user data and tokens
    """
    data = request.get_json()

    validation = validate_registration_data(data)
    if not validation['valid']:
        return make_response(jsonify({
            'status': 'error',
            'message': 'Validation failed',
            'errors': validation['errors']
        }), 400)

    # Check if user already exists
    if User.query.filter_by(username=data['username']).first():
        return make_response(jsonify({
            'status': 'error',
            'message': 'Username already exists'
        }), 409)

    if User.query.filter_by(email=data['email']).first():
        return make_response(jsonify({
            'status': 'error',
            'message': 'Email already exists'
        }), 409)

    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])

    db.session.add(user)
    db.session.commit()

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return make_response(jsonify({
        'status': 'success',
        'data': {
            'message': 'User registered successfully',
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        }
    }), 201)

@app.route('/api/auth/login', methods=['POST'])
def login():
    """
    Authenticate user and return access tokens.

    Request Body:
        {
            "username": "string",
            "password": "string"
        }

    Returns:
        JSON response with tokens
    """
    data = request.get_json()

    if not data or not data.get('username') or not data.get('password'):
        return make_response(jsonify({
            'status': 'error',
            'message': 'Username and password are required'
        }), 400)

    user = User.query.filter_by(username=data['username']).first()

    if not user or not user.check_password(data['password']):
        return make_response(jsonify({
            'status': 'error',
            'message': 'Invalid username or password'
        }), 401)

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return make_response(jsonify({
        'status': 'success',
        'data': {
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token
        }
    }), 200)

@app.route('/api/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_token():
    """
    Refresh access token using refresh token.

    Returns:
        JSON response with new access token
    """
    current_user_id = get_jwt_identity()
    access_token = create_access_token(identity=current_user_id)

    return make_response(jsonify({
        'status': 'success',
        'data': {
            'access_token': access_token
        }
    }), 200)

# Task Routes
@app.route('/api/tasks', methods=['GET'])
@jwt_required()
def get_tasks():
    """
    Get paginated list of user's tasks with filtering and sorting.

    Query Parameters:
        page: Page number (default: 1)
        per_page: Items per page (default: 10)
        status: Filter by status
        priority: Filter by priority
        search: Search in title and description
        sort_by: Sort field (default: created_at)
        sort_order: Sort order (asc/desc, default: desc)

    Returns:
        JSON response with tasks and pagination info
    """
    current_user_id = get_jwt_identity()

    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    filters = {
        'status': request.args.get('status'),
        'priority': request.args.get('priority'),
        'search': request.args.get('search'),
        'sort_by': request.args.get('sort_by', 'created_at'),
        'sort_order': request.args.get('sort_order', 'desc')
    }

    # Get filtered and sorted query
    query = get_filtered_tasks(current_user_id, filters)

    # Paginate results
    paginated_tasks = query.paginate(page=page, per_page=per_page, error_out=False)

    # Prepare response
    tasks_data = [task.to_dict() for task in paginated_tasks.items]

    return make_response(jsonify({
        'status': 'success',
        'data': {
            'tasks': tasks_data,
            'pagination': {
                'page': paginated_tasks.page,
                'per_page': paginated_tasks.per_page,
                'total_pages': paginated_tasks.pages,
                'total_items': paginated_tasks.total,
                'has_next': paginated_tasks.has_next,
                'has_prev': paginated_tasks.has_prev
            }
        }
    }), 200)

@app.route('/api/tasks', methods=['POST'])
@jwt_required()
def create_task():
    """
    Create a new task for the authenticated user.

    Request Body:
        {
            "title": "string",
            "description": "string (optional)",
            "status": "pending|in_progress|completed (optional)",
            "priority": "low|medium|high (optional)",
            "due_date": "ISO date string (optional)"
        }

    Returns:
        JSON response with created task
    """
    current_user_id = get_jwt_identity()
    data = request.get_json()

    # Validate input
    validation = validate_task_data(data)
    if not validation['valid']:
        return make_response(jsonify({
            'status': 'error',
            'message': 'Validation failed',
            'errors': validation['errors']
        }), 400)

    # Create task
    task = Task(
        title=data['title'],
        description=data.get('description', ''),
        status=data.get('status', 'pending'),
        priority=data.get('priority', 'medium'),
        due_date=datetime.fromisoformat(data['due_date'].replace('Z', '+00:00')) if data.get('due_date') else None,
        user_id=current_user_id
    )

    db.session.add(task)
    db.session.commit()

    return make_response(jsonify({
        'status': 'success',
        'data': {
            'message': 'Task created successfully',
            'task': task.to_dict()
        }
    }), 201)

@app.route('/api/tasks/<int:task_id>', methods=['GET'])
@jwt_required()
def get_task(task_id):
    """
    Get a specific task by ID.

    Args:
        task_id: ID of the task to retrieve

    Returns:
        JSON response with task data
    """
    current_user_id = get_jwt_identity()

    task = Task.query.filter_by(id=task_id, user_id=current_user_id).first()

    if not task:
        return make_response(jsonify({
            'status': 'error',
            'message': 'Task not found'
        }), 404)

    return make_response(jsonify({
        'status': 'success',
        'data': {
            'task': task.to_dict()
        }
    }), 200)

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@jwt_required()
def update_task(task_id):
    """
    Update an existing task.

    Args:
        task_id: ID of the task to update

    Request Body:
        Same as create, but all fields optional

    Returns:
        JSON response with updated task
    """
    current_user_id = get_jwt_identity()
    data = request.get_json()

    task = Task.query.filter_by(id=task_id, user_id=current_user_id).first()

    if not task:
        return make_response(jsonify({
            'status': 'error',
            'message': 'Task not found'
        }), 404)

    # Validate input
    validation = validate_task_data(data, update=True)
    if not validation['valid']:
        return make_response(jsonify({
            'status': 'error',
            'message': 'Validation failed',
            'errors': validation['errors']
        }), 400)

    # Update fields
    if 'title' in data:
        task.title = data['title']
    if 'description' in data:
        task.description = data['description']
    if 'status' in data:
        task.status = data['status']
    if 'priority' in data:
        task.priority = data['priority']
    if 'due_date' in data:
        task.due_date = datetime.fromisoformat(data['due_date'].replace('Z', '+00:00')) if data['due_date'] else None

    db.session.commit()

    return make_response(jsonify({
        'status': 'success',
        'data': {
            'message': 'Task updated successfully',
            'task': task.to_dict()
        }
    }), 200)

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@jwt_required()
def delete_task(task_id):
    """
    Delete a task.

    Args:
        task_id: ID of the task to delete

    Returns:
        JSON response confirming deletion
    """
    current_user_id = get_jwt_identity()

    task = Task.query.filter_by(id=task_id, user_id=current_user_id).first()

    if not task:
        return make_response(jsonify({
            'status': 'error',
            'message': 'Task not found'
        }), 404)

    db.session.delete(task)
    db.session.commit()

    return make_response(jsonify({
        'status': 'success',
        'data': {
            'message': 'Task deleted successfully'
        }
    }), 204)

# =============================================================================
# 5.5 WEB INTERFACE ROUTES
# =============================================================================

# Login required decorator for web routes
def login_required_web(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('web_login'))
        return f(*args, **kwargs)
    return decorated_function

# Home page
@app.route('/')
def index():
    """Home page with login/register options."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Task Management System</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .container { background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 500px; width: 100%; text-align: center; }
            h1 { color: #333; margin-bottom: 1rem; }
            p { color: #666; margin-bottom: 2rem; }
            .btn { display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 0 10px; transition: background 0.3s; }
            .btn:hover { background: #5a6fd8; }
            .btn.secondary { background: #6c757d; }
            .btn.secondary:hover { background: #5a6268; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📋 Task Management System</h1>
            <p>Organize your tasks efficiently with our comprehensive task management platform.</p>
            <a href="{{ url_for('web_register') }}" class="btn">Register</a>
            <a href="{{ url_for('web_login') }}" class="btn secondary">Login</a>
        </div>
    </body>
    </html>
    """)

# Register page
@app.route('/register', methods=['GET', 'POST'])
def web_register():
    """Web registration page."""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Basic validation
        if not all([username, email, password, confirm_password]):
            flash('All fields are required.', 'error')
            return redirect(url_for('web_register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('web_register'))

        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('web_register'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return redirect(url_for('web_register'))

        # Create user
        user = User(username=username, email=email)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('web_login'))

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Register - Task Management</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .container { background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 400px; width: 100%; }
            h1 { color: #333; text-align: center; margin-bottom: 1.5rem; }
            .form-group { margin-bottom: 1rem; }
            label { display: block; margin-bottom: 0.5rem; color: #555; }
            input[type="text"], input[type="email"], input[type="password"] { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; }
            .btn { width: 100%; padding: 12px; background: #667eea; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; margin-top: 1rem; }
            .btn:hover { background: #5a6fd8; }
            .link { text-align: center; margin-top: 1rem; }
            .link a { color: #667eea; text-decoration: none; }
            .alert { padding: 10px; border-radius: 5px; margin-bottom: 1rem; }
            .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📝 Register</h1>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ 'success' if category == 'success' else 'error' }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <form method="POST">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                </div>
                <div class="form-group">
                    <label for="email">Email</label>
                    <input type="email" id="email" name="email" required>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <div class="form-group">
                    <label for="confirm_password">Confirm Password</label>
                    <input type="password" id="confirm_password" name="confirm_password" required>
                </div>
                <button type="submit" class="btn">Register</button>
            </form>
            <div class="link">
                <a href="{{ url_for('web_login') }}">Already have an account? Login</a>
            </div>
        </div>
    </body>
    </html>
    """)

# Login page
@app.route('/login', methods=['GET', 'POST'])
def web_login():
    """Web login page."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not all([username, password]):
            flash('Username and password are required.', 'error')
            return redirect(url_for('web_login'))

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('web_login'))

        session['user_id'] = user.id
        session['username'] = user.username
        flash('Login successful!', 'success')
        return redirect(url_for('dashboard'))

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login - Task Management</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .container { background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 400px; width: 100%; }
            h1 { color: #333; text-align: center; margin-bottom: 1.5rem; }
            .form-group { margin-bottom: 1rem; }
            label { display: block; margin-bottom: 0.5rem; color: #555; }
            input[type="text"], input[type="password"] { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; }
            .btn { width: 100%; padding: 12px; background: #667eea; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; margin-top: 1rem; }
            .btn:hover { background: #5a6fd8; }
            .link { text-align: center; margin-top: 1rem; }
            .link a { color: #667eea; text-decoration: none; }
            .alert { padding: 10px; border-radius: 5px; margin-bottom: 1rem; }
            .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔑 Login</h1>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ 'success' if category == 'success' else 'error' }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <form method="POST">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="btn">Login</button>
            </form>
            <div class="link">
                <a href="{{ url_for('web_register') }}">Don't have an account? Register</a>
            </div>
        </div>
    </body>
    </html>
    """)

# Dashboard
@app.route('/dashboard')
@login_required_web
def dashboard():
    """User dashboard to view and manage tasks."""
    user_id = session['user_id']
    user = User.query.get(user_id)

    # Get user's tasks
    tasks = Task.query.filter_by(user_id=user_id).order_by(Task.created_at.desc()).all()

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard - Task Management</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
            .header { background: #667eea; color: white; padding: 1rem; display: flex; justify-content: space-between; align-items: center; }
            .header h1 { margin: 0; }
            .logout-btn { background: #dc3545; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; }
            .logout-btn:hover { background: #c82333; }
            .container { max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
            .welcome { background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 2rem; }
            .actions { display: flex; gap: 1rem; margin-bottom: 2rem; }
            .btn { padding: 12px 24px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; display: inline-block; }
            .btn:hover { background: #218838; }
            .btn-secondary { background: #6c757d; }
            .btn-secondary:hover { background: #5a6268; }
            .tasks-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }
            .task-card { background: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .task-title { font-size: 1.2rem; font-weight: bold; margin-bottom: 0.5rem; }
            .task-description { color: #666; margin-bottom: 1rem; }
            .task-meta { display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; color: #888; }
            .status { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
            .status-pending { background: #fff3cd; color: #856404; }
            .status-in_progress { background: #cce5ff; color: #004085; }
            .status-completed { background: #d4edda; color: #155724; }
            .priority { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
            .priority-low { background: #e2e3e5; color: #383d41; }
            .priority-medium { background: #fff3cd; color: #856404; }
            .priority-high { background: #f8d7da; color: #721c24; }
            .no-tasks { text-align: center; color: #666; font-style: italic; padding: 2rem; }
            .alert { padding: 10px; border-radius: 5px; margin-bottom: 1rem; }
            .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📋 Task Management Dashboard</h1>
            <a href="{{ url_for('logout') }}" class="logout-btn">Logout</a>
        </div>
        <div class="container">
            <div class="welcome">
                <h2>Welcome, {{ user.username }}!</h2>
                <p>Manage your tasks efficiently.</p>
            </div>

            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ 'success' if category == 'success' else 'error' }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}

            <div class="actions">
                <a href="{{ url_for('create_task_web') }}" class="btn">➕ Create New Task</a>
                <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">🔄 Refresh Tasks</a>
            </div>

            <h3>Your Tasks</h3>
            {% if tasks %}
            <div class="tasks-grid">
                {% for task in tasks %}
                <div class="task-card">
                    <div class="task-title">{{ task.title }}</div>
                    <div class="task-description">{{ task.description or 'No description' }}</div>
                    <div class="task-meta">
                        <span class="status status-{{ task.status }}">{{ task.status.replace('_', ' ').title() }}</span>
                        <span class="priority priority-{{ task.priority }}">{{ task.priority.title() }}</span>
                    </div>
                    {% if task.due_date %}
                    <div class="task-meta">
                        <small>Due: {{ task.due_date.strftime('%Y-%m-%d') }}</small>
                    </div>
                    {% endif %}
                    <div style="margin-top: 1rem;">
                        <a href="{{ url_for('edit_task', task_id=task.id) }}" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.9rem;">Edit</a>
                        <a href="{{ url_for('delete_task_web', task_id=task.id) }}" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.9rem; background: #dc3545;" onclick="return confirm('Are you sure you want to delete this task?')">Delete</a>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="no-tasks">
                <p>You don't have any tasks yet. <a href="{{ url_for('create_task_web') }}">Create your first task</a>!</p>
            </div>
            {% endif %}
        </div>
    </body>
    </html>
    """, user=user, tasks=tasks)

# Create task page
@app.route('/create-task', methods=['GET', 'POST'])
@login_required_web
def create_task_web():
    """Create a new task."""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        status = request.form.get('status', 'pending')
        priority = request.form.get('priority', 'medium')
        due_date = request.form.get('due_date')

        if not title:
            flash('Title is required.', 'error')
            return redirect(url_for('create_task_web'))

        # Create task
        task = Task(
            title=title,
            description=description,
            status=status,
            priority=priority,
            due_date=datetime.fromisoformat(due_date) if due_date else None,
            user_id=session['user_id']
        )

        db.session.add(task)
        db.session.commit()

        flash('Task created successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Create Task - Task Management</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
            .header { background: #667eea; color: white; padding: 1rem; }
            .header h1 { margin: 0; }
            .container { max-width: 600px; margin: 2rem auto; padding: 0 1rem; }
            .form-card { background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .form-group { margin-bottom: 1rem; }
            label { display: block; margin-bottom: 0.5rem; color: #555; font-weight: bold; }
            input[type="text"], textarea, select, input[type="date"] { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; }
            textarea { resize: vertical; min-height: 100px; }
            .btn { padding: 12px 24px; background: #28a745; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; }
            .btn:hover { background: #218838; }
            .btn-secondary { background: #6c757d; margin-left: 1rem; }
            .btn-secondary:hover { background: #5a6268; }
            .alert { padding: 10px; border-radius: 5px; margin-bottom: 1rem; }
            .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>➕ Create New Task</h1>
        </div>
        <div class="container">
            <div class="form-card">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'success' if category == 'success' else 'error' }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                <form method="POST">
                    <div class="form-group">
                        <label for="title">Title *</label>
                        <input type="text" id="title" name="title" required>
                    </div>
                    <div class="form-group">
                        <label for="description">Description</label>
                        <textarea id="description" name="description"></textarea>
                    </div>
                    <div class="form-group">
                        <label for="status">Status</label>
                        <select id="status" name="status">
                            <option value="pending">Pending</option>
                            <option value="in_progress">In Progress</option>
                            <option value="completed">Completed</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="priority">Priority</label>
                        <select id="priority" name="priority">
                            <option value="low">Low</option>
                            <option value="medium">Medium</option>
                            <option value="high">High</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="due_date">Due Date</label>
                        <input type="date" id="due_date" name="due_date">
                    </div>
                    <button type="submit" class="btn">Create Task</button>
                    <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">Cancel</a>
                </form>
            </div>
        </div>
    </body>
    </html>
    """)

# Edit task page
@app.route('/edit-task/<int:task_id>', methods=['GET', 'POST'])
@login_required_web
def edit_task(task_id):
    """Edit an existing task."""
    task = Task.query.filter_by(id=task_id, user_id=session['user_id']).first()

    if not task:
        flash('Task not found.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        status = request.form.get('status')
        priority = request.form.get('priority')
        due_date = request.form.get('due_date')

        if not title:
            flash('Title is required.', 'error')
            return redirect(url_for('edit_task', task_id=task_id))

        # Update task
        task.title = title
        task.description = description
        task.status = status
        task.priority = priority
        task.due_date = datetime.fromisoformat(due_date) if due_date else None

        db.session.commit()

        flash('Task updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Edit Task - Task Management</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
            .header { background: #667eea; color: white; padding: 1rem; }
            .header h1 { margin: 0; }
            .container { max-width: 600px; margin: 2rem auto; padding: 0 1rem; }
            .form-card { background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .form-group { margin-bottom: 1rem; }
            label { display: block; margin-bottom: 0.5rem; color: #555; font-weight: bold; }
            input[type="text"], textarea, select, input[type="date"] { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; }
            textarea { resize: vertical; min-height: 100px; }
            .btn { padding: 12px 24px; background: #28a745; color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; }
            .btn:hover { background: #218838; }
            .btn-secondary { background: #6c757d; margin-left: 1rem; }
            .btn-secondary:hover { background: #5a6268; }
            .alert { padding: 10px; border-radius: 5px; margin-bottom: 1rem; }
            .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>✏️ Edit Task</h1>
        </div>
        <div class="container">
            <div class="form-card">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'success' if category == 'success' else 'error' }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                <form method="POST">
                    <div class="form-group">
                        <label for="title">Title *</label>
                        <input type="text" id="title" name="title" value="{{ task.title }}" required>
                    </div>
                    <div class="form-group">
                        <label for="description">Description</label>
                        <textarea id="description" name="description">{{ task.description or '' }}</textarea>
                    </div>
                    <div class="form-group">
                        <label for="status">Status</label>
                        <select id="status" name="status">
                            <option value="pending" {% if task.status == 'pending' %}selected{% endif %}>Pending</option>
                            <option value="in_progress" {% if task.status == 'in_progress' %}selected{% endif %}>In Progress</option>
                            <option value="completed" {% if task.status == 'completed' %}selected{% endif %}>Completed</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="priority">Priority</label>
                        <select id="priority" name="priority">
                            <option value="low" {% if task.priority == 'low' %}selected{% endif %}>Low</option>
                            <option value="medium" {% if task.priority == 'medium' %}selected{% endif %}>Medium</option>
                            <option value="high" {% if task.priority == 'high' %}selected{% endif %}>High</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="due_date">Due Date</label>
                        <input type="date" id="due_date" name="due_date" value="{{ task.due_date.strftime('%Y-%m-%d') if task.due_date else '' }}">
                    </div>
                    <button type="submit" class="btn">Update Task</button>
                    <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">Cancel</a>
                </form>
            </div>
        </div>
    </body>
    </html>
    """, task=task)

# Delete task
@app.route('/delete-task/<int:task_id>')
@login_required_web
def delete_task_web(task_id):
    """Delete a task."""
    task = Task.query.filter_by(id=task_id, user_id=session['user_id']).first()

    if not task:
        flash('Task not found.', 'error')
        return redirect(url_for('dashboard'))

    db.session.delete(task)
    db.session.commit()

    flash('Task deleted successfully!', 'success')
    return redirect(url_for('dashboard'))

# Logout
@app.route('/logout')
def logout():
    """Logout user."""
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.errorhandler(400)
def bad_request(error):
    """Handle 400 Bad Request errors."""
    return make_response(jsonify({
        'status': 'error',
        'message': 'Bad request'
    }), 400)

@app.errorhandler(401)
def unauthorized(error):
    """Handle 401 Unauthorized errors."""
    return make_response(jsonify({
        'status': 'error',
        'message': 'Unauthorized access'
    }), 401)

@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found errors."""
    return make_response(jsonify({
        'status': 'error',
        'message': 'Resource not found'
    }), 404)

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server Error."""
    db.session.rollback()
    return make_response(jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500)

# =============================================================================
# 7. MAIN APPLICATION SETUP
# =============================================================================

if __name__ == '__main__':
    # Create database tables
    with app.app_context():
        db.create_all()

    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5000)

"""
API DOCUMENTATION
=================

Authentication Endpoints:
- POST /api/auth/register - Register new user
- POST /api/auth/login - Login and get tokens
- POST /api/auth/refresh - Refresh access token

Task Endpoints:
- GET /api/tasks - List tasks with filtering/pagination
- POST /api/tasks - Create new task
- GET /api/tasks/<id> - Get specific task
- PUT /api/tasks/<id> - Update task
- DELETE /api/tasks/<id> - Delete task

Usage Examples:
1. Register: POST /api/auth/register with {"username": "test", "email": "test@example.com", "password": "password123"}
2. Login: POST /api/auth/login with {"username": "test", "password": "password123"}
3. Create Task: POST /api/tasks with Authorization header and {"title": "My Task", "description": "Task details"}
4. Get Tasks: GET /api/tasks with Authorization header

To run: python taskManagement.py
"""
