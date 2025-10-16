# Self-Healing Network Monitoring System

A Python-based network monitoring system that automatically detects device failures and attempts SSH-based recovery.

## Features

- **Real-time Monitoring**: Continuously ping devices and track their status
- **Automatic Healing**: SSH into failed devices and run recovery commands
- **Web Dashboard**: Beautiful Flask-based UI showing live status and uptime stats
- **Detailed Logging**: CSV logs with timestamps, response times, and status changes
- **Configurable Thresholds**: Set failure thresholds and healing attempt limits
- **Thread-safe**: Safe concurrent access to device status

## Project Structure

```
self-healing-network/
├── config.json          # Device configuration
├── monitor.py           # Ping monitoring and logging
├── healer.py           # SSH-based recovery
├── dashboard.py        # Flask web interface
├── main.py             # System orchestrator
├── requirements.txt    # Python dependencies
└── logs/
    └── uptime.csv      # Status logs (auto-created)
```

## Installation

1. **Clone or create the project directory**:
```bash
mkdir self-healing-network
cd self-healing-network
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

**Note for ping3**: On Linux/Mac, you may need to run with sudo or set capabilities:
```bash
# Option 1: Run with sudo
sudo python3 main.py

# Option 2: Set capabilities (Linux only)
sudo setcap cap_net_raw+ep $(which python3)
```

3. **Configure devices**:
Edit `config.json` with your network devices, SSH credentials, and healing commands.

## Configuration

Edit `config.json`:

```json
{
  "devices": [
    {
      "ip": "192.168.1.1",
      "label": "Router",
      "ssh_enabled": true,
      "ssh_username": "admin",
      "ssh_password": "your_password",
      "ssh_port": 22,
      "healing_commands": [
        "systemctl restart networking"
      ]
    }
  ],
  "monitoring": {
    "ping_interval_seconds": 30,
    "ping_timeout_seconds": 2,
    "failure_threshold": 3
  },
  "healing": {
    "enabled": true,
    "max_attempts": 2,
    "wait_between_attempts_seconds": 10
  }
}
```

### Configuration Options

- **devices**: Array of network devices to monitor
  - `ip`: Device IP address
  - `label`: Friendly name
  - `ssh_enabled`: Enable SSH healing (true/false)
  - `ssh_username/password`: SSH credentials
  - `healing_commands`: Commands to run for recovery

- **monitoring**:
  - `ping_interval_seconds`: How often to check devices
  - `ping_timeout_seconds`: Ping timeout
  - `failure_threshold`: Failures before triggering healing

- **healing**:
  - `enabled`: Enable/disable automatic healing
  - `max_attempts`: Max healing attempts per device
  - `wait_between_attempts_seconds`: Delay between attempts

## Usage

### Start the Complete System

```bash
python main.py
```

This starts:
- Monitoring loop (checks devices every N seconds)
- Automatic healing (triggers on threshold)
- Web dashboard (http://localhost:5000)

### Run Individual Components

**Test monitoring only**:
```bash
python monitor.py
```

**Test healing on a specific device**:
```bash
python healer.py
```

**Run dashboard only**:
```bash
python dashboard.py
```

## Dashboard

Access the web dashboard at: **http://localhost:5000**

The dashboard shows:
- ✅ **Live Status**: Real-time online/offline indicators
- 📊 **Uptime Statistics**: Historical uptime percentages
- ⏱️ **Response Times**: Average ping times
- 📝 **Recent Activity**: Last 20 status changes
- 🔄 **Auto-refresh**: Updates every 10 seconds

## How It Works

1. **Monitor** pings each device periodically
2. Tracks consecutive failures per device
3. When failures exceed threshold → **Healer** triggers
4. **Healer** SSH connects and runs recovery commands
5. After healing, resets failure counter
6. All activity logged to `logs/uptime.csv`
7. **Dashboard** displays live status and stats

## Healing Process

When a device fails the threshold:

1. Establish SSH connection
2. Execute healing commands sequentially
3. Log command output and errors
4. Close connection
5. Wait before next monitoring check
6. If device recovers → reset healing attempts
7. If max attempts reached → stop healing (manual intervention needed)

## Logs

Logs are stored in `logs/uptime.csv`:

```csv
timestamp,ip,label,status,response_time_ms
2025-10-14 10:30:00,192.168.1.1,Router,online,15.23
2025-10-14 10:30:30,192.168.1.1,Router,offline,
```

## Security Considerations

⚠️ **Important**:
- Store `config.json` securely (contains SSH passwords)
- Use strong SSH passwords or key-based authentication
- Limit SSH user permissions on devices
- Consider using environment variables for credentials
- Run on a secure internal network only

## Troubleshooting

**"Permission denied" when pinging**:
- Run with `sudo` or set capabilities (see Installation)

**"Connection refused" for SSH**:
- Verify SSH is enabled on the device
- Check firewall rules
- Confirm credentials are correct

**Dashboard not loading**:
- Check if port 5000 is available
- Look for Flask errors in console
- Try accessing http://127.0.0.1:5000

**Devices not being healed**:
- Check `healing.enabled` is `true` in config
- Verify `failure_threshold` is being reached
- Check SSH credentials are correct
- Review healing command syntax for the device OS

## Example Healing Commands

**Linux/Ubuntu devices**:
```json
"healing_commands": [
  "systemctl restart networking",
  "ip link set eth0 down && ip link set eth0 up"
]
```

**Cisco devices**:
```json
"healing_commands": [
  "reload in 1",
  "clear ip route *"
]
```

**Routers**:
```json
"healing_commands": [
  "reboot"
]
```

## Extending the System

Add custom features:
- **Email alerts**: Add SMTP notifications in `monitor.py`
- **Webhook integration**: POST status to external APIs
- **Database storage**: Replace CSV with SQLite/PostgreSQL
- **Multiple healing strategies**: Different commands based on failure type
- **Grafana integration**: Export metrics for visualization

## API Endpoints

The dashboard includes JSON APIs:

- `GET /api/status` - Current device status
- `GET /api/stats` - Uptime statistics

Example:
```bash
curl http://localhost:5000/api/status
```

## License

Open source - feel free to modify and extend!