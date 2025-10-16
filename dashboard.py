import json
import os
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request, redirect, url_for, session, flash
from functools import wraps
import pandas as pd

app = Flask(__name__)
app.secret_key = 'change-this-to-a-random-secret-key-in-production'  # Change this!

# Global variables to store monitor and healer references
monitor = None
healer = None

# Default admin credentials (CHANGE THESE!)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"  # Change this in production!

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def load_config():
    """Load configuration from config.json"""
    with open('config.json', 'r') as f:
        return json.load(f)

def calculate_uptime_stats():
    """
    Calculate uptime percentage for each device from logs.
    
    Returns:
        dict: Uptime statistics for each device
    """
    config = load_config()
    log_file = os.path.join(
        config['logging']['log_directory'],
        config['logging']['log_file']
    )
    
    if not os.path.exists(log_file):
        return {}
    
    try:
        df = pd.read_csv(log_file)
        
        if df.empty:
            return {}
        
        # Check if required columns exist
        if 'ip' not in df.columns or 'status' not in df.columns:
            print(f"Warning: CSV missing required columns. Found: {df.columns.tolist()}")
            return {}
        
        # Calculate uptime percentage for each device
        stats = {}
        
        for ip in df['ip'].unique():
            device_df = df[df['ip'] == ip]
            total_checks = len(device_df)
            online_checks = len(device_df[device_df['status'] == 'online'])
            
            uptime_pct = (online_checks / total_checks * 100) if total_checks > 0 else 0
            
            # Get label
            label = device_df.iloc[0]['label']
            
            # Get last check time
            last_check = device_df.iloc[-1]['timestamp']
            
            # Calculate average response time (for online checks only)
            online_df = device_df[device_df['status'] == 'online']
            avg_response = online_df['response_time_ms'].mean() if not online_df.empty else None
            
            stats[ip] = {
                'label': label,
                'total_checks': total_checks,
                'online_checks': online_checks,
                'uptime_percentage': round(uptime_pct, 2),
                'last_check': last_check,
                'avg_response_ms': round(avg_response, 2) if avg_response else None
            }
        
        return stats
    
    except Exception as e:
        print(f"Error calculating uptime stats: {str(e)}")
        return {}

def get_recent_logs(limit=50):
    """
    Get recent log entries.
    
    Args:
        limit (int): Maximum number of entries to return
    
    Returns:
        list: Recent log entries
    """
    config = load_config()
    log_file = os.path.join(
        config['logging']['log_directory'],
        config['logging']['log_file']
    )
    
    if not os.path.exists(log_file):
        return []
    
    try:
        df = pd.read_csv(log_file)
        
        if df.empty:
            return []
        
        # Get last N entries
        recent = df.tail(limit)
        return recent.to_dict('records')
    
    except Exception as e:
        print(f"Error reading logs: {str(e)}")
        return []

def get_healing_logs(limit=20):
    """
    Get recent healing attempts from healing log.
    
    Args:
        limit (int): Maximum number of entries to return
    
    Returns:
        list: Recent healing log entries
    """
    config = load_config()
    healing_log_file = os.path.join(
        config['logging']['log_directory'],
        'healing.csv'
    )
    
    if not os.path.exists(healing_log_file):
        return []
    
    try:
        df = pd.read_csv(healing_log_file)
        
        if df.empty:
            return []
        
        # Get last N entries
        recent = df.tail(limit)
        return recent.to_dict('records')
    
    except Exception as e:
        print(f"Error reading healing logs: {str(e)}")
        return []

