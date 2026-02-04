

import requests
import json

BASE_URL = 'http://localhost:5000/api'

def test_registration():
    """Test user registration."""
    print("🔐 Testing User Registration...")

    data = {
        "username": "testuser_demo",
        "email": "test_demo@example.com",
        "password": "password123"
    }

    response = requests.post(f'{BASE_URL}/auth/register', json=data)
    print(f"Status Code: {response.status_code}")

    if response.status_code == 201:
        result = response.json()
        print("✅ Registration successful!")
        print(f"User: {result['data']['user']['username']}")
        return result['data']['access_token']
    else:
        print("❌ Registration failed:")
        print(response.json())
        return None

def test_login():
    """Test user login."""
    print("\n🔑 Testing User Login...")

    data = {
        "username": "testuser",
        "password": "password123"
    }

    response = requests.post(f'{BASE_URL}/auth/login', json=data)
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("✅ Login successful!")
        return result['data']['access_token']
    else:
        print("❌ Login failed:")
        print(response.json())
        return None

def test_create_task(token):
    """Test task creation."""
    print("\n📝 Testing Task Creation...")

    headers = {'Authorization': f'Bearer {token}'}
    data = {
        "title": "Complete API Project",
        "description": "Finish the task management REST API implementation",
        "status": "in_progress",
        "priority": "high",
        "due_date": "2024-02-15T23:59:59"
    }

    response = requests.post(f'{BASE_URL}/tasks', json=data, headers=headers)
    print(f"Status Code: {response.status_code}")

    if response.status_code == 201:
        result = response.json()
        print("✅ Task created successfully!")
        print(f"Task: {result['data']['task']['title']}")
        return result['data']['task']['id']
    else:
        print("❌ Task creation failed:")
        print(response.json())
        return None

def test_get_tasks(token):
    """Test getting tasks list."""
    print("\n📋 Testing Get Tasks...")

    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(f'{BASE_URL}/tasks', headers=headers)
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("✅ Tasks retrieved successfully!")
        print(f"Total tasks: {result['data']['pagination']['total_items']}")
        for task in result['data']['tasks']:
            print(f"  - {task['title']} ({task['status']})")
    else:
        print("❌ Failed to get tasks:")
        print(response.json())

def test_update_task(token, task_id):
    """Test task update."""
    print(f"\n✏️  Testing Task Update (ID: {task_id})...")

    headers = {'Authorization': f'Bearer {token}'}
    data = {
        "status": "completed",
        "description": "Updated: Finish the task management REST API implementation with all features"
    }

    response = requests.put(f'{BASE_URL}/tasks/{task_id}', json=data, headers=headers)
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("✅ Task updated successfully!")
        print(f"New status: {result['data']['task']['status']}")
    else:
        print("❌ Task update failed:")
        print(response.json())

def test_delete_task(token, task_id):
    """Test task deletion."""
    print(f"\n🗑️  Testing Task Deletion (ID: {task_id})...")

    headers = {'Authorization': f'Bearer {token}'}
    response = requests.delete(f'{BASE_URL}/tasks/{task_id}', headers=headers)
    print(f"Status Code: {response.status_code}")

    if response.status_code == 204:
        print("✅ Task deleted successfully!")
    else:
        print("❌ Task deletion failed:")
        print(response.json())

def test_create_multiple_tasks(token):
    """Test creating multiple tasks."""
    print("\n📝 Testing Multiple Task Creation...")

    tasks_data = [
        {
            "title": "Complete API Project",
            "description": "Finish the task management REST API implementation",
            "status": "in_progress",
            "priority": "high",
            "due_date": "2024-02-15T23:59:59"
        },
        {
            "title": "Write Documentation",
            "description": "Create comprehensive API documentation with examples",
            "status": "pending",
            "priority": "medium",
            "due_date": "2024-02-20T17:00:00"
        },
        {
            "title": "Setup Testing Environment",
            "description": "Configure automated testing and CI/CD pipeline",
            "status": "completed",
            "priority": "low",
            "due_date": "2024-02-10T12:00:00"
        }
    ]

    task_ids = []
    headers = {'Authorization': f'Bearer {token}'}

    for i, task_data in enumerate(tasks_data, 1):
        print(f"Creating Task {i}...")
        response = requests.post(f'{BASE_URL}/tasks', json=task_data, headers=headers)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 201:
            result = response.json()
            print(f"✅ Task {i} created: {result['data']['task']['title']}")
            task_ids.append(result['data']['task']['id'])
        else:
            print(f"❌ Task {i} creation failed:")
            print(response.json())

    return task_ids

def main():
    """Run all API tests."""
    print("🚀 Task Management API Test Suite")
    print("=" * 40)

    # Test registration (skip if user exists)
    token = test_registration()
    if not token:
        # Try login instead
        token = test_login()

    if not token:
        print("❌ Cannot proceed without authentication token")
        return

    # Test task operations - Create three tasks
    task_ids = test_create_multiple_tasks(token)

    # Display all tasks
    print("\n" + "="*50)
    print("📋 DISPLAYING ALL TASKS")
    print("="*50)
    test_get_tasks(token)

    # Optional: Test update and delete on first task
    if task_ids:
        print("\n" + "="*50)
        print("🔄 TESTING UPDATE AND DELETE OPERATIONS")
        print("="*50)
        test_update_task(token, task_ids[0])
        test_delete_task(token, task_ids[0])

        # Display tasks after deletion
        print("\n" + "="*50)
        print("📋 TASKS AFTER DELETION")
        print("="*50)
        test_get_tasks(token)

    print("\n🎉 API testing completed!")

if __name__ == '__main__':
    main()
