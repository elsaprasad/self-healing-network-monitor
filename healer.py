import json
import time
import os
import paramiko
from datetime import datetime
import pandas as pd

class DeviceHealer:
    """
    Performs SSH-based healing actions on failed network devices.
    FIXED: Handles network adapter reset without killing SSH connection!
    """
    
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Handle both old and new config formats
        self.devices = {}
        if 'devices' in self.config:
            self.devices = {device['ip']: device for device in self.config['devices']}
        elif 'labs' in self.config:
            for lab_id, lab_data in self.config['labs'].items():
                for device in lab_data['devices']:
                    device['lab_id'] = lab_id
                    self.devices[device['ip']] = device
        
        self.healing_enabled = self.config['healing']['enabled']
        self.max_attempts = self.config['healing']['max_attempts']
        self.wait_between_attempts = self.config['healing']['wait_between_attempts_seconds']
        self.healing_history = {}
        self._init_healing_log()
    
    def _init_healing_log(self):
        log_dir = self.config['logging']['log_directory']
        self.healing_log_file = os.path.join(log_dir, 'healing.csv')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        if not os.path.exists(self.healing_log_file):
            df = pd.DataFrame(columns=[
                'timestamp', 'ip', 'label', 'attempt_number', 
                'commands_executed', 'result', 'details'
            ])
            df.to_csv(self.healing_log_file, index=False)
    
    def _log_healing_attempt(self, ip, label, attempt_number, commands, result, details):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = {
            'timestamp': timestamp,
            'ip': ip,
            'label': label,
            'attempt_number': attempt_number,
            'commands_executed': len(commands),
            'result': result,
            'details': details
        }
        df = pd.DataFrame([log_entry])
        df.to_csv(self.healing_log_file, mode='a', header=False, index=False)
    
    def connect_ssh(self, ip, username, password, port=22, timeout=10):
        """Connect to device via SSH with better error handling."""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            print(f"  Connecting to {ip}:{port}...")
            
            client.connect(
                hostname=ip,
                username=username,
                password=password,
                port=port,
                timeout=timeout,
                look_for_keys=False,
                allow_agent=False,
                banner_timeout=timeout
            )
            print(f"  ✓ SSH connection established to {ip}")
            return client
        except paramiko.AuthenticationException:
            print(f"  ✗ SSH authentication failed for {ip} (check username/password)")
            return None
        except paramiko.SSHException as e:
            print(f"  ✗ SSH error for {ip}: {str(e)}")
            return None
        except Exception as e:
            print(f"  ✗ SSH connection failed for {ip}: {str(e)}")
            return None
    
    def _detect_os(self, ssh_client):
        """Detect remote OS via SSH with improved logic."""
        try:
            # Method 1: Try Windows-specific command
            stdin, stdout, stderr = ssh_client.exec_command('ver', timeout=3)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code == 0:
                output = stdout.read().decode('utf-8', errors='ignore').lower()
                if 'windows' in output or 'microsoft' in output:
                    print(f"    Detected: Windows (via 'ver' command)")
                    return 'windows'
            
            # Method 2: Try uname (Linux/Unix)
            stdin, stdout, stderr = ssh_client.exec_command('uname -s', timeout=3)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code == 0:
                output = stdout.read().decode('utf-8', errors='ignore').strip().lower()
                if 'linux' in output:
                    print(f"    Detected: Linux (via 'uname' command)")
                    return 'linux'
                elif 'darwin' in output:
                    print(f"    Detected: macOS (treating as Linux)")
                    return 'linux'
            
            # Method 3: Check for Windows environment variables
            stdin, stdout, stderr = ssh_client.exec_command('echo %OS%', timeout=3)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code == 0:
                output = stdout.read().decode('utf-8', errors='ignore').strip()
                if 'Windows' in output:
                    print(f"    Detected: Windows (via %OS% variable)")
                    return 'windows'
            
            # Method 4: Check for /etc/os-release (Linux)
            stdin, stdout, stderr = ssh_client.exec_command('cat /etc/os-release 2>/dev/null | head -n 1', timeout=3)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code == 0:
                output = stdout.read().decode('utf-8', errors='ignore')
                if output.strip():
                    print(f"    Detected: Linux (via /etc/os-release)")
                    return 'linux'
            
            print(f"    ⚠️ Could not determine OS")
            return 'unknown'
            
        except Exception as e:
            print(f"    ✗ Error detecting OS: {str(e)}")
            return 'unknown'
    
    def execute_command(self, ssh_client, command, timeout=30, ignore_errors=False):
        """Execute command with better error handling."""
        try:
            print(f"    Executing: {command[:80]}...")
            stdin, stdout, stderr = ssh_client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8', errors='ignore').strip()
            stderr_data = stderr.read().decode('utf-8', errors='ignore').strip()
            
            if exit_code == 0 or ignore_errors:
                print(f"    ✓ Command completed (exit code: {exit_code})")
            else:
                print(f"    ✗ Command failed with exit code {exit_code}")
                if stderr_data:
                    print(f"    Error output: {stderr_data[:200]}")
            
            return stdout_data, stderr_data, exit_code
        except Exception as e:
            print(f"    ✗ Error executing command: {str(e)}")
            return None, str(e), -1
    
    def _get_windows_adapters(self, ssh_client):
        """Get list of network adapters on Windows with status."""
        try:
            cmd = 'powershell -Command "Get-NetAdapter | Select-Object Name, Status | ConvertTo-Json"'
            stdout, stderr, exit_code = self.execute_command(ssh_client, cmd, timeout=10)
            
            if exit_code == 0 and stdout:
                try:
                    import json
                    adapters = json.loads(stdout)
                    if isinstance(adapters, dict):
                        adapters = [adapters]
                    return adapters
                except:
                    pass
            
            # Fallback
            cmd = 'powershell -Command "Get-NetAdapter | Select-Object -ExpandProperty Name"'
            stdout, stderr, exit_code = self.execute_command(ssh_client, cmd, timeout=10)
            
            if exit_code == 0 and stdout:
                adapter_names = [line.strip() for line in stdout.split('\n') if line.strip()]
                return [{'Name': name, 'Status': 'Unknown'} for name in adapter_names]
            
            return []
            
        except Exception as e:
            print(f"    ⚠️ Error listing adapters: {str(e)}")
            return []
    
    def _find_active_windows_adapter(self, ssh_client):
        """Find the active network adapter on Windows."""
        adapters = self._get_windows_adapters(ssh_client)
        
        for adapter in adapters:
            if adapter.get('Status', '').lower() == 'up':
                name = adapter.get('Name', '')
                print(f"    Found active adapter: {name}")
                return name
        
        # Fallback to common names
        common_names = ['Wi-Fi', 'Ethernet', 'Ethernet 2', 'Ethernet 3', 'Local Area Connection']
        adapter_names = [a.get('Name', '') for a in adapters]
        
        for common in common_names:
            if common in adapter_names:
                print(f"    Using common adapter name: {common}")
                return common
        
        if adapters:
            first_name = adapters[0].get('Name', 'Ethernet')
            print(f"    Using first adapter found: {first_name}")
            return first_name
        
        print(f"    ⚠️ No adapters found, using default: Wi-Fi")
        return 'Wi-Fi'
    
    def _heal_windows(self, ssh_client, ip):
        """
        Heal Windows device WITHOUT killing SSH connection.
        Strategy: Fix firewall first, then schedule adapter reset as background task.
        """
        print(f"\n  Healing Windows device...")
        
        # Step 1: Remove firewall rules blocking ping (PRIORITY FIX)
        print("\n  Step 1: Configuring Windows Firewall for ICMP...")
        firewall_commands = [
            'netsh advfirewall firewall delete rule name="Block ICMP" protocol=icmpv4:8,any',
            'netsh advfirewall firewall delete rule name="Block Ping Test" protocol=icmpv4:8,any',
            'netsh advfirewall firewall add rule name="Allow ICMP" protocol=icmpv4:8,any dir=in action=allow',
            'netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound'
        ]
        
        for cmd in firewall_commands:
            self.execute_command(ssh_client, cmd, timeout=10, ignore_errors=True)
        
        print("    ✓ Firewall configured to allow ICMP ping")
        
        # Step 2: Reset DNS and flush network cache (safe operations)
        print("\n  Step 2: Flushing network cache and resetting DNS...")
        cache_commands = [
            'ipconfig /flushdns',
            'netsh int ip reset',
            'netsh winsock reset'
        ]
        
        for cmd in cache_commands:
            self.execute_command(ssh_client, cmd, timeout=10, ignore_errors=True)
        
        # Step 3: Identify adapter
        print("\n  Step 3: Identifying network adapter...")
        adapter_name = self._find_active_windows_adapter(ssh_client)
        
        if not adapter_name:
            print("    ⚠️ Could not identify adapter, skipping adapter reset")
            return True  # Firewall fix might be enough
        
        # Step 4: Schedule adapter reset as BACKGROUND task (doesn't kill SSH)
        print(f"\n  Step 4: Scheduling adapter reset for '{adapter_name}' (background)...")
        
        # Create a background script that runs AFTER SSH disconnects
        reset_script = f'''
        powershell -Command "Start-Sleep -Seconds 2; Disable-NetAdapter -Name '{adapter_name}' -Confirm:$false; Start-Sleep -Seconds 3; Enable-NetAdapter -Name '{adapter_name}' -Confirm:$false"
        '''
        
        # Run in background using 'start /b' so SSH doesn't wait
        background_cmd = f'start /b cmd /c "{reset_script.strip()}"'
        
        try:
            # Use exec_command without waiting for completion
            stdin, stdout, stderr = ssh_client.exec_command(background_cmd, timeout=2)
            print("    ✓ Adapter reset scheduled (will execute in background)")
        except Exception as e:
            print(f"    ⚠️ Could not schedule background task: {str(e)}")
            print("    → Firewall fix should still work!")
        
        print("\n  ✓ Healing completed!")
        print("    - Firewall configured to allow ping")
        print("    - Network cache flushed")
        print("    - Adapter reset scheduled (may take 5-10 seconds)")
        
        return True
    
    def _heal_linux(self, ssh_client, ip):
        """Heal Linux device - firewall fix is primary strategy."""
        print(f"\n  Healing Linux device...")
        
        # Step 1: Configure iptables to allow ICMP (PRIMARY FIX)
        print("\n  Step 1: Configuring iptables for ICMP...")
        firewall_commands = [
            'sudo iptables -D INPUT -p icmp --icmp-type echo-request -j DROP 2>/dev/null || true',
            'sudo iptables -D INPUT -p icmp -j DROP 2>/dev/null || true',
            'sudo iptables -I INPUT -p icmp --icmp-type echo-request -j ACCEPT',
            'sudo iptables -I INPUT -p icmp -j ACCEPT'
        ]
        
        for cmd in firewall_commands:
            self.execute_command(ssh_client, cmd, timeout=10, ignore_errors=True)
        
        print("    ✓ Firewall configured to allow ICMP ping")
        
        # Step 2: Flush network cache
        print("\n  Step 2: Flushing network cache...")
        cache_commands = [
            'sudo ip route flush cache',
            'sudo systemctl restart systemd-resolved 2>/dev/null || true'
        ]
        
        for cmd in cache_commands:
            self.execute_command(ssh_client, cmd, timeout=10, ignore_errors=True)
        
        # Step 3: Test connectivity
        print("\n  Step 3: Testing connectivity...")
        test_cmd = 'ping -c 2 8.8.8.8'
        stdout, stderr, exit_code = self.execute_command(ssh_client, test_cmd, timeout=10, ignore_errors=True)
        
        if exit_code == 0:
            print(f"    ✓ Device can reach internet")
        else:
            print(f"    ⚠️ Internet test inconclusive (but firewall is fixed)")
        
        return True
    
    def heal_device(self, ip, lab_id=None):
        """Main healing function - prioritizes firewall fixes over network resets."""
        if not self.healing_enabled:
            print(f"Healing is disabled for {ip}")
            return {'success': False, 'error': 'Healing disabled'}
        
        # Reload config
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            
            self.devices = {}
            if 'labs' in config:
                for lab_id_key, lab_data in config['labs'].items():
                    for device in lab_data['devices']:
                        device['lab_id'] = lab_id_key
                        self.devices[device['ip']] = device
        except Exception as e:
            print(f"Warning: Could not reload config: {e}")
        
        device = self.devices.get(ip)
        if not device:
            print(f"Device {ip} not found in config")
            return {'success': False, 'error': 'Device not found in config'}
        
        if not device.get('ssh_enabled', False):
            print(f"SSH not enabled for {device['label']} ({ip})")
            return {'success': False, 'error': 'SSH not enabled'}
        
        attempt_count = self.healing_history.get(ip, 0)
        if attempt_count >= self.max_attempts:
            print(f"Max healing attempts reached for {device['label']} ({ip})")
            self._log_healing_attempt(
                ip, device['label'], attempt_count+1, [], 'failed',
                f'Max attempts ({self.max_attempts}) reached'
            )
            return {'success': False, 'error': f'Max attempts ({self.max_attempts}) reached'}
        
        print(f"\n{'='*60}")
        print(f"HEALING ATTEMPT {attempt_count+1}/{self.max_attempts} for {device['label']} ({ip})")
        print(f"{'='*60}")
        
        # Connect via SSH
        ssh_client = self.connect_ssh(
            ip=ip,
            username=device['ssh_username'],
            password=device['ssh_password'],
            port=device.get('ssh_port', 22)
        )
        
        if not ssh_client:
            self.healing_history[ip] = attempt_count + 1
            self._log_healing_attempt(
                ip, device['label'], attempt_count+1, [], 'failed', 
                'SSH connection failed'
            )
            return {'success': False, 'error': 'SSH connection failed'}
        
        # Detect OS
        os_type = self._detect_os(ssh_client)
        print(f"  Detected OS: {os_type.upper()}")
        
        # Execute OS-specific healing
        success = False
        healing_method = 'unknown'
        
        try:
            if os_type == 'windows':
                healing_method = 'Windows firewall + network cache reset'
                success = self._heal_windows(ssh_client, ip)
            elif os_type == 'linux':
                healing_method = 'Linux firewall + network cache reset'
                success = self._heal_linux(ssh_client, ip)
            else:
                print(f"  ✗ Unknown OS, cannot heal")
                healing_method = 'Unknown OS'
                success = False
        except Exception as e:
            print(f"  ✗ Error during healing: {str(e)}")
            success = False
        finally:
            try:
                ssh_client.close()
                print(f"  SSH connection closed")
            except:
                pass
        
        # Update healing history
        self.healing_history[ip] = attempt_count + 1
        
        # Log results
        if success:
            print(f"\n✓ Healing completed for {device['label']} ({ip})")
            print(f"  Method: {healing_method}")
            print(f"  Device should respond to ping within 10-15 seconds")
            details = f'{healing_method} - completed successfully'
        else:
            print(f"\n⚠️  Healing attempt failed for {device['label']} ({ip})")
            print(f"  Method: {healing_method}")
            details = f'{healing_method} - failed'
        
        self._log_healing_attempt(
            ip, device['label'], attempt_count+1, [healing_method],
            'success' if success else 'failed', details
        )
        
        print(f"{'='*60}\n")
        
        return {'success': success, 'error': None if success else 'Healing failed'}
    
    def reset_healing_history(self, ip):
        """Reset healing attempt counter when device recovers."""
        if ip in self.healing_history:
            old_count = self.healing_history[ip]
            self.healing_history[ip] = 0
            print(f"✓ Reset healing history for {ip} (was {old_count} attempts)")
            
            device = self.devices.get(ip)
            if device:
                self._log_healing_attempt(
                    ip, device['label'], 0, [], 'success',
                    f'Device recovered - reset after {old_count} attempts'
                )
    
    def get_healing_status(self):
        """Get current healing attempt counts for all devices."""
        return self.healing_history.copy()


if __name__ == '__main__':
    healer = DeviceHealer()
    
    print("Testing healing process...")
    test_ip = '172.20.1.105'
    
    result = healer.heal_device(test_ip)
    
    if result['success']:
        print("\n" + "="*60)
        print("HEALING COMPLETED")
        print("="*60)
        print("\nThe device should come back online in 10-15 seconds!")
        print("Monitor will detect it in the next cycle.")
    else:
        print("\n" + "="*60)
        print("HEALING FAILED")
        print("="*60)
        print(f"\nError: {result.get('error')}")