# Login page HTML
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Network Monitor</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #0A192F;
            --accent: #00E5FF;
            --text: #E6F1FF;
            --glass: rgba(255, 255, 255, 0.05);
            --glass-border: rgba(255, 255, 255, 0.1);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background: var(--primary);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
        }
        
        .bg-animation {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
        }
        
        .bg-gradient {
            position: absolute;
            width: 150%;
            height: 150%;
            background: radial-gradient(circle at 20% 30%, rgba(0, 229, 255, 0.1) 0%, transparent 50%),
                        radial-gradient(circle at 80% 70%, rgba(0, 200, 83, 0.08) 0%, transparent 50%);
            animation: gradient-shift 15s ease infinite;
        }
        
        @keyframes gradient-shift {
            0%, 100% { transform: translate(0, 0) rotate(0deg); }
            50% { transform: translate(-5%, -5%) rotate(5deg); }
        }
        
        .login-container {
            position: relative;
            z-index: 1;
            background: var(--glass);
            backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 24px;
            padding: 50px 40px;
            width: 100%;
            max-width: 420px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }
        
        .login-header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .login-header h1 {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }
        
        .login-header p {
            color: rgba(230, 241, 255, 0.6);
            font-size: 0.95rem;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: rgba(230, 241, 255, 0.8);
            font-weight: 500;
            font-size: 0.9rem;
        }
        
        .form-group input {
            width: 100%;
            padding: 14px 18px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            color: var(--text);
            font-size: 1rem;
            font-family: 'Inter', sans-serif;
            transition: all 0.3s ease;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: var(--accent);
            background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 0 0 3px rgba(0, 229, 255, 0.1);
        }
        
        .btn-login {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, var(--accent), #00C853);
            border: none;
            border-radius: 12px;
            color: white;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0, 229, 255, 0.3);
        }
        
        .btn-login:active {
            transform: translateY(0);
        }
        
        .alert {
            padding: 14px 18px;
            border-radius: 12px;
            margin-bottom: 25px;
            font-size: 0.9rem;
        }
        
        .alert-error {
            background: rgba(255, 82, 82, 0.1);
            border: 1px solid rgba(255, 82, 82, 0.3);
            color: #FF5252;
        }
        
        .security-note {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid var(--glass-border);
            text-align: center;
            font-size: 0.85rem;
            color: rgba(230, 241, 255, 0.5);
        }
    </style>
</head>
<body>
    <div class="bg-animation">
        <div class="bg-gradient"></div>
    </div>
    
    <div class="login-container">
        <div class="login-header">
            <h1>🔒 Admin Login</h1>
            <p>Network Monitoring Dashboard</p>
        </div>
        
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="alert alert-error">
                    {{ messages[0] }}
                </div>
            {% endif %}
        {% endwith %}
        
        <form method="POST" action="{{ url_for('login') }}">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autofocus>
            </div>
            
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            
            <button type="submit" class="btn-login">Login</button>
        </form>
        
        <div class="security-note">
            🛡️ Secure access only • Default: admin/admin123
        </div>
    </div>
