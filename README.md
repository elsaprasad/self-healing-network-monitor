# Self Healing Network Monitoring System

Monitor multiple labs, auto-heal failed devices, and manage everything from a real-time dashboard.

## Features

- **Multi-lab monitoring** with ping, HTTP, SSH, and performance checks
- **Auto-healing** for offline devices (firewall fixes, network resets)
- **Real-time dashboard** with WebSocket updates
- **User management** (superadmin and lab admin roles)
- **SQLite storage** - no external database needed

## Quick Start

### Install

```bash
pip install -r requirements_enterprise.txt
```

### Run

```bash
python main_enterprise.py
```

### Login

Open `http://localhost:5000`

- Username: `admin`
- Password: `admin123`

## Configuration

Edit `config.json` to add labs and devices:

```json
{
  "labs": {
    "lab1": {
      "name": "Computer Lab",
      "location": "Building A",
      "devices": [
        {
          "ip": "192.168.1.100",
          "label": "PC-01",
          "ssh_enabled": true,
          "ssh_username": "admin",
          "ssh_password": "password",
          "health_checks": {
            "ping": true,
            "performance_metrics": true
          }
        }
      ]
    }
  }
}
```

## Key Settings

- `ping_interval_seconds`: How often to check devices (default: 30)
- `failure_threshold`: Failures before triggering healing (default: 3)
- `max_attempts`: Max healing attempts per device (default: 2)
- `healing.enabled`: Enable/disable auto-healing (default: true)

## Troubleshooting

**Device shows offline but it's reachable?**
- Check firewall allows ICMP ping
- Verify IP address is correct

**Auto-healing not working?**
- Ensure SSH is enabled on device
- Verify SSH credentials in config
- Check SSH port is accessible (22)

**Can't access dashboard?**
- Check port 5000 isn't in use
- Verify firewall allows port 5000

## File Structure

```
main_enterprise.py          # Start here
monitor_enhanced.py         # Monitoring logic
healer.py                   # Auto-healing
dashboard_enterprise.py     # Web dashboard
config.json                 # Configuration
monitoring_data.db          # Database (auto-created)
```

## Production

Change the secret key in `config.json`:

```json
"dashboard": {
  "secret_key": "your-random-secret-key-here"
}
```

Run with gunicorn:

```bash
pip install gunicorn eventlet
gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 main_enterprise:app
```
