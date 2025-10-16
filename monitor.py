import json
import os
import time
from datetime import datetime
from ping3 import ping
import pandas as pd
from threading import Lock

class NetworkMonitor:
    """
    Monitors network devices by pinging them periodically and logging status.
    """
    
    def __init__(self, config_path='config.json'):
        """
        Initialize monitor with configuration.
        
        Args:
            config_path (str): Path to config.json file
        """
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.devices = self.config['devices']
        self.ping_timeout = self.config['monitoring']['ping_timeout_seconds']
        self.failure_threshold = self.config['monitoring']['failure_threshold']
        
        # Track consecutive failures for each device
        self.failure_counts = {device['ip']: 0 for device in self.devices}
        
        # Store current status and last seen time
        self.device_status = {}
        for device in self.devices:
            self.device_status[device['ip']] = {
                'online': False,
                'last_seen': None,
                'consecutive_failures': 0,
                'label': device['label']
            }
        
        # Thread lock for safe concurrent access
        self.lock = Lock()
        
        # Initialize logging
        self._init_logging()
    
    def _init_logging(self):
        """
        Create logs directory and CSV file if they don't exist.
        """
        log_dir = self.config['logging']['log_directory']
        self.log_file = os.path.join(log_dir, self.config['logging']['log_file'])
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Create CSV with headers if it doesn't exist
        if not os.path.exists(self.log_file):
            df = pd.DataFrame(columns=['timestamp', 'ip', 'label', 'status', 'response_time_ms'])
            df.to_csv(self.log_file, index=False)
    
    def ping_device(self, ip, timeout=None):
        """
        Ping a single device and return response time.
        
        Args:
            ip (str): IP address to ping
            timeout (int): Ping timeout in seconds
        
        Returns:
            float or None: Response time in seconds, or None if unreachable
        """
        if timeout is None:
            timeout = self.ping_timeout
        
        try:
            # ping3 returns response time in seconds, or None/False if failed
            response = ping(ip, timeout=timeout, unit='s')
            return response if response else None
        except Exception as e:
            print(f"Error pinging {ip}: {str(e)}")
            return None
    
    def check_device(self, device):
        """
        Check a single device status and update internal state.
        
        Args:
            device (dict): Device configuration dictionary
        
        Returns:
            dict: Status information including online/offline and response time
        """
        ip = device['ip']
        label = device['label']
        
        response_time = self.ping_device(ip)
        
        with self.lock:
            if response_time is not None:
                # Device is online
                self.device_status[ip]['online'] = True
                self.device_status[ip]['last_seen'] = datetime.now()
                self.device_status[ip]['consecutive_failures'] = 0
                self.failure_counts[ip] = 0
                
                status_info = {
                    'ip': ip,
                    'label': label,
                    'online': True,
                    'response_time_ms': round(response_time * 1000, 2)
                }
            else:
                # Device is offline
                self.device_status[ip]['online'] = False
                self.device_status[ip]['consecutive_failures'] += 1
                self.failure_counts[ip] += 1
                
                status_info = {
                    'ip': ip,
                    'label': label,
                    'online': False,
                    'response_time_ms': None,
                    'consecutive_failures': self.device_status[ip]['consecutive_failures']
                }
        
        return status_info
    
    def log_status(self, status_info):
        """
        Log device status to CSV file.
        
        Args:
            status_info (dict): Status information from check_device()
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        log_entry = {
            'timestamp': timestamp,
            'ip': status_info['ip'],
            'label': status_info['label'],
            'status': 'online' if status_info['online'] else 'offline',
            'response_time_ms': status_info.get('response_time_ms', None)
        }
        
        # Append to CSV
        df = pd.DataFrame([log_entry])
        df.to_csv(self.log_file, mode='a', header=False, index=False)
    
    def check_all_devices(self):
        """
        Check all configured devices and log their status.
        
        Returns:
            list: List of status information for all devices
        """
        results = []
        
        for device in self.devices:
            status_info = self.check_device(device)
            self.log_status(status_info)
            results.append(status_info)
            
            # Print status
            if status_info['online']:
                print(f"✓ {status_info['label']} ({status_info['ip']}): ONLINE - {status_info['response_time_ms']}ms")
            else:
                failures = status_info.get('consecutive_failures', 0)
                print(f"✗ {status_info['label']} ({status_info['ip']}): OFFLINE - {failures} consecutive failures")
        
        return results
    
    def get_device_status(self):
        """
        Get current status of all devices (thread-safe).
        
        Returns:
            dict: Current device status dictionary
        """
        with self.lock:
            return self.device_status.copy()
    
    def should_trigger_healing(self, ip):
        """
        Check if a device has exceeded failure threshold and needs healing.
        
        Args:
            ip (str): Device IP address
        
        Returns:
            bool: True if healing should be triggered
        """
        with self.lock:
            return self.failure_counts[ip] >= self.failure_threshold
    
    def reset_failure_count(self, ip):
        """
        Reset failure count after healing attempt.
        
        Args:
            ip (str): Device IP address
        """
        with self.lock:
            self.failure_counts[ip] = 0
            self.device_status[ip]['consecutive_failures'] = 0


# Example usage
if __name__ == '__main__':
    monitor = NetworkMonitor()
    
    print("Starting network monitoring...")
    print(f"Monitoring {len(monitor.devices)} devices\n")
    
    # Run a single check
    monitor.check_all_devices()
    
    print("\nMonitoring complete. Check logs/uptime.csv for results.")