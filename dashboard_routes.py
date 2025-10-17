DEVICE_DETAIL_HTML = """
<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
        <title>{{ device.label }} - Device Details</title>
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
        .nav-links a { color: var(--text); text-decoration: none; font-weight: 500; }
        .container { max-width: 1600px; margin: 0 auto; padding: 40px 20px; }
        .page-header { margin-bottom: 40px; }
        .page-header h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .breadcrumb { color: rgba(230, 241, 255, 0.6); margin-bottom: 20px; }
        .breadcrumb a { color: var(--accent); text-decoration: none; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 40px; }
        .stat-card { background: var(--glass); backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border); border-radius: 16px; padding: 20px; }
        .stat-value { font-size: 2.5rem; font-weight: 700; color: var(--accent); margin: 10px 0; }
        .stat-label { font-size: 0.9rem; color: rgba(230, 241, 255, 0.6); text-transform: uppercase; }
        .info-section { background: var(--glass); backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border); border-radius: 16px; padding: 30px; margin-bottom: 30px; }
        .info-section h3 { font-size: 1.5rem; margin-bottom: 20px; color: var(--accent); }
        .info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
        .info-item { padding: 15px; background: rgba(255, 255, 255, 0.03); border-radius: 8px; }
        .info-label { font-size: 0.85rem; color: rgba(230, 241, 255, 0.6); text-transform: uppercase; margin-bottom: 5px; }
        .info-value { font-size: 1.1rem; font-weight: 600; }
        .chart-container { background: var(--glass); backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border); border-radius: 24px; padding: 30px; margin-bottom: 30px; }
        .chart-header { margin-bottom: 20px; }
        canvas { max-height: 300px; }
        .status-badge { padding: 8px 16px; border-radius: 20px; font-size: 0.9rem; font-weight: 600; display: inline-block; }
        .status-online { background: rgba(0, 200, 83, 0.2); color: var(--success); }
        .status-offline { background: rgba(255, 82, 82, 0.2); color: var(--error); }
        .btn { padding: 12px 24px; border-radius: 8px; border: none; font-weight: 600;
            cursor: pointer; transition: all 0.3s; text-decoration: none; display: inline-block; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-danger { background: var(--error); color: white; }
    </style>
</head>
<body>
    <nav class="nav">
        <div class="nav-brand">📡 Network Monitor</div>
        <div class="nav-links">
            <a href="{{ url_for('dashboard') }}">Dashboard</a>
            <a href="{{ url_for('add_device') }}">Add Device</a>
            <a href="{{ url_for('logout') }}">Logout</a>
        </div>
    </nav>
    <div class="container">
        <div class="breadcrumb">
            <a href="{{ url_for('dashboard') }}">Dashboard</a> / 
            <a href="{{ url_for('lab_detail', lab_id=lab_id) }}">{{ lab_name }}</a> / 
            {{ device.label }}
        </div>
        <div class="page-header">
            <h1>{{ device.label }}</h1>
            <p>{{ device.ip }}</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Status</div>
                <span class="status-badge status-{{ 'online' if device.online else 'offline' }}">
                    {{ 'Online' if device.online else 'Offline' }}
                </span>
            </div>
            <div class="stat-card">
                <div class="stat-label">Response Time</div>
                <div class="stat-value" style="font-size: 2rem;">
                    {{ '%.1f'|format(device.response_time) if device.response_time else 'N/A' }} ms
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Uptime (7 days)</div>
                <div class="stat-value" style="font-size: 2rem;">{{ '%.1f'|format(device.uptime_pct) }}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Failures</div>
                <div class="stat-value" style="font-size: 2rem; color: var(--warning);">{{ device.failures }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Healing Attempts</div>
                <div class="stat-value" style="font-size: 2rem; color: var(--accent);">{{ device.healing_attempts }}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Last Seen</div>
                <div class="stat-value" style="font-size: 1.3rem;">
                    {{ device.last_seen if device.last_seen else 'Never' }}
                </div>
            </div>
        </div>

        <div class="info-section">
            <h3>Device Configuration</h3>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">IP Address</div>
                    <div class="info-value">{{ device.ip }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Device Name</div>
                    <div class="info-value">{{ device.label }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">SSH Enabled</div>
                    <div class="info-value">{{ 'Yes' if device.ssh_enabled else 'No' }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Ping Check</div>
                    <div class="info-value">{{ 'Enabled' if device.health_checks.ping else 'Disabled' }}</div>
                </div>
                {% if device.ssh_enabled %}
                <div class="info-item">
                    <div class="info-label">SSH Username</div>
                    <div class="info-value">{{ device.ssh_username }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">SSH Port</div>
                    <div class="info-value">{{ device.ssh_port }}</div>
                </div>
                {% endif %}
            </div>
        </div>

        <div class="chart-container">
            <div class="chart-header">
                <h3>Response Time History (Last 24 Hours)</h3>
            </div>
            <canvas id="responseChart"></canvas>
        </div>

        <div class="chart-container">
            <div class="chart-header">
                <h3>Uptime History (Last 7 Days)</h3>
            </div>
            <canvas id="uptimeChart"></canvas>
        </div>

        {% if device.performance_metrics %}
        <div class="info-section">
            <h3>Performance Metrics</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">CPU Usage</div>
                    <div class="stat-value" style="font-size: 2rem;">{{ device.performance_metrics.cpu_usage }}%</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Memory Usage</div>
                    <div class="stat-value" style="font-size: 2rem;">{{ device.performance_metrics.memory_usage }}%</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Disk Usage</div>
                    <div class="stat-value" style="font-size: 2rem;">{{ device.performance_metrics.disk_usage }}%</div>
                </div>
                {% if device.performance_metrics.network_in_mbps %}
                <div class="stat-card">
                    <div class="stat-label">Network In</div>
                    <div class="stat-value" style="font-size: 1.8rem;">{{ device.performance_metrics.network_in_mbps }} MB</div>
                </div>
                {% endif %}
                {% if device.performance_metrics.network_out_mbps %}
                <div class="stat-card">
                    <div class="stat-label">Network Out</div>
                    <div class="stat-value" style="font-size: 1.8rem;">{{ device.performance_metrics.network_out_mbps }} MB</div>
                </div>
                {% endif %}
            </div>
        </div>
        {% endif %}
    </div>
    <script>
        const responseCtx = document.getElementById('responseChart');
        new Chart(responseCtx, {
            type: 'line',
            data: {
                labels: {{ response_labels|tojson }},
                datasets: [{
                    label: 'Response Time (ms)',
                    data: {{ response_data|tojson }},
                    borderColor: '#00E5FF',
                    backgroundColor: 'rgba(0, 229, 255, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#E6F1FF' } } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(230, 241, 255, 0.1)' }, ticks: { color: '#E6F1FF' } },
                    x: { grid: { color: 'rgba(230, 241, 255, 0.1)' }, ticks: { color: '#E6F1FF' } }
                }
            }
        });

        const uptimeCtx = document.getElementById('uptimeChart');
        new Chart(uptimeCtx, {
            type: 'bar',
            data: {
                labels: {{ uptime_labels|tojson }},
                datasets: [{
                    label: 'Uptime %',
                    data: {{ uptime_data|tojson }},
                    backgroundColor: 'rgba(0, 200, 83, 0.6)',
                    borderColor: '#00C853',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#E6F1FF' } } },
                scales: {
                    y: { beginAtZero: true, max: 100, grid: { color: 'rgba(230, 241, 255, 0.1)' }, ticks: { color: '#E6F1FF' } },
                    x: { grid: { color: 'rgba(230, 241, 255, 0.1)' }, ticks: { color: '#E6F1FF' } }
                }
            }
        });
    </script>
</body>
</html>
"""

