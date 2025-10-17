import json
import os
from datetime import datetime

class DeviceManager:
    """
    Manage device registration and configuration.
    Allows admin to add/edit/delete devices and labs dynamically.
    """
    
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self):
        """Load configuration from file."""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return self._create_default_config()
    
    def save_config(self):
        """Save configuration to file."""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)
    
    def _create_default_config(self):
        """Create default configuration structure."""
        return {
            "monitoring": {
                "ping_interval_seconds": 30,
                "ping_timeout_seconds": 2,
                "http_timeout_seconds": 5,
                "failure_threshold": 3,
                "performance_metrics_interval": 60
            },
            "healing": {
                "enabled": True,
                "max_attempts": 3,
                "wait_between_attempts_seconds": 10
            },
            "dashboard": {
                "host": "0.0.0.0",
                "port": 5000,
                "websocket_enabled": True
            },
            "logging": {
                "log_directory": "logs"
            },
            "labs": {}
        }
    
    def get_all_labs(self):
        """Get all labs."""
        return self.config.get('labs', {})
    
    def get_lab(self, lab_id):
        """Get specific lab."""
        return self.config['labs'].get(lab_id)
    
    def add_lab(self, lab_id, name, location, description=""):
        """Add a new lab."""
        if lab_id in self.config['labs']:
            return False, "Lab ID already exists"
        
        self.config['labs'][lab_id] = {
            "name": name,
            "location": location,
            "description": description,
            "devices": []
        }
        self.save_config()
        return True, "Lab added successfully"
    
    def update_lab(self, lab_id, name=None, location=None, description=None):
        """Update lab details."""
        if lab_id not in self.config['labs']:
            return False, "Lab not found"
        
        if name:
            self.config['labs'][lab_id]['name'] = name
        if location:
            self.config['labs'][lab_id]['location'] = location
        if description is not None:
            self.config['labs'][lab_id]['description'] = description
        
        self.save_config()
        return True, "Lab updated successfully"
    
    def delete_lab(self, lab_id):
        """Delete a lab."""
        if lab_id not in self.config['labs']:
            return False, "Lab not found"
        
        del self.config['labs'][lab_id]
        self.save_config()
        return True, "Lab deleted successfully"
    
    def add_device(self, lab_id, ip, label, ssh_enabled=False, ssh_username="",
                   ssh_password="", ssh_port=22, health_checks=None):
        """Add a device to a lab."""
        if lab_id not in self.config['labs']:
            return False, "Lab not found"
        
        # Check if IP already exists in this lab
        for device in self.config['labs'][lab_id]['devices']:
            if device['ip'] == ip:
                return False, "Device with this IP already exists in this lab"
        
        if health_checks is None:
            health_checks = {
                "ping": True,
                "http": {"enabled": False, "url": "", "expected_status": 200},
                "port_checks": [],
                "performance_metrics": ssh_enabled
            }
        
        device = {
            "ip": ip,
            "label": label,
            "ssh_enabled": ssh_enabled,
            "ssh_username": ssh_username,
            "ssh_password": ssh_password,
            "ssh_port": ssh_port,
            "health_checks": health_checks,
            "added_at": datetime.now().isoformat()
        }
        
        self.config['labs'][lab_id]['devices'].append(device)
        self.save_config()
        return True, "Device added successfully"
    
    def update_device(self, lab_id, ip, **kwargs):
        """Update device details."""
        if lab_id not in self.config['labs']:
            return False, "Lab not found"
        
        for device in self.config['labs'][lab_id]['devices']:
            if device['ip'] == ip:
                # Update fields
                for key, value in kwargs.items():
                    if key in device:
                        device[key] = value
                
                self.save_config()
                return True, "Device updated successfully"
        
        return False, "Device not found"
    
    def delete_device(self, lab_id, ip):
        """Delete a device from a lab."""
        if lab_id not in self.config['labs']:
            return False, "Lab not found"
        
        devices = self.config['labs'][lab_id]['devices']
        for i, device in enumerate(devices):
            if device['ip'] == ip:
                devices.pop(i)
                self.save_config()
                return True, "Device deleted successfully"
        
        return False, "Device not found"
    
    def get_device(self, lab_id, ip):
        """Get specific device details."""
        if lab_id not in self.config['labs']:
            return None
        
        for device in self.config['labs'][lab_id]['devices']:
            if device['ip'] == ip:
                return device
        
        return None
    
    def get_all_devices(self):
        """Get all devices across all labs."""
        all_devices = []
        for lab_id, lab_data in self.config['labs'].items():
            for device in lab_data['devices']:
                device_copy = device.copy()
                device_copy['lab_id'] = lab_id
                device_copy['lab_name'] = lab_data['name']
                all_devices.append(device_copy)
        return all_devices
    
    def get_device_count(self):
        """Get total device count."""
        total = 0
        for lab_data in self.config['labs'].values():
            total += len(lab_data['devices'])
        return total
    
    def get_lab_device_count(self, lab_id):
        """Get device count for a specific lab."""
        if lab_id in self.config['labs']:
            return len(self.config['labs'][lab_id]['devices'])
        return 0


# Testing
if __name__ == '__main__':
    dm = DeviceManager()
    
    # Add a test lab
    success, msg = dm.add_lab('lab1', 'Computer Lab 1', 'Building A, Floor 2')
    print(f"Add lab: {msg}")
    
    # Add a test device
    success, msg = dm.add_device(
        'lab1',
        ip='192.168.1.100',
        label='PC-01',
        ssh_enabled=True,
        ssh_username='admin',
        ssh_password='password'
    )
    print(f"Add device: {msg}")
    
    # Get all labs
    labs = dm.get_all_labs()
    print(f"\nTotal labs: {len(labs)}")
    print(f"Total devices: {dm.get_device_count()}")