</body>
</html>
"""

# Updated dashboard HTML with healing information
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Network Monitoring Dashboard</title>
    <meta http-equiv="refresh" content="10">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #0A192F;
            --accent: #00E5FF;
            --online: #00C853;
            --warning: #FFC400;
            --offline: #FF5252;
            --healing: #9C27B0;
            --text: #E6F1FF;
            --glass: rgba(255, 255, 255, 0.05);
            --glass-border: rgba(255, 255, 255, 0.1);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--primary);
            color: var(--text);
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
        }
        
        .bg-animation {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            overflow: hidden;
        }
        
        .bg-gradient {
            position: absolute;
            width: 150%;
            height: 150%;
            background: radial-gradient(circle at 20% 30%, rgba(0, 229, 255, 0.1) 0%, transparent 50%),
                        radial-gradient(circle at 80% 70%, rgba(0, 200, 83, 0.08) 0%, transparent 50%),
                        radial-gradient(circle at 40% 80%, rgba(255, 196, 0, 0.06) 0%, transparent 50%);
            animation: gradient-shift 15s ease infinite;
        }
        
        @keyframes gradient-shift {
            0%, 100% { transform: translate(0, 0) rotate(0deg); }
            33% { transform: translate(-5%, -5%) rotate(5deg); }
            66% { transform: translate(5%, 5%) rotate(-5deg); }
        }
        
        .grid-overlay {
            position: absolute;
            width: 100%;
            height: 100%;
            background-image: 
                linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px);
            background-size: 50px 50px;
            animation: grid-move 20s linear infinite;
        }
        
        @keyframes grid-move {
            0% { transform: translate(0, 0); }
            100% { transform: translate(50px, 50px); }
        }
        
        .container {
            position: relative;
            z-index: 1;
            max-width: 1600px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 50px;
            animation: fadeInDown 0.8s ease;
        }
        
        @keyframes fadeInDown {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .header-left {
            text-align: left;
        }
        
        .header-left h1 {
            font-size: 3.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 15px;
            letter-spacing: -2px;
        }
        
        .header-subtitle {
            font-size: 1rem;
            color: rgba(230, 241, 255, 0.6);
            font-weight: 400;
            letter-spacing: 2px;
            text-transform: uppercase;
        }
        
        .header-right {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        
        .refresh-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 20px;
            background: var(--glass);
            backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 50px;
            font-size: 0.85rem;
            color: rgba(230, 241, 255, 0.8);
        }
        
        .refresh-badge::before {
            content: "●";
            color: var(--accent);
            animation: pulse 2s ease infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        
        .logout-btn {
            padding: 10px 24px;
            background: rgba(255, 82, 82, 0.2);
            border: 1px solid rgba(255, 82, 82, 0.4);
            border-radius: 50px;
            color: #FF5252;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.85rem;
            transition: all 0.3s ease;
        }
        
        .logout-btn:hover {
            background: rgba(255, 82, 82, 0.3);
            transform: translateY(-2px);
        }
        
        .stats-overview {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
            animation: fadeInUp 0.8s ease 0.2s backwards;
        }
        
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .stat-card {
            background: var(--glass);
            backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 25px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, var(--accent), var(--online));
            transform: scaleX(0);
            transform-origin: left;
            transition: transform 0.3s ease;
        }
        
        .stat-card:hover::before {
            transform: scaleX(1);
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            border-color: rgba(0, 229, 255, 0.3);
            box-shadow: 0 20px 60px rgba(0, 229, 255, 0.2);
        }
        
        .stat-label {
            font-size: 0.85rem;
            color: rgba(230, 241, 255, 0.6);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--text);
        }
        
        .device-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }
        
        .device-card {
            background: var(--glass);
            backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 24px;
            padding: 30px;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
            animation: fadeInUp 0.8s ease backwards;
        }
        
        .device-card:nth-child(1) { animation-delay: 0.3s; }
        .device-card:nth-child(2) { animation-delay: 0.4s; }
        .device-card:nth-child(3) { animation-delay: 0.5s; }
        .device-card:nth-child(4) { animation-delay: 0.6s; }
        
        .device-card::before {
            content: '';
            position: absolute;
            top: -2px;
            left: -2px;
            right: -2px;
            bottom: -2px;
            background: linear-gradient(45deg, var(--accent), var(--online), var(--warning));
            border-radius: 24px;
            opacity: 0;
            transition: opacity 0.3s ease;
            z-index: -1;
        }
        
        .device-card:hover::before {
            opacity: 0.1;
        }
        
        .device-card:hover {
            transform: translateY(-8px) scale(1.02);
            border-color: rgba(0, 229, 255, 0.3);
            box-shadow: 0 25px 80px rgba(0, 229, 255, 0.15);
        }
        
        .device-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(230, 241, 255, 0.1);
        }
        
        .device-name {
            font-size: 1.6rem;
            font-weight: 600;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .device-icon {
            width: 40px;
            height: 40px;
            background: var(--glass);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
        }
        
        .status-badge {
            padding: 10px 18px;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 8px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.2);
        }
        
        .status-badge::before {
            content: '';
            width: 8px;
            height: 8px;
            border-radius: 50%;
            animation: pulse-dot 2s ease infinite;
        }
        
        @keyframes pulse-dot {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.3); opacity: 0.7; }
        }
        
        .status-online {
            background: linear-gradient(135deg, var(--online), #00E676);
            color: white;
        }
        
        .status-online::before {
            background: white;
        }
        
        .status-offline {
            background: linear-gradient(135deg, var(--offline), #FF1744);
            color: white;
        }
        
        .status-offline::before {
            background: white;
        }
        
        .device-info {
            display: grid;
            gap: 15px;
            margin-bottom: 25px;
        }
        
        .info-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid rgba(230, 241, 255, 0.05);
        }
        
        .info-label {
            color: rgba(230, 241, 255, 0.6);
            font-size: 0.9rem;
            font-weight: 500;
        }
        
        .info-value {
            color: var(--text);
            font-weight: 600;
            font-size: 0.95rem;
        }
        
        .info-value.highlight {
            color: var(--accent);
        }
        
        .healing-badge {
            padding: 6px 14px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.8rem;
            background: rgba(156, 39, 176, 0.2);
            color: var(--healing);
            border: 1px solid var(--healing);
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        
        .healing-badge::before {
            content: '🔧';
            font-size: 0.9rem;
        }
        
        .uptime-container {
            margin-top: 20px;
        }
        
        .uptime-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        
        .uptime-label {
            font-size: 0.9rem;
            color: rgba(230, 241, 255, 0.7);
            font-weight: 500;
        }
        
        .uptime-value {
            font-size: 1.4rem;
            font-weight: 700;
            color: var(--text);
        }
        
        .progress-bar-container {
            height: 12px;
            background: rgba(230, 241, 255, 0.05);
            border-radius: 50px;
            overflow: hidden;
            position: relative;
            box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.2);
        }
        
        .progress-bar-fill {
            height: 100%;
            border-radius: 50px;
            background: linear-gradient(90deg, var(--online), var(--accent));
            transition: width 1s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        
        .progress-bar-fill::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg, 
                transparent 0%, 
                rgba(255, 255, 255, 0.3) 50%, 
                transparent 100%);
            animation: shimmer 2s infinite;
        }
        
        @keyframes shimmer {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }
        
        .logs-section {
            background: var(--glass);
            backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 24px;
            padding: 35px;
            margin-bottom: 40px;
            animation: fadeInUp 0.8s ease 0.7s backwards;
        }
        
        .logs-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid rgba(0, 229, 255, 0.2);
        }
        
        .logs-title {
            font-size: 2rem;
            font-weight: 700;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .log-count {
            padding: 8px 16px;
            background: var(--glass);
            border: 1px solid var(--glass-border);
            border-radius: 50px;
            font-size: 0.85rem;
            color: rgba(230, 241, 255, 0.8);
        }
        
        .log-table-container {
            overflow-x: auto;
            border-radius: 16px;
        }
        
        .log-table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .log-table thead {
            background: rgba(0, 229, 255, 0.05);
        }
        
        .log-table th {
            padding: 18px 16px;
            text-align: left;
            font-weight: 600;
            font-size: 0.85rem;
            color: rgba(230, 241, 255, 0.8);
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 2px solid rgba(0, 229, 255, 0.2);
        }
        
        .log-table td {
            padding: 16px;
            border-bottom: 1px solid rgba(230, 241, 255, 0.05);
            color: var(--text);
            font-size: 0.9rem;
        }
        
        .log-table tbody tr {
            transition: all 0.2s ease;
        }
        
        .log-table tbody tr:hover {
            background: rgba(0, 229, 255, 0.05);
        }
        
        .log-status {
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.8rem;
            text-transform: uppercase;
            display: inline-block;
        }
        
        .log-status.online {
            background: rgba(0, 200, 83, 0.2);
            color: var(--online);
            border: 1px solid var(--online);
        }
        
        .log-status.offline {
            background: rgba(255, 82, 82, 0.2);
            color: var(--offline);
            border: 1px solid var(--offline);
        }
        
        .log-status.success {
            background: rgba(0, 200, 83, 0.2);
            color: var(--online);
            border: 1px solid var(--online);
        }
        
        .log-status.failed {
            background: rgba(255, 82, 82, 0.2);
            color: var(--offline);
            border: 1px solid var(--offline);
        }
        
        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }
        
        ::-webkit-scrollbar-track {
            background: rgba(230, 241, 255, 0.02);
            border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: rgba(0, 229, 255, 0.3);
            border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(0, 229, 255, 0.5);
        }
        
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                gap: 20px;
            }
            
            .header-left h1 {
                font-size: 2.5rem;
            }
            
            .device-grid {
                grid-template-columns: 1fr;
            }
            
            .stats-overview {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .log-table {
                font-size: 0.8rem;
            }
        }
    </style>
</head>
<body>
    <div class="bg-animation">
        <div class="bg-gradient"></div>
        <div class="grid-overlay"></div>
    </div>
    
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>Network Monitor</h1>
                <div class="header-subtitle">Real-Time System Status</div>
            </div>
            <div class="header-right">
                <div class="refresh-badge">Live • Updated {{ current_time }}</div>
                <a href="{{ url_for('logout') }}" class="logout-btn">🚪 Logout</a>
            </div>
        </div>
        
        <div class="stats-overview">
            <div class="stat-card">
                <div class="stat-label">Total Devices</div>
                <div class="stat-value">{{ devices|length }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Online</div>
                <div class="stat-value" style="color: var(--online);">{{ devices.values()|selectattr('online')|list|length }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Offline</div>
                <div class="stat-value" style="color: var(--offline);">{{ devices.values()|rejectattr('online')|list|length }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Healing Attempts</div>
                <div class="stat-value" style="color: var(--healing);">{{ total_healing_attempts }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Uptime</div>
                <div class="stat-value" style="color: var(--accent);">
                    {% if stats %}
                        {{ "%.1f"|format(stats.values()|map(attribute='uptime_percentage')|sum / stats.values()|list|length) }}%
                    {% else %}
                        0%
                    {% endif %}
                </div>
            </div>
        </div>
        
        <div class="device-grid">
            {% for ip, device in devices.items() %}
            <div class="device-card">
                <div class="device-header">
                    <div class="device-name">
                        <div class="device-icon">
                            {% if device.online %}🟢{% else %}🔴{% endif %}
                        </div>
                        {{ device.label }}
                    </div>
                    <div class="status-badge {% if device.online %}status-online{% else %}status-offline{% endif %}">
                        {% if device.online %}Online{% else %}Offline{% endif %}
                    </div>
                </div>
                
                <div class="device-info">
                    <div class="info-row">
                        <span class="info-label">IP Address</span>
                        <span class="info-value highlight">{{ ip }}</span>
                    </div>
                    
                    {% if device.online and device.response_time %}
                    <div class="info-row">
                        <span class="info-label">Response Time</span>
                        <span class="info-value">{{ device.response_time }} ms</span>
                    </div>
                    {% endif %}
                    
                    <div class="info-row">
                        <span class="info-label">Last Seen</span>
                        <span class="info-value">{{ device.last_seen }}</span>
                    </div>
                    
                    {% if device.consecutive_failures > 0 %}
                    <div class="info-row">
                        <span class="info-label">Failures</span>
                        <span class="info-value" style="color: var(--offline);">{{ device.consecutive_failures }}</span>
                    </div>
                    {% endif %}
                    
                    {% if device.healing_attempts > 0 %}
                    <div class="info-row">
                        <span class="info-label">Healing Status</span>
                        <span class="healing-badge">{{ device.healing_attempts }} attempt(s)</span>
                    </div>
                    {% endif %}
                </div>
                
                {% if stats.get(ip) %}
                <div class="uptime-container">
                    <div class="uptime-header">
                        <span class="uptime-label">Uptime</span>
                        <span class="uptime-value">{{ stats[ip].uptime_percentage }}%</span>
                    </div>
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" style="width: {{ stats[ip].uptime_percentage }}%"></div>
                    </div>
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        
        {% if healing_logs %}
        <div class="logs-section">
            <div class="logs-header">
                <div class="logs-title">🔧 Healing History</div>
                <div class="log-count">{{ healing_logs|length }} attempts</div>
            </div>
            <div class="log-table-container">
                <table class="log-table">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Device</th>
                            <th>IP Address</th>
                            <th>Status</th>
                            <th>Attempt</th>
                            <th>Commands</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for log in healing_logs %}
                        <tr>
                            <td>{{ log.timestamp }}</td>
                            <td><strong>{{ log.label }}</strong></td>
                            <td>{{ log.ip }}</td>
                            <td>
                                <span class="log-status {{ log.result }}">
                                    {{ log.result }}
                                </span>
                            </td>
                            <td>{{ log.attempt_number }}</td>
                            <td>{{ log.commands_executed }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}
        
        <div class="logs-section">
            <div class="logs-header">
                <div class="logs-title">📊 Recent Activity</div>
                <div class="log-count">{{ recent_logs|length }} events</div>
            </div>
            <div class="log-table-container">
                <table class="log-table">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Device</th>
                            <th>IP Address</th>
                            <th>Status</th>
                            <th>Response</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for log in recent_logs %}
                        <tr>
                            <td>{{ log.timestamp }}</td>
                            <td><strong>{{ log.label }}</strong></td>
                            <td>{{ log.ip }}</td>
                            <td>
                                <span class="log-status {{ log.status }}">
                                    {{ log.status }}
                                </span>
                            </td>
                            <td>
                                {% if log.response_time_ms %}
                                    {{ log.response_time_ms }} ms
                                {% else %}
                                    <span style="color: rgba(230, 241, 255, 0.4);">—</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    """Logout and clear session."""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    """
    Main dashboard route displaying device status and logs.
    
    Returns:
        str: Rendered HTML dashboard
    """
    # Get current device status from monitor
    devices = {}
    if monitor:
        device_status = monitor.get_device_status()
        
        for ip, status in device_status.items():
            # Get healing attempts for this device
            healing_attempts = 0
            if healer:
                healing_attempts = healer.healing_history.get(ip, 0)
            
            devices[ip] = {
                'label': status['label'],
                'online': status['online'],
                'last_seen': status['last_seen'].strftime('%Y-%m-%d %H:%M:%S') if status['last_seen'] else 'Never',
                'consecutive_failures': status['consecutive_failures'],
                'response_time': None,
                'healing_attempts': healing_attempts
            }
    else:
        # Fallback if monitor not initialized
        config = load_config()
        for device in config['devices']:
            ip = device['ip']
            devices[ip] = {
                'label': device['label'],
                'online': False,
                'last_seen': 'Monitoring not started',
                'consecutive_failures': 0,
                'response_time': None,
                'healing_attempts': 0
            }
    
    # Get uptime statistics
    stats = calculate_uptime_stats()
    
    # Get recent logs
    recent_logs = get_recent_logs(limit=20)
    recent_logs.reverse()  # Show newest first
    
    # Get healing logs
    healing_logs = get_healing_logs(limit=20)
    healing_logs.reverse()  # Show newest first
    
    # Calculate total healing attempts
    total_healing_attempts = sum(h.get('attempt_number', 0) for h in healing_logs) if healing_logs else 0
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template_string(
        DASHBOARD_HTML,
        devices=devices,
        stats=stats,
        recent_logs=recent_logs,
        healing_logs=healing_logs,
        total_healing_attempts=total_healing_attempts,
        current_time=current_time
    )

@app.route('/api/status')
@login_required
def api_status():
    """
    API endpoint for current device status (JSON).
    
    Returns:
        json: Current status of all devices
    """
    if monitor:
        device_status = monitor.get_device_status()
        
        # Convert datetime objects to strings for JSON
        for ip in device_status:
            if device_status[ip]['last_seen']:
                device_status[ip]['last_seen'] = device_status[ip]['last_seen'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify(device_status)
    else:
        return jsonify({'error': 'Monitor not initialized'}), 503

@app.route('/api/stats')
@login_required
def api_stats():
    """
    API endpoint for uptime statistics (JSON).
    
    Returns:
        json: Uptime statistics for all devices
    """
    stats = calculate_uptime_stats()
    return jsonify(stats)

@app.route('/api/healing')
@login_required
def api_healing():
    """
    API endpoint for healing history (JSON).
    
    Returns:
        json: Healing history for all devices
    """
    healing_logs = get_healing_logs(limit=50)
    return jsonify(healing_logs)

def init_dashboard(monitor_instance, healer_instance):
    """
    Initialize dashboard with monitor and healer instances.
    
    Args:
        monitor_instance: NetworkMonitor instance
        healer_instance: DeviceHealer instance
    """
    global monitor, healer
    monitor = monitor_instance
    healer = healer_instance

def run_dashboard(threaded=False):
    """
    Start the Flask dashboard server.
    
    Args:
        threaded (bool): If True, disables debug mode for thread compatibility
    """
    config = load_config()
    dashboard_config = config['dashboard']
    
    # Disable debug mode when running in a thread (Windows compatibility)
    debug_mode = False if threaded else dashboard_config.get('debug', False)
    
    app.run(
        host=dashboard_config['host'],
        port=dashboard_config['port'],
        debug=debug_mode,
        use_reloader=False  # Disable reloader for thread safety
    )

if __name__ == '__main__':
    run_dashboard()