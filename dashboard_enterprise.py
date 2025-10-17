import json
import os
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
import hashlib
from user_management import UserManager, login_required, admin_required, lab_access_required

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key-in-production')
socketio = SocketIO(app, cors_allowed_origins="*")

# Global variables
monitor = None
healer = None
database = None
device_manager = None
# Initialize user manager with reset option controlled by env var
user_manager = UserManager(reset_db=(os.environ.get('RESET_USERS_DB', '1') == '1'))

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def save_config(config):
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=2)

# Deprecated admin-only helpers replaced by user_management decorators

def init_dashboard(monitor_instance, healer_instance, database_instance, device_manager_instance=None):
    """Initialize dashboard with monitor, healer, and database instances."""
    global monitor, healer, database, device_manager
    monitor = monitor_instance
    healer = healer_instance
    database = database_instance
    device_manager = device_manager_instance

def run_dashboard(threaded=True):
    """Run the Flask-SocketIO dashboard."""
    config = load_config()
    dashboard_config = config['dashboard']
    
    socketio.run(
        app,
        host=dashboard_config['host'],
        port=dashboard_config['port'],
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )

def broadcast_device_update(ip, status):
    """Broadcast device status update via WebSocket."""
    socketio.emit('device_update', {
        'ip': ip,
        'status': status
    })

# ==================== LOGIN/LOGOUT ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, go to dashboard
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        ok, msg, user = user_manager.authenticate(username, password)
        if ok:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_superadmin'] = user['is_superadmin']
            session['lab_id'] = user['lab_id']
            session.permanent = True
            # On first-time setup with no labs and superadmin, redirect onboarding
            config = load_config()
            if user['is_superadmin'] and len(config.get('labs', {})) == 0:
                return redirect(url_for('onboarding'))
            return redirect(url_for('dashboard'))
        flash(msg, 'error')
    LOGIN_HTML = """
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>Login</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
    :root{--primary:#0A192F;--accent:#00E5FF;--success:#00C853;--error:#FF5252;--text:#E6F1FF;--glass:rgba(255,255,255,0.05);--glass-border:rgba(255,255,255,0.1)}
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:'Inter',sans-serif;background:var(--primary);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center}
    .auth-container{background:var(--glass);backdrop-filter:blur(20px);border:1px solid var(--glass-border);border-radius:24px;padding:50px 40px;width:100%;max-width:420px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}
    .auth-header{text-align:center;margin-bottom:40px}
    .auth-header h1{font-size:2.5rem;font-weight:700;background:linear-gradient(135deg,var(--text) 0%,var(--accent) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:10px}
    .form-group{margin-bottom:25px}
    .form-group label{display:block;margin-bottom:8px;color:rgba(230,241,255,0.8);font-weight:500;font-size:0.9rem}
    .form-group input{width:100%;padding:14px 18px;background:rgba(255,255,255,0.05);border:1px solid var(--glass-border);border-radius:12px;color:var(--text);font-size:1rem;font-family:'Inter',sans-serif;transition:all 0.3s ease}
    .form-group input:focus{outline:none;border-color:var(--accent);background:rgba(255,255,255,0.08);box-shadow:0 0 0 3px rgba(0,229,255,0.1)}
    .btn-primary{width:100%;padding:16px;background:linear-gradient(135deg,var(--accent),var(--success));border:none;border-radius:12px;color:white;font-size:1rem;font-weight:600;cursor:pointer;transition:all 0.3s ease;text-transform:uppercase;letter-spacing:1px}
    .btn-primary:hover{transform:translateY(-2px);box-shadow:0 10px 30px rgba(0,229,255,0.3)}
    .alert{padding:14px 18px;border-radius:12px;margin-bottom:25px;font-size:0.9rem}
    .alert-error{background:rgba(255,82,82,0.1);border:1px solid rgba(255,82,82,0.3);color:var(--error)}
    </style></head>
    <body>
    <div class="auth-container">
    <div class="auth-header"><h1>🔒 Login</h1><p>Network Monitor</p></div>
    {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}{% for category, message in messages %}
    <div class="alert alert-{{ category }}">{{ message }}</div>
    {% endfor %}{% endif %}{% endwith %}
    <form method="POST">
    <div class="form-group"><label for="username">Username</label>
    <input type="text" id="username" name="username" required autofocus></div>
    <div class="form-group"><label for="password">Password</label>
    <input type="password" id="password" name="password" required></div>
    <button type="submit" class="btn-primary">Login</button></form>
    </div></body></html>
    """
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================

