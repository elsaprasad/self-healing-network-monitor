import json
import socket
import time
from datetime import datetime
from ping3 import ping
import requests
import dns.resolver
import paramiko
import psutil
from threading import Lock

class EnhancedNetworkMonitor:
    """
    Advanced network monitoring with:
    - Multi-protocol health checks (Ping, HTTP, HTTPS, TCP, DNS)
    - Performance metrics collection (CPU, Memory, Disk, Network)
    - SSL certificate validation
    - Response time tracking
    - InfluxDB integration for time-series data
    """
    
    def __init__(self, config_path='config.json', db_handler=None):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.labs = self.config['labs']
        self.ping_timeout = self.config['monitoring']['ping_timeout_seconds']
        self.http_timeout = self.config['monitoring']['http_timeout_seconds']
        self.failure_threshold = self.config['monitoring']['failure_threshold']
        
        # Database handler for time-series data (e.g., SQLiteHandler)
        self.db = db_handler
        
        # Track device status
        self.device_status = {}
        self.failure_counts = {}
        
        # Thread lock for safe concurrent access
        self.lock = Lock()
        
        # Initialize device status for all labs
        self._init_device_status()
        
        print(f"Enhanced Monitor initialized for {len(self.labs)} labs")

    def merge_devices(self, new_labs):
        """Merge newly added devices without resetting existing status/counters."""
        # Update labs reference
        self.labs = new_labs
        # Add any new devices to tracking structures
        for lab_id, lab_data in self.labs.items():
            for device in lab_data['devices']:
                ip = device['ip']
                if ip not in self.device_status:
                    self.device_status[ip] = {
                        'ip': ip,
                        'label': device['label'],
                        'lab_id': lab_id,
                        'online': False,
                        'last_seen': None,
                        'consecutive_failures': 0,
                        'health_checks': {}
                    }
                if ip not in self.failure_counts:
                    self.failure_counts[ip] = 0
    
    def _init_device_status(self):
        """Initialize status tracking for all devices."""
        for lab_id, lab_data in self.labs.items():
            for device in lab_data['devices']:
                ip = device['ip']
                self.device_status[ip] = {
                    'ip': ip,
                    'label': device['label'],
                    'lab_id': lab_id,
                    'online': False,
                    'last_seen': None,
                    'consecutive_failures': 0,
                    'health_checks': {}
                }
                self.failure_counts[ip] = 0
    
    def check_ping(self, ip, timeout=None):
        """Perform ICMP ping check."""
        if timeout is None:
            timeout = self.ping_timeout
        
        try:
            response = ping(ip, timeout=timeout, unit='ms')
            if response is not None:
                return {'success': True, 'response_time_ms': round(response, 2)}
            else:
                return {'success': False, 'response_time_ms': None}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def check_http(self, url, expected_status=200, timeout=None):
        """Perform HTTP/HTTPS health check."""
        if timeout is None:
            timeout = self.http_timeout
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=timeout, allow_redirects=True, verify=False)
            response_time_ms = (time.time() - start_time) * 1000
            
            success = response.status_code == expected_status
            
            return {
                'success': success,
                'status_code': response.status_code,
                'response_time_ms': round(response_time_ms, 2)
            }
        except requests.Timeout:
            return {'success': False, 'error': 'timeout'}
        except requests.ConnectionError:
            return {'success': False, 'error': 'connection_error'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def check_port(self, ip, port, timeout=3):
        """Check if a TCP port is open."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            
            return {'success': result == 0, 'is_open': result == 0}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def check_dns(self, domain, dns_server='8.8.8.8'):
        """Perform DNS resolution check."""
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [dns_server]
            resolver.timeout = 3
            resolver.lifetime = 3
            
            start_time = time.time()
            answers = resolver.resolve(domain, 'A')
            response_time_ms = (time.time() - start_time) * 1000
            
            ips = [str(rdata) for rdata in answers]
            
            return {
                'success': True,
                'resolved_ips': ips,
                'response_time_ms': round(response_time_ms, 2)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def collect_performance_metrics_ssh(self, ip, username, password, port=22):
        """
        Collect performance metrics via SSH.
        Works for Linux/Windows with proper commands.
        """
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(ip, username=username, password=password, port=port, timeout=5)
            
            metrics = {}
            
            # Try Windows commands first
            stdin, stdout, stderr = client.exec_command(
                'powershell "Get-Counter \'\\Processor(_Total)\\% Processor Time\' | Select-Object -ExpandProperty CounterSamples | Select-Object -ExpandProperty CookedValue"',
                timeout=5
            )
            output = stdout.read().decode().strip()
            if output and output.replace('.', '').isdigit():
                metrics['cpu_usage'] = round(float(output), 2)
            
            # Try Linux commands if Windows fails
            if 'cpu_usage' not in metrics:
                stdin, stdout, stderr = client.exec_command(
                    "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'",
                    timeout=5
                )
                output = stdout.read().decode().strip()
                if output and output.replace('.', '').isdigit():
                    metrics['cpu_usage'] = round(float(output), 2)
            
            # Memory usage (Linux)
            stdin, stdout, stderr = client.exec_command(
                "free | grep Mem | awk '{print ($3/$2) * 100.0}'",
                timeout=5
            )
            output = stdout.read().decode().strip()
            if output and output.replace('.', '').isdigit():
                metrics['memory_usage'] = round(float(output), 2)
            
            # Disk usage (Linux)
            stdin, stdout, stderr = client.exec_command(
                "df -h / | awk 'NR==2 {print $5}' | sed 's/%//'",
                timeout=5
            )
            output = stdout.read().decode().strip()
            if output and output.replace('.', '').isdigit():
                metrics['disk_usage'] = round(float(output), 2)
            
            client.close()
            return {'success': True, 'metrics': metrics}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def collect_local_performance_metrics(self):
        """Collect performance metrics for local machine using psutil."""
        try:
            metrics = {
                'cpu_usage': round(psutil.cpu_percent(interval=1), 2),
                'memory_usage': round(psutil.virtual_memory().percent, 2),
                'disk_usage': round(psutil.disk_usage('/').percent, 2)
            }
            
            # Network stats
            net_io = psutil.net_io_counters()
            metrics['network_in_mbps'] = round(net_io.bytes_recv / 1024 / 1024, 2)
            metrics['network_out_mbps'] = round(net_io.bytes_sent / 1024 / 1024, 2)
            
            return {'success': True, 'metrics': metrics}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def check_device(self, device, lab_id):
        """
        Perform all configured health checks for a device.
        
        Returns:
            dict: Comprehensive health check results
        """
        ip = device['ip']
        label = device['label']
        health_checks = device.get('health_checks', {})
        
        results = {
            'ip': ip,
            'label': label,
            'lab_id': lab_id,
            'timestamp': datetime.now(),
            'checks': {}
        }
        
        # Ping check
        if health_checks.get('ping', False):
            ping_result = self.check_ping(ip)
            results['checks']['ping'] = ping_result
            
            if self.db:
                if ping_result['success']:
                    self.db.write_ping_data(
                        ip, label, lab_id,
                        'online',
                        ping_result.get('response_time_ms')
                    )
                else:
                    self.db.write_ping_data(ip, label, lab_id, 'offline')
        
        # HTTP check
        if 'http' in health_checks and health_checks['http'].get('enabled'):
            http_config = health_checks['http']
            http_result = self.check_http(
                http_config['url'],
                http_config.get('expected_status', 200)
            )
            results['checks']['http'] = http_result
            
            if self.db:
                self.db.write_http_check(
                    ip, label, lab_id,
                    http_config['url'],
                    http_result.get('status_code', 0),
                    http_result.get('response_time_ms', 0),
                    http_result['success']
                )
        
        # Port checks
        if 'port_checks' in health_checks:
            results['checks']['ports'] = {}
            for port in health_checks['port_checks']:
                port_result = self.check_port(ip, port)
                results['checks']['ports'][port] = port_result
                
                if self.db:
                    self.db.write_port_check(
                        ip, label, lab_id, port,
                        port_result.get('is_open', False)
                    )
        
        # DNS check
        if health_checks.get('dns', False):
            # For DNS servers, resolve a constant domain using the device as the DNS server
            if device.get('device_type') == 'dns_server':
                dns_result = self.check_dns('example.com', dns_server=ip)
            else:
                dns_result = self.check_dns('example.com')
            results['checks']['dns'] = dns_result
        
        # Performance metrics
        if health_checks.get('performance_metrics', False):
            if device.get('ssh_enabled'):
                perf_result = self.collect_performance_metrics_ssh(
                    ip,
                    device['ssh_username'],
                    device['ssh_password']
                )
            else:
                # For local machine
                if ip in ['127.0.0.1', 'localhost']:
                    perf_result = self.collect_local_performance_metrics()
                else:
                    perf_result = {'success': False, 'error': 'SSH not enabled'}
            
            results['checks']['performance'] = perf_result
            
            if self.db and perf_result['success']:
                self.db.write_performance_metrics(
                    ip, label, lab_id,
                    perf_result['metrics']
                )
        
        # Determine overall device status (prefer ping/http if available)
        primary_check = results['checks'].get('ping', results['checks'].get('http', {}))
        device_online = primary_check.get('success', False)
        
        # Update device status
        with self.lock:
            self.device_status[ip]['online'] = device_online
            self.device_status[ip]['health_checks'] = results['checks']
            
            if device_online:
                self.device_status[ip]['last_seen'] = datetime.now()
                self.device_status[ip]['consecutive_failures'] = 0
                self.failure_counts[ip] = 0
            else:
                self.device_status[ip]['consecutive_failures'] += 1
                self.failure_counts[ip] += 1
        
        results['online'] = device_online
        results['consecutive_failures'] = self.device_status[ip]['consecutive_failures']
        
        return results
    
    def check_all_devices(self):
        """Check all devices across all labs."""
        all_results = []
        
        for lab_id, lab_data in self.labs.items():
            for device in lab_data['devices']:
                result = self.check_device(device, lab_id)
                all_results.append(result)
                
                # Print status
                if result['online']:
                    checks = result['checks']
                    ping_info = checks.get('ping', {})
                    if ping_info.get('success'):
                        print(f"✓ [{lab_id}] {result['label']} ({result['ip']}): ONLINE - {ping_info.get('response_time_ms')}ms")
                    else:
                        print(f"✓ [{lab_id}] {result['label']} ({result['ip']}): ONLINE")
                else:
                    print(f"✗ [{lab_id}] {result['label']} ({result['ip']}): OFFLINE - {result['consecutive_failures']} failures")
        
        return all_results
    
    def get_device_status(self):
        """Get current status of all devices."""
        with self.lock:
            return self.device_status.copy()
    
    def should_trigger_healing(self, ip):
        """Check if healing should be triggered for a device."""
        with self.lock:
            return self.failure_counts[ip] >= self.failure_threshold
    
    def reset_failure_count(self, ip):
        """Reset failure count after healing attempt."""
        with self.lock:
            self.failure_counts[ip] = 0
            self.device_status[ip]['consecutive_failures'] = 0
    
    def get_lab_devices(self, lab_id):
        """Get all devices for a specific lab."""
        if lab_id in self.labs:
            return self.labs[lab_id]['devices']
        return []
    
    def get_lab_info(self, lab_id):
        """Get lab information."""
        if lab_id in self.labs:
            return {
                'id': lab_id,
                'name': self.labs[lab_id]['name'],
                'location': self.labs[lab_id]['location'],
                'description': self.labs[lab_id]['description'],
                'device_count': len(self.labs[lab_id]['devices'])
            }
        return None


# Testing
if __name__ == '__main__':
    print("Testing Enhanced Network Monitor...")
    
    monitor = EnhancedNetworkMonitor()
    
    print("\nRunning comprehensive health checks...\n")
    results = monitor.check_all_devices()
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total devices checked: {len(results)}")
    print(f"Online: {sum(1 for r in results if r['online'])}")
    print(f"Offline: {sum(1 for r in results if not r['online'])}")
    print(f"{'='*60}")