ADD_DEVICE_HTML = """
<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
        <title>Add Device - Network Monitor</title>
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
        .form-section { margin-bottom: 30px; }
        .form-section h3 { font-size: 1.3rem; margin-bottom: 20px; color: var(--accent); }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; color: rgba(230, 241, 255, 0.8);
            font-weight: 500; font-size: 0.95rem; }
        .form-group input, .form-group select, .form-group textarea {
            width: 100%; padding: 12px 16px; background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--glass-border); border-radius: 8px; color: var(--text);
            font-size: 1rem; font-family: 'Inter', sans-serif; transition: all 0.3s ease; }
        .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
            outline: none; border-color: var(--accent); background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 0 0 3px rgba(0, 229, 255, 0.1); }
        .form-group textarea { resize: vertical; min-height: 80px; }
        .checkbox-group { display: flex; align-items: center; gap: 10px; }
        .checkbox-group input[type="checkbox"] { width: auto; }
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
        .help-text { font-size: 0.85rem; color: rgba(230, 241, 255, 0.5); margin-top: 5px; }
        .ssh-section { background: rgba(255, 255, 255, 0.02); padding: 20px; border-radius: 12px; margin-top: 15px; }
    </style>
</head>
<body>
    <nav class="nav">
        <div class="nav-brand">📡 Network Monitor</div>
        <div class="nav-links">
            <a href="{{ url_for('dashboard') }}">Dashboard</a>
            <a href="{{ url_for('add_device') }}">Add Device</a>
            <a href="{{ url_for('logout') }}">Logout</a>
        </div>
    </nav>
    <div class="container">
        <div class="page-header">
            <h1>{% if lab_id %}Add Device to {{ lab_name }}{% else %}Add New Device{% endif %}</h1>
            <p>Configure a new device for monitoring</p>
        </div>
        
        <div class="form-container">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <form method="POST" action="{{ url_for('add_device_to_lab', lab_id=lab_id) if lab_id else url_for('add_device') }}">
                <div class="form-section">
                    <h3>Basic Information</h3>
                    
                    {% if not lab_id %}
                    <div class="form-group">
                        <label for="lab_id">Lab</label>
                        <select id="lab_id" name="lab_id" required>
                            <option value="">Select a lab...</option>
                            {% for lab_id_opt, lab in labs.items() %}
                            <option value="{{ lab_id_opt }}">{{ lab.name }} - {{ lab.location }}</option>
                            {% endfor %}
                        </select>
                        <div class="help-text">Or <a href="#" onclick="createNewLab()">create a new lab</a></div>
                    </div>
                    {% endif %}
                    
                    <div class="form-group">
                        <label for="label">Device Name</label>
                        <input type="text" id="label" name="label" required placeholder="e.g., Main Router, PC-Lab1-01">
                        <div class="help-text">A friendly name to identify this device</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="ip">IP Address</label>
                        <input type="text" id="ip" name="ip" required placeholder="e.g., 192.168.1.100">
                        <div class="help-text">The IP address to monitor</div>
                    </div>
                </div>

                <div class="form-section">
                    <h3>Health Check Configuration</h3>
                    
                    <div class="checkbox-group form-group">
                        <input type="checkbox" id="ping_check" name="ping_check" checked>
                        <label for="ping_check" style="margin-bottom: 0;">Enable Ping Monitoring</label>
                    </div>
                    
            <div class="checkbox-group form-group">
                <input type="checkbox" id="http_enabled" name="http_enabled" onchange="toggleHTTP()">
                <label for="http_enabled" style="margin-bottom: 0;">Enable HTTP Monitoring</label>
            </div>

            <div id="http-config" class="ssh-section" style="display: none;">
                <div class="form-group">
                    <label for="http_url">HTTP URL</label>
                    <input type="text" id="http_url" name="http_url" placeholder="e.g., http://192.168.1.100:80/health">
                    <div class="help-text">Full URL to check; HTTPS supported.</div>
                </div>
                <div class="form-group">
                    <label for="http_expected_status">Expected Status</label>
                    <input type="number" id="http_expected_status" name="http_expected_status" value="200" placeholder="200">
                    <div class="help-text">HTTP status code expected from the endpoint.</div>
                </div>
            </div>

                    <div class="checkbox-group form-group">
                        <input type="checkbox" id="ssh_enabled" name="ssh_enabled" onchange="toggleSSH()">
                        <label for="ssh_enabled" style="margin-bottom: 0;">Enable SSH for Auto-Healing</label>
                    </div>
                    
                    <div id="ssh-config" class="ssh-section" style="display: none;">
                        <div class="form-group">
                            <label for="ssh_username">SSH Username</label>
                            <input type="text" id="ssh_username" name="ssh_username" placeholder="e.g., admin">
                        </div>
                        
                        <div class="form-group">
                            <label for="ssh_password">SSH Password</label>
                            <input type="password" id="ssh_password" name="ssh_password" placeholder="Enter SSH password">
                            <div class="help-text">⚠️ Password is stored encrypted in config</div>
                        </div>
                        
                        <div class="form-group">
                            <label for="ssh_port">SSH Port</label>
                            <input type="number" id="ssh_port" name="ssh_port" value="22" placeholder="22">
                        </div>
                    </div>
                </div>

                <div class="btn-group">
                    <button type="submit" class="btn btn-primary">Add Device</button>
                    <a href="{{ url_for('lab_detail', lab_id=lab_id) if lab_id else url_for('dashboard') }}" class="btn btn-secondary">Cancel</a>
                </div>
            </form>
        </div>
    </div>
    
    <script>
        function toggleSSH() {
            const checkbox = document.getElementById('ssh_enabled');
            const sshConfig = document.getElementById('ssh-config');
            sshConfig.style.display = checkbox.checked ? 'block' : 'none';
        }
        function toggleHTTP() {
            const checkbox = document.getElementById('http_enabled');
            const httpConfig = document.getElementById('http-config');
            httpConfig.style.display = checkbox.checked ? 'block' : 'none';
        }
        
        function createNewLab() {
            const labName = prompt('Enter new lab name:');
            const labLocation = prompt('Enter lab location:');
            if (labName && labLocation) {
                fetch('/api/create_lab', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: labName, location: labLocation})
                }).then(response => response.json())
                  .then(data => {
                      if (data.success) {
                          location.reload();
                      } else {
                          alert('Error creating lab: ' + data.message);
                      }
                  });
            }
        }
    </script>
</body>
</html>
"""