import sqlite3
import hashlib
import secrets
import json
import os
from datetime import datetime
from functools import wraps
from flask import session, redirect, url_for, flash

class UserManager:
    """User management with superadmin and per-lab admins."""
    
    def __init__(self, config_path='config.json', reset_db=False):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.db_path = 'users.db'
        # Allow reset via param or env var
        self.reset_db = reset_db or os.environ.get('RESET_USERS_DB', '0') == '1'
        self.init_database()
    
    def init_database(self):
        """Initialize or reset user database with required schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if self.reset_db:
            cursor.execute('DROP TABLE IF EXISTS users')
            conn.commit()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_superadmin INTEGER DEFAULT 0,
                lab_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # Ensure columns exist if table pre-existed (simple online migration)
        cursor.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'is_superadmin' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_superadmin INTEGER DEFAULT 0')
        if 'lab_id' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN lab_id TEXT')
        conn.commit()
        
        # Create default superadmin if none exists
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_superadmin = 1')
        if cursor.fetchone()[0] == 0:
            admin_password_hash = self.hash_password('admin123')
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, is_superadmin, lab_id)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin', 'admin@example.com', admin_password_hash, 1, None))
            print("✓ Created default superadmin: admin / admin123")
        
        conn.commit()
        conn.close()
    
    def hash_password(self, password):
        """Hash password using SHA-256 with salt."""
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}${pwd_hash}"
    
    def verify_password(self, password, password_hash):
        """Verify password against stored hash."""
        try:
            salt, pwd_hash = password_hash.split('$')
            return hashlib.sha256((password + salt).encode()).hexdigest() == pwd_hash
        except:
            return False
    
    def authenticate(self, username, password):
        """Authenticate user and return profile including lab scope."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, email, password_hash, is_superadmin, lab_id
            FROM users WHERE username = ?
        ''', (username,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return (False, 'Invalid username or password', None)
        
        user_id, username, email, password_hash, is_superadmin, lab_id = user
        
        if not self.verify_password(password, password_hash):
            conn.close()
            return (False, 'Invalid username or password', None)
        
        cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.now(), user_id))
        conn.commit()
        conn.close()
        
        user_data = {
            'id': user_id,
            'username': username,
            'email': email,
            'is_superadmin': is_superadmin == 1,
            'lab_id': lab_id
        }
        return (True, 'Login successful', user_data)

    def create_user(self, username, email, password, lab_id=None, is_superadmin=False):
        """Create a new user with optional lab assignment and role."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            pwd_hash = self.hash_password(password)
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, is_superadmin, lab_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, email, pwd_hash, 1 if is_superadmin else 0, lab_id))
            conn.commit()
            return True, 'User created'
        except sqlite3.IntegrityError as e:
            return False, f'Integrity error: {str(e)}'
        finally:
            conn.close()

    def list_users(self):
        """List all users with roles and lab assignments."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, email, is_superadmin, lab_id, created_at, last_login FROM users')
        rows = cursor.fetchall()
        conn.close()
        users = []
        for r in rows:
            users.append({
                'id': r[0], 'username': r[1], 'email': r[2],
                'is_superadmin': r[3] == 1, 'lab_id': r[4],
                'created_at': r[5], 'last_login': r[6]
            })
        return users

    def set_lab_for_user(self, user_id, lab_id):
        """Assign or change a user's lab scope."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET lab_id = ? WHERE id = ?', (lab_id, user_id))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def is_authorized_for_lab(user_session, lab_id):
        """Check if session user is authorized to access the given lab."""
        if not user_session:
            return False
        if user_session.get('is_superadmin'):
            return True
        return user_session.get('lab_id') == lab_id


# Decorator for requiring login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Decorator for admin-only routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in', 'error')
            return redirect(url_for('login'))
        if not session.get('is_superadmin'):
            flash('Superadmin access required', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def lab_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in', 'error')
            return redirect(url_for('login'))
        if session.get('is_superadmin'):
            return f(*args, **kwargs)
        # Lab admins must match lab_id in route args
        route_lab_id = kwargs.get('lab_id') or session.get('lab_id')
        if route_lab_id and session.get('lab_id') == route_lab_id:
            return f(*args, **kwargs)
        flash('Not authorized for this lab', 'error')
        return redirect(url_for('dashboard'))
    return decorated_function