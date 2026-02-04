# 📋 Task Management REST API

A complete RESTful API for task management system built with Flask, featuring user authentication, comprehensive CRUD operations, filtering, sorting, pagination, and a user-friendly web interface.

## 🚀 Features

- **User Authentication**: JWT-based authentication with registration and login
- **Task Management**: Full CRUD operations for tasks
- **Advanced Filtering**: Filter tasks by status, priority, and search functionality
- **Sorting & Pagination**: Sort by various fields with paginated results
- **Input Validation**: Comprehensive validation with detailed error messages
- **Web Interface**: User-friendly web dashboard for task management
- **API Documentation**: Complete API documentation with examples
- **Testing Suite**: Automated API testing script
- **Error Handling**: Proper HTTP status codes and error responses

## 🛠️ Technology Stack

- **Backend**: Flask 2.3.3
- **Database**: SQLAlchemy with SQLite
- **Authentication**: Flask-JWT-Extended 4.5.3
- **Security**: Werkzeug password hashing
- **Testing**: Python requests library

## 📦 Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd task-management-rest-api
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   python taskManagement.py
   ```

The API will be available at `http://localhost:5000` and the web interface at `http://localhost:5000/`

## 🔐 API Endpoints

### Authentication Endpoints

#### Register User
```http
POST /api/auth/register
Content-Type: application/json

{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "securepassword123"
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "johndoe",
  "password": "securepassword123"
}
```

#### Refresh Token
```http
POST /api/auth/refresh
Authorization: Bearer <refresh_token>
```

### Task Endpoints

#### Get Tasks (with filtering and pagination)
```http
GET /api/tasks?page=1&per_page=10&status=pending&priority=high&sort_by=due_date&sort_order=asc&search=project
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `page`: Page number (default: 1)
- `per_page`: Items per page (default: 10)
- `status`: Filter by status (pending, in_progress, completed)
- `priority`: Filter by priority (low, medium, high)
- `search`: Search in title and description
- `sort_by`: Sort field (created_at, due_date, priority, title)
- `sort_order`: Sort order (asc, desc)

#### Create Task
```http
POST /api/tasks
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "Complete API Documentation",
  "description": "Write comprehensive API documentation with examples",
  "status": "in_progress",
  "priority": "high",
  "due_date": "2024-02-15T23:59:59"
}
```

#### Get Single Task
```http
GET /api/tasks/{task_id}
Authorization: Bearer <access_token>
```

#### Update Task
```http
PUT /api/tasks/{task_id}
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "Updated Task Title",
  "status": "completed",
  "description": "Updated description"
}
```

#### Delete Task
```http
DELETE /api/tasks/{task_id}
Authorization: Bearer <access_token>
```

## 🌐 Web Interface

The application includes a user-friendly web interface accessible at the root URL:

- **Home Page** (`/`): Landing page with registration/login options
- **Registration** (`/register`): User registration form
- **Login** (`/login`): User authentication form
- **Dashboard** (`/dashboard`): Task management dashboard
- **Create Task** (`/create-task`): Form to create new tasks
- **Edit Task** (`/edit-task/<task_id>`): Form to edit existing tasks

## 🧪 Testing

Run the comprehensive API test suite:

```bash
python test_api.py
```

The test suite covers:
- User registration and authentication
- Task CRUD operations
- Filtering and pagination
- Error handling scenarios

## 📊 API Response Format

### Success Response
```json
{
  "status": "success",
  "data": {
    "message": "Operation completed successfully",
    "task": {
      "id": 1,
      "title": "Sample Task",
      "description": "Task description",
      "status": "pending",
      "priority": "medium",
      "due_date": "2024-02-15T23:59:59",
      "created_at": "2024-01-25T10:30:00Z",
      "updated_at": "2024-01-25T10:30:00Z"
    }
  }
}
```

### Error Response
```json
{
  "status": "error",
  "message": "Validation failed",
  "errors": {
    "title": ["Title is required", "Title must be at least 3 characters"],
    "email": ["Invalid email format"]
  }
}
```

### Paginated Response
```json
{
  "status": "success",
  "data": {
    "tasks": [...],
    "pagination": {
      "page": 1,
      "per_page": 10,
      "total_pages": 5,
      "total_items": 48,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=jwt-secret-key-here
DATABASE_URL=sqlite:///tasks.db
```

### Database

The application uses SQLite by default. The database file `instance/tasks.db` is created automatically when the application runs for the first time.

## 📝 Data Models

### User Model
- `id`: Primary key
- `username`: Unique username
- `email`: Unique email address
- `password_hash`: Hashed password
- `created_at`: Registration timestamp

### Task Model
- `id`: Primary key
- `title`: Task title (required, min 3 characters)
- `description`: Task description (optional)
- `status`: Task status (pending, in_progress, completed)
- `priority`: Task priority (low, medium, high)
- `due_date`: Optional due date (ISO format)
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
- `user_id`: Foreign key to user

## 🛡️ Security Features

- **Password Hashing**: Uses Werkzeug's secure password hashing
- **JWT Authentication**: Stateless authentication with access and refresh tokens
- **Input Validation**: Comprehensive validation for all endpoints
- **SQL Injection Protection**: SQLAlchemy ORM prevents SQL injection
- **CORS Ready**: Configurable CORS settings for cross-origin requests

## 🚀 Deployment

### Local Development
```bash
export FLASK_ENV=development
python taskManagement.py
```

### Production Deployment
1. Set environment variables for production
2. Use a production WSGI server (gunicorn, uwsgi)
3. Configure a production database (PostgreSQL recommended)
4. Set up proper logging and monitoring

## 📚 Project Structure

```
task-management-rest-api/
├── taskManagement.py          # Main application file
├── requirements.txt           # Python dependencies
├── test_api.py               # API testing suite
├── Problem Statement.md      # Project requirements
├── README.md                 # This file
└── instance/
    └── tasks.db             # SQLite database
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new features
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For questions or issues, please open an issue on the GitHub repository.

---

**Built with ❤️ using Flask and modern web development practices.**
