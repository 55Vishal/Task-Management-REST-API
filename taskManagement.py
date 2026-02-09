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
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tasks = db.relationship('Task', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat()
        }

class Task(db.Model):
  
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
    return render_template_string()

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

    return render_template_string()

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

    return render_template_string()

# Dashboard
@app.route('/dashboard')
@login_required_web
def dashboard():
    """User dashboard to view and manage tasks."""
    user_id = session['user_id']
    user = User.query.get(user_id)

    # Get user's tasks
    tasks = Task.query.filter_by(user_id=user_id).order_by(Task.created_at.desc()).all()

    return render_template_string(user=user, tasks=tasks)

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

    return render_template_string()

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

    return render_template_string(task=task)

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


