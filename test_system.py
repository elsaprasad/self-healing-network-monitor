#!/usr/bin/env python3
"""
Test script for Self-Healing Network Monitoring System.
Tests individual components and integration.
"""

import json
import os
import time
from monitor import NetworkMonitor
from healer import DeviceHealer

def print_header(text):
    """Print formatted section header."""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def test_config_loading():
    """Test 1: Verify config.json loads correctly."""
    print_header("TEST 1: Configuration Loading")
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        print("✓ config.json loaded successfully")
        print(f"  Devices configured: {len(config['devices'])}")
        print(f"  Ping interval: {config['monitoring']['ping_interval_seconds']}s")
        print(f"  Healing enabled: {config['healing']['enabled']}")
        
        # Display devices
        print("\nConfigured devices:")
        for device in config['devices']:
            print(f"  - {device['label']} ({device['ip']}) - SSH: {device.get('ssh_enabled', False)}")
        
        return True
    
    except FileNotFoundError:
        print("✗ config.json not found!")
        return False
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON: {str(e)}")
        return False
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False

def test_monitor():
    """Test 2: Test network monitoring component."""
    print_header("TEST 2: Network Monitoring")
    
    try:
        monitor = NetworkMonitor()
        print("✓ Monitor initialized successfully")
        
        print("\nRunning single ping check on all devices...")
        results = monitor.check_all_devices()
        
        print(f"\nResults: {len(results)} devices checked")
        
        # Display results
        online_count = sum(1 for r in results if r['online'])
        offline_count = len(results) - online_count
        
        print(f"  Online: {online_count}")
        print(f"  Offline: {offline_count}")
        
        # Check if log file was created
        if os.path.exists(monitor.log_file):
            print(f"\n✓ Log file created: {monitor.log_file}")
        else:
            print(f"\n✗ Log file not created")
        
        return True
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_healer(test_ip=None):
    """Test 3: Test healing component (without actually healing)."""
    print_header("TEST 3: Healing System")
    
    try:
        healer = DeviceHealer()
        print("✓ Healer initialized successfully")
        
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Find a device with SSH enabled
        ssh_devices = [d for d in config['devices'] if d.get('ssh_enabled', False)]
        
        if not ssh_devices:
            print("\n⚠️  No SSH-enabled devices in config")
            print("   Skipping SSH connection test")
            return True
        
        if test_ip:
            test_device = next((d for d in ssh_devices if d['ip'] == test_ip), None)
            if not test_device:
                print(f"✗ Device {test_ip} not found or SSH not enabled")
                return False
        else:
            test_device = ssh_devices[0]
        
        print(f"\nTesting SSH connection to {test_device['label']} ({test_device['ip']})")
        print("⚠️  Note: This will NOT execute healing commands, just test connection\n")
        
        # Test SSH connection only
        ssh_client = healer.connect_ssh(
            ip=test_device['ip'],
            username=test_device['ssh_username'],
            password=test_device['ssh_password'],
            port=test_device.get('ssh_port', 22),
            timeout=5
        )
        
        if ssh_client:
            print("✓ SSH connection successful")
            
            # Test a safe command
            print("\nTesting command execution with 'whoami':")
            stdout, stderr, exit_code = healer.execute_command(ssh_client, 'whoami')
            
            if exit_code == 0:
                print(f"✓ Command executed successfully")
                print(f"  Output: {stdout}")
            else:
                print(f"✗ Command failed")
            
            ssh_client.close()
            return True
        else:
            print("✗ SSH connection failed")
            print("  Check credentials in config.json")
            return False
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_integration():
    """Test 4: Test integration between components."""
    print_header("TEST 4: Integration Test")
    
    try:
        monitor = NetworkMonitor()
        healer = DeviceHealer()
        
        print("✓ Both components initialized")
        
        print("\nRunning monitoring check...")
        results = monitor.check_all_devices()
        
        print("\nChecking for devices that need healing...")
        devices_needing_healing = []
        
        for result in results:
            if not result['online']:
                # Simulate multiple failures
                monitor.failure_counts[result['ip']] = monitor.failure_threshold
                
                if monitor.should_trigger_healing(result['ip']):
                    devices_needing_healing.append(result)
        
        if devices_needing_healing:
            print(f"  {len(devices_needing_healing)} device(s) would trigger healing")
            for device in devices_needing_healing:
                print(f"    - {device['label']} ({device['ip']})")
        else:
            print("  No devices need healing (all online)")
        
        print("\n✓ Integration test completed")
        return True
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_dashboard():
    """Test 5: Verify dashboard can be imported and initialized."""
    print_header("TEST 5: Dashboard Component")
    
    try:
        from dashboard import init_dashboard, calculate_uptime_stats
        
        print("✓ Dashboard module imported successfully")
        
        # Initialize monitor and healer
        monitor = NetworkMonitor()
        healer = DeviceHealer()
        
        # Initialize dashboard
        init_dashboard(monitor, healer)
        print("✓ Dashboard initialized with monitor and healer")
        
        # Test stats calculation
        stats = calculate_uptime_stats()
        print(f"\n  Uptime stats calculated: {len(stats)} devices")
        
        print("\n✓ Dashboard ready to run")
        print("  Start with: python dashboard.py")
        print("  Then visit: http://localhost:5000")
        
        return True
    
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def run_all_tests():
    """Run all tests sequentially."""
    print("\n" + "="*60)
    print("  SELF-HEALING NETWORK MONITOR - TEST SUITE")
    print("="*60)
    
    tests = [
        ("Configuration Loading", test_config_loading),
        ("Network Monitoring", test_monitor),
        ("Healing System", lambda: test_healer()),
        ("Integration", test_integration),
        ("Dashboard", test_dashboard)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
            time.sleep(1)  # Brief pause between tests
        except KeyboardInterrupt:
            print("\n\nTests interrupted by user")
            break
        except Exception as e:
            print(f"\nUnexpected error in {test_name}: {str(e)}")
            results[test_name] = False
    
    # Print summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! System is ready to use.")
        print("\nTo start the system:")
        print("  python main.py")
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        # Run specific test
        test_name = sys.argv[1].lower()
        
        if test_name == 'config':
            test_config_loading()
        elif test_name == 'monitor':
            test_monitor()
        elif test_name == 'healer':
            test_ip = sys.argv[2] if len(sys.argv) > 2 else None
            test_healer(test_ip)
        elif test_name == 'integration':
            test_integration()
        elif test_name == 'dashboard':
            test_dashboard()
        else:
            print(f"Unknown test: {test_name}")
            print("\nAvailable tests:")
            print("  python test_system.py config")
            print("  python test_system.py monitor")
            print("  python test_system.py healer [ip]")
            print("  python test_system.py integration")
            print("  python test_system.py dashboard")
    else:
        # Run all tests
        run_all_tests()