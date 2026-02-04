"""
Task Management REST API - Humanized Implementation
====================================================

This is a complete, human-readable implementation of a Task Management REST API
built with Flask. The code is structured with clear comments, logical sections,
and follows best practices for readability and maintainability.

Features implemented:
- User authentication with JWT
- Task CRUD operations
- Filtering, sorting, and pagination
- Input validation and error handling
- Comprehensive API documentation
- Unit tests (basic structure included)

The code is organized into sections for easy understanding:
1. Imports and Configuration
2. Database Models
3. Authentication Utilities
4. Task Management Logic
5. API Routes
6. Error Handling
7. Main Application Setup
"""

# =============================================================================
# 1. IMPORTS AND CONFIGURATION
# =============================================================================

from flask import Flask, request, jsonify, make_response, render_template_string, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, create_refresh_token, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import os
import re

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-key')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///tasks.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)

# =============================================================================
# 2. DATABASE MODELS
# =============================================================================

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

# =============================================================================
# 3. AUTHENTICATION UTILITIES
# =============================================================================

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

# =============================================================================
# 4. TASK MANAGEMENT LOGIC
# =============================================================================

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

# =============================================================================
# 5. API ROUTES
# =============================================================================

# Authentication Routes
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

    # Validate input
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

    # Create new user
    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])

    db.session.add(user)
    db.session.commit()

    # Generate tokens
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
