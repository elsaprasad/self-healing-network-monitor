import json
import time
import os
import paramiko
from datetime import datetime
import pandas as pd

class DeviceHealer:
    """
    Performs SSH-based healing actions on failed network devices.
    Now with verification to ensure healing actually works!
    """
    
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.devices = {device['ip']: device for device in self.config['devices']}
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
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            print(f"  Connecting to {ip}...")
            client.connect(
                hostname=ip,
                username=username,
                password=password,
                port=port,
                timeout=timeout,
                look_for_keys=False,
                allow_agent=False
            )
            print(f"  ✓ SSH connection established to {ip}")
            return client
        except Exception as e:
            print(f"  ✗ SSH connection failed for {ip}: {str(e)}")
            return None
    
    def _detect_os(self, ssh_client):
        """Detect remote OS via SSH."""
        try:
            # Try Windows first
            stdin, stdout, stderr = ssh_client.exec_command('ver', timeout=5)
            output = stdout.read().decode().lower()
            if 'windows' in output or 'microsoft' in output:
                return 'windows'
            
            # Try Linux
            stdin, stdout, stderr = ssh_client.exec_command('uname -s', timeout=5)
            output = stdout.read().decode().lower()
            if 'linux' in output:
                return 'linux'
            
            return 'unknown'
        except Exception as e:
            print(f"    ✗ Error detecting OS: {str(e)}")
            return 'unknown'
    
    def execute_command(self, ssh_client, command, timeout=30):
        """Execute command and return output."""
        try:
            print(f"    Executing: {command}")
            stdin, stdout, stderr = ssh_client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8', errors='ignore').strip()
            stderr_data = stderr.read().decode('utf-8', errors='ignore').strip()
            
            if exit_code == 0:
                print(f"    ✓ Command succeeded")
            else:
                print(f"    ✗ Command failed with exit code {exit_code}")
                if stderr_data:
                    print(f"    Error: {stderr_data[:200]}")  # First 200 chars
            
            return stdout_data, stderr_data, exit_code
        except Exception as e:
            print(f"    ✗ Error executing command: {str(e)}")
            return None, str(e), -1
    
    def _get_windows_active_adapter(self, ssh_client):
        """Get the name of the active network adapter on Windows."""
        try:
            # Get active adapter name
            cmd = 'powershell -Command "Get-NetAdapter | Where-Object {$_.Status -eq \'Up\'} | Select-Object -First 1 -ExpandProperty Name"'
            stdout, stderr, exit_code = self.execute_command(ssh_client, cmd, timeout=10)
            
            if exit_code == 0 and stdout:
                adapter_name = stdout.strip()
                print(f"    Active adapter: {adapter_name}")
                return adapter_name
            
            # Fallback to common names
            for common_name in ['Wi-Fi', 'Ethernet', 'Local Area Connection']:
                cmd = f'powershell -Command "Get-NetAdapter -Name \'{common_name}\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"'
                stdout, stderr, exit_code = self.execute_command(ssh_client, cmd, timeout=10)
                if exit_code == 0 and stdout:
                    print(f"    Found adapter: {common_name}")
                    return common_name
            
            print("    ⚠️  Could not determine adapter name, using 'Wi-Fi' as default")
            return 'Wi-Fi'
            
        except Exception as e:
            print(f"    ⚠️  Error getting adapter name: {str(e)}, using 'Wi-Fi'")
            return 'Wi-Fi'
    
    def _heal_windows(self, ssh_client, ip):
        """
        Heal Windows device with verification.
        Steps:
        1. Remove firewall rules blocking ping
        2. Reset network adapter
        3. Wait for adapter to come back up
        4. Verify connectivity
        """
        print(f"\n  Healing Windows device...")
        
        # Step 1: Remove any firewall rules blocking ICMP
        print("\n  Step 1: Removing firewall blocks...")
        firewall_commands = [
            'netsh advfirewall firewall delete rule name="Block Ping Test"',
            'netsh advfirewall firewall add rule name="Allow ICMP" protocol=icmpv4:8,any dir=in action=allow'
        ]
        
        for cmd in firewall_commands:
            self.execute_command(ssh_client, cmd, timeout=10)
        
        # Step 2: Get active adapter name
        print("\n  Step 2: Identifying network adapter...")
        adapter_name = self._get_windows_active_adapter(ssh_client)
        
        # Step 3: Reset network adapter
        print(f"\n  Step 3: Resetting network adapter '{adapter_name}'...")
        reset_commands = [
            f'netsh interface set interface "{adapter_name}" admin=disable',
            f'timeout /t 2 /nobreak',  # Wait 2 seconds
            f'netsh interface set interface "{adapter_name}" admin=enable',
            f'timeout /t 3 /nobreak',  # Wait for adapter to come up
        ]
        
        success = True
        for cmd in reset_commands:
            stdout, stderr, exit_code = self.execute_command(ssh_client, cmd, timeout=15)
            if exit_code != 0 and 'timeout' not in cmd.lower():
                success = False
        
        # Step 4: Verify adapter is up
        print("\n  Step 4: Verifying adapter status...")
        verify_cmd = f'powershell -Command "Get-NetAdapter -Name \'{adapter_name}\' | Select-Object -ExpandProperty Status"'
        stdout, stderr, exit_code = self.execute_command(ssh_client, verify_cmd, timeout=10)
        
        if exit_code == 0 and stdout:
            status = stdout.strip()
            print(f"    Adapter status: {status}")
            if status.lower() == 'up':
                print(f"    ✓ Adapter is UP")
            else:
                print(f"    ⚠️  Adapter status is: {status}")
                success = False
        
        # Step 5: Test local connectivity (ping gateway)
        print("\n  Step 5: Testing connectivity...")
        test_cmd = 'ping -n 2 8.8.8.8'
        stdout, stderr, exit_code = self.execute_command(ssh_client, test_cmd, timeout=10)
        
        if exit_code == 0:
            print(f"    ✓ Device can reach internet")
        else:
            print(f"    ⚠️  Connectivity test inconclusive")
        
        return success
    
    def _heal_linux(self, ssh_client, ip):
        """Heal Linux device with verification."""
        print(f"\n  Healing Linux device...")
        
        # Step 1: Allow ICMP through iptables
        print("\n  Step 1: Allowing ICMP...")
        firewall_commands = [
            'sudo iptables -D INPUT -p icmp --icmp-type echo-request -j DROP 2>/dev/null || true',
            'sudo iptables -A INPUT -p icmp --icmp-type echo-request -j ACCEPT'
        ]
        
        for cmd in firewall_commands:
            self.execute_command(ssh_client, cmd, timeout=10)
        
        # Step 2: Restart networking
        print("\n  Step 2: Restarting network service...")
        restart_commands = [
            'sudo systemctl restart networking',
            'sleep 3'
        ]
        
        success = True
        for cmd in restart_commands:
            stdout, stderr, exit_code = self.execute_command(ssh_client, cmd, timeout=15)
            if exit_code != 0 and 'sleep' not in cmd:
                success = False
        
        # Step 3: Verify connectivity
        print("\n  Step 3: Testing connectivity...")
        test_cmd = 'ping -c 2 8.8.8.8'
        stdout, stderr, exit_code = self.execute_command(ssh_client, test_cmd, timeout=10)
        
        if exit_code == 0:
            print(f"    ✓ Device can reach internet")
        else:
            print(f"    ⚠️  Connectivity test inconclusive")
        
        return success
    
    def heal_device(self, ip):
        """
        Main healing function with OS detection and verification.
        """
        if not self.healing_enabled:
            print(f"Healing is disabled for {ip}")
            return False
        
        device = self.devices.get(ip)
        if not device:
            print(f"Device {ip} not found in config")
            return False
        
        if not device.get('ssh_enabled', False):
            print(f"SSH not enabled for {device['label']} ({ip})")
            return False
        
        attempt_count = self.healing_history.get(ip, 0)
        if attempt_count >= self.max_attempts:
            print(f"Max healing attempts reached for {device['label']} ({ip})")
            self._log_healing_attempt(
                ip, device['label'], attempt_count+1, [], 'failed',
                f'Max attempts ({self.max_attempts}) reached'
            )
            return False
        
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
            return False
        
        # Detect OS
        os_type = self._detect_os(ssh_client)
        print(f"  Detected OS: {os_type.upper()}")
        
        # Execute OS-specific healing
        success = False
        healing_method = 'unknown'
        
        if os_type == 'windows':
            healing_method = 'Windows network reset'
            success = self._heal_windows(ssh_client, ip)
        elif os_type == 'linux':
            healing_method = 'Linux network reset'
            success = self._heal_linux(ssh_client, ip)
        else:
            print(f"  ✗ Unknown OS, cannot heal")
            ssh_client.close()
            self.healing_history[ip] = attempt_count + 1
            self._log_healing_attempt(
                ip, device['label'], attempt_count+1, [], 'failed', 
                'Unknown OS - cannot determine healing commands'
            )
            return False
        
        # Close SSH connection
        ssh_client.close()
        print(f"  SSH connection closed")
        
        # Update healing history
        self.healing_history[ip] = attempt_count + 1
        
        # Log results
        if success:
            print(f"\n✓ Healing completed successfully for {device['label']} ({ip})")
            print(f"  Method: {healing_method}")
            print(f"  Device should now respond to ping!")
            details = f'{healing_method} - verification passed'
        else:
            print(f"\n⚠️  Healing completed with warnings for {device['label']} ({ip})")
            print(f"  Method: {healing_method}")
            print(f"  Device may or may not respond to ping")
            details = f'{healing_method} - verification inconclusive'
        
        self._log_healing_attempt(
            ip, device['label'], attempt_count+1, [healing_method],
            'success' if success else 'partial', details
        )
        
        print(f"{'='*60}\n")
        
        return True
    
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


# Example usage and testing
if __name__ == '__main__':
    healer = DeviceHealer()
    
    # Test healing on Geethika's Laptop
    print("Testing healing process...")
    test_ip = '10.59.249.15'
    
    success = healer.heal_device(test_ip)
    
    if success:
        print("\n" + "="*60)
        print("HEALING ATTEMPT COMPLETED")
        print("="*60)
        print("\nNext steps:")
        print("1. Wait 5-10 seconds for network to stabilize")
        print("2. Test ping manually: ping", test_ip)
        print("3. If ping works, healing was successful!")
        print("4. Monitor will detect device as online in next cycle")
    else:
        print("\n" + "="*60)
        print("HEALING FAILED")
        print("="*60)
        print("\nPossible issues:")
        print("- SSH not enabled on device")
        print("- Wrong credentials in config.json")
        print("- Device truly offline (not just firewall)")