@app.route('/')
@login_required
def dashboard():
    config = load_config()
    # If lab admin, redirect to their lab directly
    if not session.get('is_superadmin') and session.get('lab_id'):
        return redirect(url_for('lab_detail', lab_id=session['lab_id']))
    total_devices = 0
    total_online = 0
    total_offline = 0
    total_response_times = []
    total_healing = 0
    labs_data = {}
    
    for lab_id, lab_config in config['labs'].items():
        devices = lab_config['devices']
        online_count = 0
        lab_healing = 0
        
        if monitor:
            device_status = monitor.get_device_status()
            for device in devices:
                if device['ip'] in device_status:
                    if device_status[device['ip']]['online']:
                        online_count += 1
                        health_checks = device_status[device['ip']].get('health_checks', {})
                        ping_check = health_checks.get('ping', {})
                        if ping_check.get('response_time_ms'):
                            total_response_times.append(ping_check['response_time_ms'])
        
        if healer:
            healing_status = healer.get_healing_status()
            lab_healing = sum(healing_status.get(device['ip'], 0) for device in devices)
            total_healing += lab_healing
        
        total_devices += len(devices)
        total_online += online_count
        total_offline += (len(devices) - online_count)
        
        labs_data[lab_id] = {
            'name': lab_config['name'],
            'location': lab_config['location'],
            'description': lab_config['description'],
            'stats': {
                'total': len(devices),
                'online': online_count,
                'offline': len(devices) - online_count,
                'healing_attempts': lab_healing
            }
        }
    
    avg_response_time = sum(total_response_times) / len(total_response_times) if total_response_times else 0
    uptime_pct = (total_online / total_devices * 100) if total_devices > 0 else 0
    
    total_stats = {
        'total': total_devices,
        'online': total_online,
        'offline': total_offline,
        'uptime_pct': uptime_pct,
        'avg_response': avg_response_time,
        'labs': len(labs_data),
        'healing_attempts': total_healing
    }
    
    DASHBOARD_HTML = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="10">
        <title>Network Monitor Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
        <style>
            :root { --primary: #0A192F; --accent: #00E5FF; --success: #00C853; --warning: #FFC400;
                --error: #FF5252; --text: #E6F1FF; --glass: rgba(255, 255, 255, 0.05);
                --glass-border: rgba(255, 255, 255, 0.1); }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Inter', sans-serif; background: var(--primary); color: var(--text); min-height: 100vh; }
            .nav { background: var(--glass); backdrop-filter: blur(20px); border-bottom: 1px solid var(--glass-border);
                padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; }
            .nav-brand { font-size: 1.5rem; font-weight: 700;
                background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .nav-links { display: flex; gap: 30px; align-items: center; }
            .nav-links a { color: var(--text); text-decoration: none; font-weight: 500; transition: color 0.3s; }
            .nav-links a:hover { color: var(--accent); }
            .container { max-width: 1600px; margin: 0 auto; padding: 40px 20px; }
            .page-header { margin-bottom: 40px; }
            .page-header h1 { font-size: 2.5rem; margin-bottom: 10px; }
            .page-header p { color: rgba(230, 241, 255, 0.6); font-size: 1.1rem; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 40px; }
            .stat-card { background: var(--glass); backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border); border-radius: 16px; padding: 25px;
                transition: transform 0.3s, box-shadow 0.3s; }
            .stat-card:hover { transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0, 229, 255, 0.2); }
            .stat-icon { font-size: 2rem; margin-bottom: 10px; }
            .stat-value { font-size: 2.5rem; font-weight: 700; color: var(--accent); margin: 10px 0; }
            .stat-label { font-size: 0.9rem; color: rgba(230, 241, 255, 0.6); text-transform: uppercase; }
            .labs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 25px; }
            .lab-card { background: var(--glass); backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border); border-radius: 20px; padding: 30px;
                transition: all 0.3s; cursor: pointer; }
            .lab-card:hover { transform: translateY(-5px); border-color: var(--accent);
                box-shadow: 0 15px 40px rgba(0, 229, 255, 0.2); }
            .lab-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px; }
            .lab-name { font-size: 1.5rem; font-weight: 600; color: var(--accent); margin-bottom: 5px; }
            .lab-location { font-size: 0.9rem; color: rgba(230, 241, 255, 0.6); }
            .lab-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-top: 20px; }
            .lab-stat { text-align: center; padding: 10px; background: rgba(255, 255, 255, 0.03); border-radius: 8px; }
            .lab-stat-value { font-size: 1.8rem; font-weight: 700; }
            .lab-stat-label { font-size: 0.75rem; color: rgba(230, 241, 255, 0.5); margin-top: 5px; }
            .status-online { color: var(--success); }
            .status-offline { color: var(--error); }
            .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
            .section-title { font-size: 1.8rem; font-weight: 600; }
            .btn { padding: 12px 24px; border-radius: 8px; border: none; font-weight: 600;
                cursor: pointer; transition: all 0.3s; text-decoration: none; display: inline-block; }
            .btn-primary { background: linear-gradient(135deg, var(--accent), var(--success)); color: white; }
            .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0, 229, 255, 0.3); }
            .empty-state { text-align: center; padding: 60px 20px; color: rgba(230, 241, 255, 0.5); }
            .empty-state-icon { font-size: 4rem; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <nav class="nav">
            <div class="nav-brand">📡 Network Monitor</div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Dashboard</a>
                <a href="{{ url_for('add_lab') }}">Add Lab</a>
                {% if session.get('is_superadmin') %}
                <a href="{{ url_for('admin_users') }}">User Management</a>
                {% endif %}
                <a href="{{ url_for('logout') }}">Logout</a>
            </div>
        </nav>
        
        <div class="container">
            <div class="page-header">
                <h1>Network Monitoring Dashboard</h1>
                <p>Real-time system overview and lab management</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon">🖥️</div>
                    <div class="stat-value">{{ total_stats.total }}</div>
                    <div class="stat-label">Total Devices</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">✅</div>
                    <div class="stat-value status-online">{{ total_stats.online }}</div>
                    <div class="stat-label">Online</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">❌</div>
                    <div class="stat-value status-offline">{{ total_stats.offline }}</div>
                    <div class="stat-label">Offline</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">🔧</div>
                    <div class="stat-value" style="color: var(--warning);">{{ total_stats.healing_attempts }}</div>
                    <div class="stat-label">Healing Attempts</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📊</div>
                    <div class="stat-value">{{ '%.1f'|format(total_stats.uptime_pct) }}%</div>
                    <div class="stat-label">Average Uptime</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">⚡</div>
                    <div class="stat-value" style="font-size: 1.8rem;">{{ '%.1f'|format(total_stats.avg_response) }}ms</div>
                    <div class="stat-label">Avg Response Time</div>
                </div>
            </div>
            
            <div class="section-header">
                <h2 class="section-title">Labs ({{ total_stats.labs }})</h2>
                <a href="{{ url_for('add_lab') }}" class="btn btn-primary">+ Add New Lab</a>
            </div>
            
            {% if labs %}
            <div class="labs-grid">
                {% for lab_id, lab in labs.items() %}
                <div class="lab-card" onclick="window.location.href='{{ url_for('lab_detail', lab_id=lab_id) }}'">
                    <div class="lab-header">
                        <div>
                            <div class="lab-name">{{ lab.name }}</div>
                            <div class="lab-location">📍 {{ lab.location }}</div>
                        </div>
                    </div>
                    {% if lab.description %}
                    <p style="color: rgba(230, 241, 255, 0.7); margin-bottom: 15px;">{{ lab.description }}</p>
                    {% endif %}
                    <div class="lab-stats">
                        <div class="lab-stat">
                            <div class="lab-stat-value">{{ lab.stats.total }}</div>
                            <div class="lab-stat-label">Devices</div>
                        </div>
                        <div class="lab-stat">
                            <div class="lab-stat-value status-online">{{ lab.stats.online }}</div>
                            <div class="lab-stat-label">Online</div>
                        </div>
                        <div class="lab-stat">
                            <div class="lab-stat-value status-offline">{{ lab.stats.offline }}</div>
                            <div class="lab-stat-label">Offline</div>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <div class="empty-state-icon">🏢</div>
                <h3>No Labs Yet</h3>
                <p>Get started by adding your first lab</p>
                <br>
                <a href="{{ url_for('add_lab') }}" class="btn btn-primary">Add First Lab</a>
            </div>
            {% endif %}
        </div>
        
        <script>
            // WebSocket for real-time updates
            const socket = io();
            
            socket.on('device_update', function(data) {
                console.log('Device update:', data);
                // Reload page to show updated stats
                location.reload();
            });
            
            socket.on('connect', function() {
                console.log('Connected to server');
            });
        </script>
    </body>
    </html>
    """
    
    return render_template_string(DASHBOARD_HTML, labs=labs_data, total_stats=total_stats)

# ==================== LAB MANAGEMENT ====================

@app.route('/add_lab', methods=['GET', 'POST'])
@login_required
def add_lab():
    if request.method == 'POST':
        name = request.form.get('name')
        location = request.form.get('location')
        description = request.form.get('description', '')
        
        if not name or not location:
            flash('Name and location are required', 'error')
        else:
            config = load_config()
            lab_id = f"lab_{len(config['labs']) + 1}"
            
            config['labs'][lab_id] = {
                'name': name,
                'location': location,
                'description': description,
                'devices': []
            }
            
            save_config(config)
            flash(f'Lab "{name}" created successfully!', 'success')
            return redirect(url_for('lab_detail', lab_id=lab_id))
    
    ADD_LAB_HTML = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
        <title>Add Lab - Network Monitor</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root { --primary: #0A192F; --accent: #00E5FF; --success: #00C853; --error: #FF5252;
                --text: #E6F1FF; --glass: rgba(255, 255, 255, 0.05); --glass-border: rgba(255, 255, 255, 0.1); }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Inter', sans-serif; background: var(--primary); color: var(--text); min-height: 100vh; }
            .nav { background: var(--glass); backdrop-filter: blur(20px); border-bottom: 1px solid var(--glass-border);
                padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; }
            .nav-brand { font-size: 1.5rem; font-weight: 700;
                background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .nav-links { display: flex; gap: 30px; align-items: center; }
            .nav-links a { color: var(--text); text-decoration: none; font-weight: 500; }
            .container { max-width: 800px; margin: 0 auto; padding: 40px 20px; }
            .page-header { margin-bottom: 40px; }
            .page-header h1 { font-size: 2.5rem; margin-bottom: 10px; }
            .form-container { background: var(--glass); backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border); border-radius: 24px; padding: 40px; }
            .form-group { margin-bottom: 25px; }
            .form-group label { display: block; margin-bottom: 8px; color: rgba(230, 241, 255, 0.8);
                font-weight: 500; font-size: 0.95rem; }
            .form-group input, .form-group textarea {
                width: 100%; padding: 12px 16px; background: rgba(255, 255, 255, 0.05);
                border: 1px solid var(--glass-border); border-radius: 8px; color: var(--text);
                font-size: 1rem; font-family: 'Inter', sans-serif; transition: all 0.3s ease; }
            .form-group input:focus, .form-group textarea:focus {
                outline: none; border-color: var(--accent); background: rgba(255, 255, 255, 0.08);
                box-shadow: 0 0 0 3px rgba(0, 229, 255, 0.1); }
            .form-group textarea { resize: vertical; min-height: 100px; }
            .btn { padding: 14px 28px; border-radius: 8px; border: none; font-weight: 600;
                cursor: pointer; transition: all 0.3s; text-decoration: none; display: inline-block; font-size: 1rem; }
            .btn-primary { background: linear-gradient(135deg, var(--accent), var(--success));
                color: white; text-transform: uppercase; letter-spacing: 1px; }
            .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0, 229, 255, 0.3); }
            .btn-secondary { background: var(--glass); border: 1px solid var(--glass-border); color: var(--text); }
            .btn-group { display: flex; gap: 15px; margin-top: 30px; }
            .alert { padding: 14px 18px; border-radius: 12px; margin-bottom: 25px; font-size: 0.9rem; }
            .alert-error { background: rgba(255, 82, 82, 0.1); border: 1px solid rgba(255, 82, 82, 0.3); color: var(--error); }
            .alert-success { background: rgba(0, 200, 83, 0.1); border: 1px solid rgba(0, 200, 83, 0.3); color: var(--success); }
        </style>
    </head>
    <body>
        <nav class="nav">
            <div class="nav-brand">📡 Network Monitor</div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Dashboard</a>
                <a href="{{ url_for('add_lab') }}">Add Lab</a>
                {% if session.get('is_superadmin') %}
                <a href="{{ url_for('admin_users') }}">User Management</a>
                {% endif %}
                <a href="{{ url_for('logout') }}">Logout</a>
            </div>
        </nav>
        <div class="container">
            <div class="page-header">
                <h1>Add New Lab</h1>
                <p>Create a new lab to organize your devices</p>
            </div>
            
            <div class="form-container">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <form method="POST">
                    <div class="form-group">
                        <label for="name">Lab Name *</label>
                        <input type="text" id="name" name="name" required placeholder="e.g., Computer Lab 1">
                    </div>
                    
                    <div class="form-group">
                        <label for="location">Location *</label>
                        <input type="text" id="location" name="location" required placeholder="e.g., Building A, Floor 2">
                    </div>
                    
                    <div class="form-group">
                        <label for="description">Description (Optional)</label>
                        <textarea id="description" name="description" placeholder="Additional details about this lab..."></textarea>
                    </div>
                    
                    <div class="btn-group">
                        <button type="submit" class="btn btn-primary">Create Lab</button>
                        <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">Cancel</a>
                    </div>
                </form>
            </div>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(ADD_LAB_HTML)

# Continue in next artifact...

# Add these routes to dashboard_enterprise.py

@app.route('/lab/<lab_id>')
@login_required
@lab_access_required
def lab_detail(lab_id):
    config = load_config()
    
    if lab_id not in config['labs']:
        flash('Lab not found', 'error')
        return redirect(url_for('dashboard'))
    
    lab = config['labs'][lab_id]
    devices_data = []
    total_failures = 0
    total_healing_attempts = 0
    
    # Chart data for last 7 days
    chart_labels = []
    chart_online = []
    chart_offline = []
    
    if monitor:
        device_status = monitor.get_device_status()
        for device in lab['devices']:
            ip = device['ip']
            status = device_status.get(ip, {})
            
            uptime_pct = 0
            if database:
                uptime_pct = database.get_device_uptime(ip, '7d')
            
            failures = status.get('consecutive_failures', 0)
            total_failures += failures
            
            healing_attempts = 0
            if healer:
                healing_status = healer.get_healing_status()
                healing_attempts = healing_status.get(ip, 0)
                total_healing_attempts += healing_attempts
            
            devices_data.append({
                'label': device['label'],
                'ip': ip,
                'online': status.get('online', False),
                'response_time': status.get('health_checks', {}).get('ping', {}).get('response_time_ms'),
                'uptime_pct': uptime_pct,
                'failures': failures,
                'healing_attempts': healing_attempts,
                'last_seen': status.get('last_seen').strftime('%Y-%m-%d %H:%M:%S') if status.get('last_seen') else 'Never',
                'ssh_enabled': device.get('ssh_enabled', False),
                'health_checks': device.get('health_checks', {})
            })
        
        # Get historical data for chart (last 7 days)
        if database and lab['devices']:
            for i in range(6, -1, -1):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                chart_labels.append(date)
                
                # Count online/offline for this day
                online_count = 0
                offline_count = 0
                for device in lab['devices']:
                    ip = device['ip']
                    # Get uptime for this specific day
                    uptime = database.get_device_uptime(ip, '24h')
                    if uptime > 50:  # Consider online if uptime > 50%
                        online_count += 1
                    else:
                        offline_count += 1
                
                chart_online.append(online_count)
                chart_offline.append(offline_count)
    
    lab_stats = {
        'total': len(lab['devices']),
        'online': sum(1 for d in devices_data if d['online']),
        'offline': sum(1 for d in devices_data if not d['online']),
        'failures': total_failures,
        'healing_attempts': total_healing_attempts,
        'avg_uptime': sum(d['uptime_pct'] for d in devices_data) / len(devices_data) if devices_data else 0,
        'avg_response': sum(d['response_time'] for d in devices_data if d['response_time']) / len([d for d in devices_data if d['response_time']]) if any(d['response_time'] for d in devices_data) else 0
    }
    
    LAB_DETAIL_HTML = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="10">
        <title>{{ lab.name }} - Network Monitor</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
        <style>
            :root { --primary: #0A192F; --accent: #00E5FF; --success: #00C853; --warning: #FFC400;
                --error: #FF5252; --text: #E6F1FF; --glass: rgba(255, 255, 255, 0.05); 
                --glass-border: rgba(255, 255, 255, 0.1); }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Inter', sans-serif; background: var(--primary); color: var(--text); min-height: 100vh; }
            .nav { background: var(--glass); backdrop-filter: blur(20px); border-bottom: 1px solid var(--glass-border);
                padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; }
            .nav-brand { font-size: 1.5rem; font-weight: 700;
                background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .nav-links { display: flex; gap: 30px; align-items: center; }
            .nav-links a { color: var(--text); text-decoration: none; font-weight: 500; transition: color 0.3s; }
            .nav-links a:hover { color: var(--accent); }
            .container { max-width: 1600px; margin: 0 auto; padding: 40px 20px; }
            .breadcrumb { color: rgba(230, 241, 255, 0.6); margin-bottom: 20px; font-size: 0.9rem; }
            .breadcrumb a { color: var(--accent); text-decoration: none; }
            .breadcrumb a:hover { text-decoration: underline; }
            .page-header { margin-bottom: 40px; display: flex; justify-content: space-between; align-items: center; }
            .page-header h1 { font-size: 2.5rem; margin-bottom: 5px; }
            .page-header p { color: rgba(230, 241, 255, 0.6); }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 40px; }
            .stat-card { background: var(--glass); backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border); border-radius: 16px; padding: 20px;
                transition: transform 0.3s; }
            .stat-card:hover { transform: translateY(-3px); }
            .stat-value { font-size: 2.5rem; font-weight: 700; color: var(--accent); margin: 10px 0; }
            .stat-label { font-size: 0.9rem; color: rgba(230, 241, 255, 0.6); text-transform: uppercase; }
            .chart-container { background: var(--glass); backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border); border-radius: 24px; padding: 30px; margin-bottom: 30px; }
            .chart-header { margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
            .chart-header h3 { font-size: 1.5rem; color: var(--accent); }
            canvas { max-height: 300px; }
            .devices-table { background: var(--glass); backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border); border-radius: 24px; padding: 30px; }
            .devices-table h3 { font-size: 1.5rem; color: var(--accent); margin-bottom: 20px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 15px; text-align: left; border-bottom: 1px solid var(--glass-border); }
            th { color: rgba(230, 241, 255, 0.8); font-weight: 600; text-transform: uppercase; font-size: 0.85rem; }
            tr:hover { background: rgba(255, 255, 255, 0.03); }
            .status-badge { padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; }
            .status-online { background: rgba(0, 200, 83, 0.2); color: var(--success); }
            .status-offline { background: rgba(255, 82, 82, 0.2); color: var(--error); }
            .btn { padding: 10px 20px; border-radius: 8px; border: none; font-weight: 600;
                cursor: pointer; transition: all 0.3s; text-decoration: none; display: inline-block; font-size: 0.9rem; }
            .btn-primary { background: var(--accent); color: white; }
            .btn-primary:hover { background: #00c5d9; transform: translateY(-2px); }
            .btn-small { padding: 6px 12px; font-size: 0.8rem; }
            .empty-state { text-align: center; padding: 60px 20px; color: rgba(230, 241, 255, 0.5); }
            .empty-state-icon { font-size: 4rem; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <nav class="nav">
            <div class="nav-brand">📡 Network Monitor</div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Dashboard</a>
                <a href="{{ url_for('add_lab') }}">Add Lab</a>
                {% if session.get('is_superadmin') %}
                <a href="{{ url_for('admin_users') }}">User Management</a>
                {% endif %}
                <a href="{{ url_for('logout') }}">Logout</a>
            </div>
        </nav>
        
        <div class="container">
            <div class="breadcrumb">
                <a href="{{ url_for('dashboard') }}">Dashboard</a> / {{ lab.name }}
            </div>
            
            <div class="page-header">
                <div>
                    <h1>{{ lab.name }}</h1>
                    <p>📍 {{ lab.location }}</p>
                    {% if lab.description %}
                    <p style="margin-top: 10px;">{{ lab.description }}</p>
                    {% endif %}
                </div>
                <a href="{{ url_for('add_device_to_lab', lab_id=lab_id) }}" class="btn btn-primary">+ Add Device</a>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Devices</div>
                    <div class="stat-value">{{ lab_stats.total }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Online</div>
                    <div class="stat-value" style="color: var(--success);">{{ lab_stats.online }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Offline</div>
                    <div class="stat-value" style="color: var(--error);">{{ lab_stats.offline }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total Failures</div>
                    <div class="stat-value" style="color: var(--warning);">{{ lab_stats.failures }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Healing Attempts</div>
                    <div class="stat-value" style="color: var(--accent);">{{ lab_stats.healing_attempts }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avg Uptime (7d)</div>
                    <div class="stat-value" style="font-size: 2rem;">{{ '%.1f'|format(lab_stats.avg_uptime) }}%</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avg Response Time</div>
                    <div class="stat-value" style="font-size: 1.8rem;">{{ '%.1f'|format(lab_stats.avg_response) }}ms</div>
                </div>
            </div>
            
            <div class="chart-container">
                <div class="chart-header">
                    <h3>Device Status History (Last 7 Days)</h3>
                </div>
                <canvas id="statusChart"></canvas>
            </div>
            
            <div class="devices-table">
                <h3>Devices ({{ lab_stats.total }})</h3>
                
                {% if devices %}
                <table>
                    <thead>
                        <tr>
                            <th>Device Name</th>
                            <th>IP Address</th>
                            <th>Status</th>
                            <th>Response Time</th>
                            <th>Uptime (7d)</th>
                            <th>Failures</th>
                            <th>Healing</th>
                            <th>Last Seen</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for device in devices %}
                        <tr>
                            <td><strong>{{ device.label }}</strong></td>
                            <td>{{ device.ip }}</td>
                            <td>
                                <span class="status-badge status-{{ 'online' if device.online else 'offline' }}">
                                    {{ 'Online' if device.online else 'Offline' }}
                                </span>
                            </td>
                            <td>{{ '%.1f'|format(device.response_time) if device.response_time else 'N/A' }} ms</td>
                            <td>{{ '%.1f'|format(device.uptime_pct) }}%</td>
                            <td style="color: var(--warning);">{{ device.failures }}</td>
                            <td style="color: var(--accent);">{{ device.healing_attempts }}</td>
                            <td style="font-size: 0.85rem;">{{ device.last_seen }}</td>
                            <td>
                                <a href="{{ url_for('device_detail', lab_id=lab_id, ip=device.ip) }}" class="btn btn-primary btn-small">View</a>
                                <a href="{{ url_for('delete_device', lab_id=lab_id, ip=device.ip) }}" class="btn btn-danger btn-small" onclick="return confirm('Are you sure you want to delete this device?')">Delete</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <div class="empty-state">
                    <div class="empty-state-icon">💻</div>
                    <h3>No Devices Yet</h3>
                    <p>Add your first device to start monitoring</p>
                    <br>
                    <a href="{{ url_for('add_device_to_lab', lab_id=lab_id) }}" class="btn btn-primary">Add First Device</a>
                </div>
                {% endif %}
            </div>
        </div>
        
        <script>
            const ctx = document.getElementById('statusChart');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: {{ chart_labels|tojson }},
                    datasets: [
                        {
                            label: 'Online',
                            data: {{ chart_online|tojson }},
                            backgroundColor: 'rgba(0, 200, 83, 0.6)',
                            borderColor: '#00C853',
                            borderWidth: 2
                        },
                        {
                            label: 'Offline',
                            data: {{ chart_offline|tojson }},
                            backgroundColor: 'rgba(255, 82, 82, 0.6)',
                            borderColor: '#FF5252',
                            borderWidth: 2
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: { color: '#E6F1FF', font: { size: 14 } }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            stacked: true,
                            grid: { color: 'rgba(230, 241, 255, 0.1)' },
                            ticks: { color: '#E6F1FF', stepSize: 1 }
                        },
                        x: {
                            stacked: true,
                            grid: { color: 'rgba(230, 241, 255, 0.1)' },
                            ticks: { color: '#E6F1FF' }
                        }
                    }
                }
            });
        </script>
    </body>
    </html>
    """
    
    return render_template_string(LAB_DETAIL_HTML, lab_id=lab_id, lab=lab, devices=devices_data, 
                                   lab_stats=lab_stats, chart_labels=chart_labels, 
                                   chart_online=chart_online, chart_offline=chart_offline)


@app.route('/lab/<lab_id>/add_device', methods=['GET', 'POST'])
@login_required
@lab_access_required
def add_device_to_lab(lab_id):
    config = load_config()
    
    if lab_id not in config['labs']:
        flash('Lab not found', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        ip = request.form.get('ip')
        label = request.form.get('label')
        ssh_enabled = request.form.get('ssh_enabled') == 'on'
        ssh_username = request.form.get('ssh_username', '')
        ssh_password = request.form.get('ssh_password', '')
        ssh_port = int(request.form.get('ssh_port', 22))
        ping_check = request.form.get('ping_check') == 'on'
        http_enabled = request.form.get('http_enabled') == 'on'
        http_url = request.form.get('http_url', '')
        http_expected_status = int(request.form.get('http_expected_status', 200)) if request.form.get('http_expected_status') else 200
        
        # Validate
        if not ip or not label:
            flash('IP address and device name are required', 'error')
        else:
            # Check if IP already exists
            for device in config['labs'][lab_id]['devices']:
                if device['ip'] == ip:
                    flash(f'Device with IP {ip} already exists in this lab', 'error')
                    return redirect(url_for('add_device_to_lab', lab_id=lab_id))
            
            # Add device
            device = {
                'ip': ip,
                'label': label,
                'ssh_enabled': ssh_enabled,
                'ssh_username': ssh_username,
                'ssh_password': ssh_password,
                'ssh_port': ssh_port,
                'health_checks': {
                    'ping': ping_check,
                    'http': {'enabled': http_enabled, 'url': http_url, 'expected_status': http_expected_status},
                    'port_checks': [],
                    'performance_metrics': ssh_enabled
                }
            }
            
            config['labs'][lab_id]['devices'].append(device)
            save_config(config)
            
            flash(f'Device "{label}" added successfully!', 'success')
            return redirect(url_for('lab_detail', lab_id=lab_id))
    
    lab = config['labs'][lab_id]
    
    # Reuse the ADD_DEVICE_HTML from dashboard_routes.py
    from dashboard_routes import ADD_DEVICE_HTML
    
    return render_template_string(ADD_DEVICE_HTML, lab_id=lab_id, lab_name=lab['name'], labs={})


@app.route('/device/<lab_id>/<ip>')
@login_required
@lab_access_required
def device_detail(lab_id, ip):
    config = load_config()
    
    if lab_id not in config['labs']:
        flash('Lab not found', 'error')
        return redirect(url_for('dashboard'))
    
    lab = config['labs'][lab_id]
    device_config = None
    
    for device in lab['devices']:
        if device['ip'] == ip:
            device_config = device
            break
    
    if not device_config:
        flash('Device not found', 'error')
        return redirect(url_for('lab_detail', lab_id=lab_id))
    
    device_data = {
        'ip': ip,
        'label': device_config['label'],
        'ssh_enabled': device_config.get('ssh_enabled', False),
        'ssh_username': device_config.get('ssh_username', ''),
        'ssh_port': device_config.get('ssh_port', 22),
        'health_checks': device_config.get('health_checks', {}),
        'online': False,
        'response_time': None,
        'uptime_pct': 0,
        'failures': 0,
        'healing_attempts': 0,
        'last_seen': 'Never',
        'performance_metrics': None
    }
    
    if monitor:
        device_status = monitor.get_device_status()
        status = device_status.get(ip, {})
        
        device_data['online'] = status.get('online', False)
        device_data['failures'] = status.get('consecutive_failures', 0)
        device_data['last_seen'] = status.get('last_seen').strftime('%Y-%m-%d %H:%M:%S') if status.get('last_seen') else 'Never'
        
        health_checks = status.get('health_checks', {})
        ping_check = health_checks.get('ping', {})
        device_data['response_time'] = ping_check.get('response_time_ms')
        
        # Performance metrics
        perf_check = health_checks.get('performance', {})
        if perf_check.get('success'):
            device_data['performance_metrics'] = perf_check.get('metrics', {})
    
    if database:
        device_data['uptime_pct'] = database.get_device_uptime(ip, '7d')
    
    if healer:
        healing_status = healer.get_healing_status()
        device_data['healing_attempts'] = healing_status.get(ip, 0)
    
    # Get historical data for charts
    response_labels = []
    response_data = []
    uptime_labels = []
    uptime_data = []
    
    if database:
        # Response time history (last 24 hours)
        history = database.get_historical_data('ping', ip, '24h')
        for record in history[-20:]:  # Last 20 data points
            timestamp = datetime.fromisoformat(record['timestamp'])
            response_labels.append(timestamp.strftime('%H:%M'))
            response_data.append(record['value'])
        
        # Uptime history (last 7 days)
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            uptime_labels.append(date[-5:])  # Just MM-DD
            
            # Get uptime for this day
            uptime = database.get_device_uptime(ip, '24h')
            uptime_data.append(uptime)
    
    # Reuse DEVICE_DETAIL_HTML from dashboard_routes.py
    from dashboard_routes import DEVICE_DETAIL_HTML
    
    return render_template_string(DEVICE_DETAIL_HTML, 
                                   lab_id=lab_id, 
                                   lab_name=lab['name'],
                                   device=device_data,
                                   response_labels=response_labels,
                                   response_data=response_data,
                                   uptime_labels=uptime_labels,
                                   uptime_data=uptime_data)


@app.route('/delete_device/<lab_id>/<ip>')
@login_required
@lab_access_required
def delete_device(lab_id, ip):
    """Delete a device from a lab."""
    config = load_config()
    
    if lab_id not in config['labs']:
        flash('Lab not found', 'error')
        return redirect(url_for('dashboard'))
    
    lab = config['labs'][lab_id]
    device_found = False
    
    for i, device in enumerate(lab['devices']):
        if device['ip'] == ip:
            device_label = device['label']
            lab['devices'].pop(i)
            device_found = True
            break
    
    if device_found:
        save_config(config)
        flash(f'Device "{device_label}" ({ip}) deleted successfully!', 'success')
    else:
        flash('Device not found', 'error')
    
    return redirect(url_for('lab_detail', lab_id=lab_id))


# ==================== GENERAL ADD DEVICE ====================

@app.route('/add_device')
@login_required
def add_device():
    """General add device page - redirect to lab selection for superadmin or specific lab for lab admin."""
    config = load_config()
    
    # If lab admin, redirect to their lab's add device page
    if not session.get('is_superadmin') and session.get('lab_id'):
        return redirect(url_for('add_device_to_lab', lab_id=session['lab_id']))
    
    # If superadmin, show lab selection
    if session.get('is_superadmin'):
        labs = config.get('labs', {})
        if not labs:
            flash('No labs available. Create a lab first.', 'error')
            return redirect(url_for('add_lab'))
        
        # Show lab selection page
        LAB_SELECTION_HTML = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Select Lab - Add Device</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <style>
                :root { --primary: #0A192F; --accent: #00E5FF; --success: #00C853; --error: #FF5252;
                    --text: #E6F1FF; --glass: rgba(255, 255, 255, 0.05); --glass-border: rgba(255, 255, 255, 0.1); }
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { font-family: 'Inter', sans-serif; background: var(--primary); color: var(--text); min-height: 100vh; }
                .nav { background: var(--glass); backdrop-filter: blur(20px); border-bottom: 1px solid var(--glass-border);
                    padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; }
                .nav-brand { font-size: 1.5rem; font-weight: 700;
                    background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
                    -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
                .nav-links { display: flex; gap: 30px; align-items: center; }
                .nav-links a { color: var(--text); text-decoration: none; font-weight: 500; }
                .container { max-width: 800px; margin: 0 auto; padding: 40px 20px; }
                .page-header { margin-bottom: 40px; text-align: center; }
                .page-header h1 { font-size: 2.5rem; margin-bottom: 10px; }
                .labs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
                .lab-card { background: var(--glass); backdrop-filter: blur(20px);
                    border: 1px solid var(--glass-border); border-radius: 16px; padding: 30px;
                    transition: all 0.3s; cursor: pointer; text-align: center; }
                .lab-card:hover { transform: translateY(-5px); border-color: var(--accent);
                    box-shadow: 0 15px 40px rgba(0, 229, 255, 0.2); }
                .lab-name { font-size: 1.5rem; font-weight: 600; color: var(--accent); margin-bottom: 10px; }
                .lab-location { color: rgba(230, 241, 255, 0.6); margin-bottom: 15px; }
                .lab-devices { color: rgba(230, 241, 255, 0.8); font-size: 0.9rem; }
                .btn { padding: 12px 24px; border-radius: 8px; border: none; font-weight: 600;
                    cursor: pointer; transition: all 0.3s; text-decoration: none; display: inline-block; }
                .btn-primary { background: linear-gradient(135deg, var(--accent), var(--success)); color: white; }
                .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0, 229, 255, 0.3); }
            </style>
        </head>
        <body>
            <nav class="nav">
                <div class="nav-brand">📡 Network Monitor</div>
                <div class="nav-links">
                    <a href="{{ url_for('dashboard') }}">Dashboard</a>
                    <a href="{{ url_for('add_lab') }}">Add Lab</a>
                    {% if session.get('is_superadmin') %}
                    <a href="{{ url_for('admin_users') }}">User Management</a>
                    {% endif %}
                    <a href="{{ url_for('logout') }}">Logout</a>
                </div>
            </nav>
            
            <div class="container">
                <div class="page-header">
                    <h1>Select Lab</h1>
                    <p>Choose a lab to add a device to</p>
                </div>
                
                <div class="labs-grid">
                    {% for lab_id, lab in labs.items() %}
                    <div class="lab-card" onclick="window.location.href='{{ url_for('add_device_to_lab', lab_id=lab_id) }}'">
                        <div class="lab-name">{{ lab.name }}</div>
                        <div class="lab-location">📍 {{ lab.location }}</div>
                        <div class="lab-devices">{{ lab.devices|length }} devices</div>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(LAB_SELECTION_HTML, labs=labs)
    
    # Fallback
    return redirect(url_for('dashboard'))


# ==================== ONBOARDING (SUPERADMIN) ====================

@app.route('/onboarding', methods=['GET', 'POST'])
@login_required
@admin_required
def onboarding():
    config = load_config()
    step = request.args.get('step', '1')
    # Step 1: Create Lab
    if step == '1':
        if request.method == 'POST':
            name = request.form.get('name')
            location = request.form.get('location')
            description = request.form.get('description', '')
            if not name or not location:
                flash('Name and location are required', 'error')
            else:
                lab_id = f"lab_{len(config['labs']) + 1}"
                config['labs'][lab_id] = {'name': name, 'location': location, 'description': description, 'devices': []}
                save_config(config)
                flash('Lab created. Now create a lab admin.', 'success')
                return redirect(url_for('onboarding', step='2', lab_id=lab_id))
        HTML = """
        <!DOCTYPE html><html><head><meta charset=\"UTF-8\"><title>Onboarding - Create Lab</title>
        <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap\" rel=\"stylesheet\"></head>
        <body style=\"font-family:Inter;padding:40px;color:#E6F1FF;background:#0A192F\">
        <h1>Create First Lab</h1>
        <form method=\"POST\"> 
            <p><label>Name <input name=\"name\" required></label></p>
            <p><label>Location <input name=\"location\" required></label></p>
            <p><label>Description <input name=\"description\"></label></p>
            <button type=\"submit\">Continue</button>
        </form>
        </body></html>
        """
        return render_template_string(HTML)
    # Step 2: Create Lab Admin
    if step == '2':
        lab_id = request.args.get('lab_id')
        if not lab_id or lab_id not in config['labs']:
            flash('Invalid lab', 'error')
            return redirect(url_for('onboarding', step='1'))
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            ok, msg = user_manager.create_user(username, email, password, lab_id=lab_id, is_superadmin=False)
            if ok:
                flash('Lab admin created. Add a device next.', 'success')
                return redirect(url_for('add_device_to_lab', lab_id=lab_id))
            flash(msg, 'error')
        HTML = f"""
        <!DOCTYPE html><html><head><meta charset=\"UTF-8\"><title>Onboarding - Create Lab Admin</title>
        <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap\" rel=\"stylesheet\"></head>
        <body style=\"font-family:Inter;padding:40px;color:#E6F1FF;background:#0A192F\">
        <h1>Create Lab Admin for {lab_id}</h1>
        <form method=\"POST\"> 
            <p><label>Username <input name=\"username\" required></label></p>
            <p><label>Email <input name=\"email\" type=\"email\" required></label></p>
            <p><label>Password <input name=\"password\" type=\"password\" required></label></p>
            <button type=\"submit\">Continue</button>
        </form>
        </body></html>
        """
        return render_template_string(HTML)


# ==================== JSON APIs ====================

@app.route('/api/create_lab', methods=['POST'])
@login_required
@admin_required
def api_create_lab():
    data = request.get_json(force=True)
    name = data.get('name')
    location = data.get('location')
    description = data.get('description', '')
    if not name or not location:
        return jsonify({'success': False, 'message': 'Name and location required'}), 400
    config = load_config()
    lab_id = f"lab_{len(config['labs']) + 1}"
    config['labs'][lab_id] = {'name': name, 'location': location, 'description': description, 'devices': []}
    save_config(config)
    return jsonify({'success': True, 'lab_id': lab_id})


@app.route('/api/add_device', methods=['POST'])
@login_required
def api_add_device():
    data = request.get_json(force=True)
    lab_id = data.get('lab_id')
    if not lab_id:
        return jsonify({'success': False, 'message': 'lab_id required'}), 400
    # ACL: superadmin bypass, else lab must match session
    if not session.get('is_superadmin') and session.get('lab_id') != lab_id:
        return jsonify({'success': False, 'message': 'Not authorized for this lab'}), 403
    ip = data.get('ip')
    label = data.get('label')
    ssh_enabled = bool(data.get('ssh_enabled'))
    ssh_username = data.get('ssh_username', '')
    ssh_password = data.get('ssh_password', '')
    ssh_port = int(data.get('ssh_port', 22))
    ping_check = bool(data.get('ping_check', True))
    http_enabled = bool(data.get('http_enabled', False))
    http_url = data.get('http_url', '')
    http_expected_status = int(data.get('http_expected_status', 200))
    if not ip or not label:
        return jsonify({'success': False, 'message': 'IP and label required'}), 400
    health_checks = {
        'ping': ping_check,
        'http': {'enabled': http_enabled, 'url': http_url, 'expected_status': http_expected_status},
        'port_checks': [],
        'performance_metrics': ssh_enabled
    }
    ok, msg = device_manager.add_device(lab_id, ip, label, ssh_enabled, ssh_username, ssh_password, ssh_port, health_checks)
    return jsonify({'success': ok, 'message': msg})


# ==================== ADMIN USER MANAGEMENT ====================

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """Superadmin page to manage users and lab assignments."""
    users = user_manager.list_users()
    config = load_config()
    labs = config.get('labs', {})
    
    ADMIN_USERS_HTML = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="refresh" content="10">
        <title>User Management - Network Monitor</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root { --primary: #0A192F; --accent: #00E5FF; --success: #00C853; --error: #FF5252;
                --text: #E6F1FF; --glass: rgba(255, 255, 255, 0.05); --glass-border: rgba(255, 255, 255, 0.1); }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Inter', sans-serif; background: var(--primary); color: var(--text); min-height: 100vh; }
            .nav { background: var(--glass); backdrop-filter: blur(20px); border-bottom: 1px solid var(--glass-border);
                padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; }
            .nav-brand { font-size: 1.5rem; font-weight: 700;
                background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .nav-links { display: flex; gap: 30px; align-items: center; }
            .nav-links a { color: var(--text); text-decoration: none; font-weight: 500; }
            .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
            .page-header { margin-bottom: 40px; display: flex; justify-content: space-between; align-items: center; }
            .page-header h1 { font-size: 2.5rem; margin-bottom: 10px; }
            .btn { padding: 12px 24px; border-radius: 8px; border: none; font-weight: 600;
                cursor: pointer; transition: all 0.3s; text-decoration: none; display: inline-block; }
            .btn-primary { background: linear-gradient(135deg, var(--accent), var(--success)); color: white; }
            .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0, 229, 255, 0.3); }
            .users-table { background: var(--glass); backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border); border-radius: 16px; padding: 30px; margin-bottom: 30px; }
            .users-table h3 { font-size: 1.5rem; margin-bottom: 20px; color: var(--accent); }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 15px; text-align: left; border-bottom: 1px solid var(--glass-border); }
            th { color: rgba(230, 241, 255, 0.8); font-weight: 600; text-transform: uppercase; font-size: 0.85rem; }
            tr:hover { background: rgba(255, 255, 255, 0.03); }
            .badge { padding: 4px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
            .badge-superadmin { background: rgba(255, 193, 7, 0.2); color: #FFC107; }
            .badge-labadmin { background: rgba(0, 229, 255, 0.2); color: var(--accent); }
            .form-container { background: var(--glass); backdrop-filter: blur(20px);
                border: 1px solid var(--glass-border); border-radius: 16px; padding: 30px; }
            .form-group { margin-bottom: 20px; }
            .form-group label { display: block; margin-bottom: 8px; color: rgba(230, 241, 255, 0.8);
                font-weight: 500; font-size: 0.95rem; }
            .form-group input, .form-group select { width: 100%; padding: 12px 16px; background: rgba(255, 255, 255, 0.05);
                border: 1px solid var(--glass-border); border-radius: 8px; color: var(--text);
                font-size: 1rem; font-family: 'Inter', sans-serif; }
            .form-group input:focus, .form-group select:focus { outline: none; border-color: var(--accent);
                box-shadow: 0 0 0 3px rgba(0, 229, 255, 0.1); }
            .checkbox-group { display: flex; align-items: center; gap: 10px; }
            .checkbox-group input[type="checkbox"] { width: auto; }
            .alert { padding: 14px 18px; border-radius: 12px; margin-bottom: 25px; font-size: 0.9rem; }
            .alert-success { background: rgba(0, 200, 83, 0.1); border: 1px solid rgba(0, 200, 83, 0.3); color: var(--success); }
            .alert-error { background: rgba(255, 82, 82, 0.1); border: 1px solid rgba(255, 82, 82, 0.3); color: var(--error); }
        </style>
    </head>
    <body>
        <nav class="nav">
            <div class="nav-brand">📡 Network Monitor</div>
            <div class="nav-links">
                <a href="{{ url_for('dashboard') }}">Dashboard</a>
                <a href="{{ url_for('admin_users') }}">User Management</a>
                <a href="{{ url_for('logout') }}">Logout</a>
            </div>
        </nav>
        
        <div class="container">
            <div class="page-header">
                <div>
                    <h1>User Management</h1>
                    <p>Manage lab administrators and superadmin accounts</p>
                </div>
            </div>
            
            <div class="users-table">
                <h3>Current Users ({{ users|length }})</h3>
                {% if users %}
                <table>
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>Email</th>
                            <th>Role</th>
                            <th>Lab Assignment</th>
                            <th>Last Login</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for user in users %}
                        <tr>
                            <td><strong>{{ user.username }}</strong></td>
                            <td>{{ user.email }}</td>
                            <td>
                                <span class="badge badge-{{ 'superadmin' if user.is_superadmin else 'labadmin' }}">
                                    {{ 'Superadmin' if user.is_superadmin else 'Lab Admin' }}
                                </span>
                            </td>
                            <td>{{ user.lab_id or 'N/A' }}</td>
                            <td>{{ user.last_login or 'Never' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p>No users found.</p>
                {% endif %}
            </div>
            
            <div class="form-container">
                <h3>Create New User</h3>
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <form method="POST" action="{{ url_for('create_user') }}">
                    <div class="form-group">
                        <label for="username">Username</label>
                        <input type="text" id="username" name="username" required placeholder="e.g., alice">
                    </div>
                    
                    <div class="form-group">
                        <label for="email">Email</label>
                        <input type="email" id="email" name="email" required placeholder="alice@example.com">
                    </div>
                    
                    <div class="form-group">
                        <label for="password">Password</label>
                        <input type="password" id="password" name="password" required placeholder="Enter password">
                    </div>
                    
                    <div class="form-group">
                        <label for="lab_id">Lab Assignment</label>
                        <select id="lab_id" name="lab_id">
                            <option value="">Select a lab (optional for superadmin)</option>
                            {% for lab_id, lab in labs.items() %}
                            <option value="{{ lab_id }}">{{ lab.name }} - {{ lab.location }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    
                    <div class="checkbox-group form-group">
                        <input type="checkbox" id="is_superadmin" name="is_superadmin">
                        <label for="is_superadmin" style="margin-bottom: 0;">Superadmin (can manage all labs)</label>
                    </div>
                    
                    <button type="submit" class="btn btn-primary">Create User</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(ADMIN_USERS_HTML, users=users, labs=labs)


@app.route('/create_user', methods=['POST'])
@login_required
@admin_required
def create_user():
    """Create a new user (superadmin only)."""
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    lab_id = request.form.get('lab_id') or None
    is_superadmin = request.form.get('is_superadmin') == 'on'
    
    if not username or not email or not password:
        flash('Username, email, and password are required', 'error')
        return redirect(url_for('admin_users'))
    
    # Validate lab_id if provided
    if lab_id:
        config = load_config()
        if lab_id not in config.get('labs', {}):
            flash('Invalid lab selected', 'error')
            return redirect(url_for('admin_users'))
    
    ok, msg = user_manager.create_user(username, email, password, lab_id, is_superadmin)
    if ok:
        flash(f'User "{username}" created successfully!', 'success')
    else:
        flash(f'Error creating user: {msg}', 'error')
    
    return redirect(url_for('admin_users'))
