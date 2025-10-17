import json
import time
import threading
from datetime import datetime
from monitor_enhanced import EnhancedNetworkMonitor
from healer import DeviceHealer
from dashboard_enterprise import init_dashboard, run_dashboard, socketio, broadcast_device_update
from sqlite_handler import SQLiteHandler
from device_manager import DeviceManager

class EnterpriseMonitoringSystem:
    """
    Enterprise Network Monitoring System - Simplified Admin-Only Version
    
    Features:
    - Multi-lab support
    - Dynamic device registration (no hardcoding!)
    - Multi-protocol health checks
    - Performance metrics collection
    - SQLite time-series database
    - Automatic healing with verification
    - Real-time dashboard with WebSocket
    - Comprehensive analytics and graphs
    """
    
    def __init__(self, config_path='config.json'):
        """Initialize the enterprise system."""
        print("\n" + "="*70)
        print("  🚀 ENTERPRISE NETWORK MONITORING SYSTEM")
        print("  Admin-Only Edition")
        print("="*70 + "\n")
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Initialize components
        print("Initializing components...")
        
        # 1. Device Manager (for dynamic device registration)
        print("  → Device Manager...", end=" ")
        self.device_manager = DeviceManager(config_path)
        print("✓")
        
        # 2. SQLite Database Handler
        print("  → SQLite Handler...", end=" ")
        try:
            self.database = SQLiteHandler(config_path)
            print("✓")
        except Exception as e:
            print(f"✗ ({str(e)})")
            print("\n⚠️  Warning: Database not available. Running without database.")
            self.database = None
        
        # 3. Enhanced Network Monitor
        print("  → Enhanced Monitor...", end=" ")
        self.monitor = EnhancedNetworkMonitor(config_path, db_handler=self.database)
        print("✓")
        
        # 4. Device Healer
        print("  → Device Healer...", end=" ")
        self.healer = DeviceHealer(config_path)
        print("✓")
        
        # 5. Dashboard Integration
        print("  → Dashboard Integration...", end=" ")
        init_dashboard(self.monitor, self.healer, self.database, self.device_manager)
        print("✓")
        
        # Track previous device states for change detection
        self.previous_states = {}
        
        # Control flags
        self.running = False
        self.monitoring_thread = None
        self.dashboard_thread = None
        self.metrics_thread = None
        
        # Get intervals
        self.ping_interval = self.config['monitoring']['ping_interval_seconds']
        self.metrics_interval = self.config['monitoring'].get('performance_metrics_interval', 60)
        
        # System info
        total_labs = len(self.config['labs'])
        total_devices = sum(len(lab['devices']) for lab in self.config['labs'].values())
        
        print("\n" + "="*70)
        print("  SYSTEM CONFIGURATION")
        print("="*70)
        print(f"  Labs: {total_labs}")
        print(f"  Total Devices: {total_devices}")
        print(f"  Ping Interval: {self.ping_interval}s")
        print(f"  Metrics Interval: {self.metrics_interval}s")
        print(f"  Failure Threshold: {self.config['monitoring']['failure_threshold']}")
        print(f"  Healing Enabled: {self.config['healing']['enabled']}")
        print(f"  Max Healing Attempts: {self.config['healing']['max_attempts']}")
        print(f"  Database: {'SQLite (monitoring_data.db)' if self.database else 'Disabled'}")
        print(f"  Dashboard Port: {self.config['dashboard']['port']}")
        print(f"  WebSocket: {'Enabled' if self.config['dashboard'].get('websocket_enabled') else 'Disabled'}")
        print(f"  User Management: Admin Only (Simplified)")
        print("="*70 + "\n")
    
    def monitoring_loop(self):
        """
        Main monitoring loop that checks devices and triggers healing.
        Runs in a separate thread.
        """
        print("🔍 Starting monitoring loop...\n")
        
        while self.running:
            try:
                print(f"\n{'='*70}")
                print(f"  MONITORING CYCLE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*70}\n")
                
                # Reload config in case new devices were added
                with open('config.json', 'r') as f:
                    self.config = json.load(f)
                # Merge devices without resetting status to preserve failure counts
                self.monitor.merge_devices(self.config['labs'])
                
                # Check all devices across all labs
                results = self.monitor.check_all_devices()
                
                # Process results and trigger healing if needed
                for result in results:
                    ip = result['ip']
                    lab_id = result['lab_id']
                    
                    # Detect state changes
                    previous_state = self.previous_states.get(ip, {}).get('online')
                    current_state = result['online']
                    
                    if previous_state != current_state:
                        # State changed - broadcast update via WebSocket
                        if self.config['dashboard'].get('websocket_enabled'):
                            broadcast_device_update(ip, result)
                        
                        # Log state change
                        if current_state:
                            print(f"\n✅ [{lab_id}] {result['label']} ({ip}) came back ONLINE")
                            # Reset healing history when device recovers
                            self.healer.reset_healing_history(ip)
                        else:
                            print(f"\n❌ [{lab_id}] {result['label']} ({ip}) went OFFLINE")
                    
                    # Store current state
                    self.previous_states[ip] = {'online': current_state}
                    
                    # Check if healing should be triggered
                    if not result['online'] and self.monitor.should_trigger_healing(ip):
                        print(f"\n⚠️  [{lab_id}] Device {result['label']} ({ip}) has failed threshold - triggering healing...")
                        
                        # Attempt healing
                        if self.config['healing']['enabled']:
                            healing_result = self.healer.heal_device(ip, lab_id)
                            if healing_result['success']:
                                print(f"✅ [{lab_id}] Healing successful for {result['label']} ({ip})")
                                self.monitor.reset_failure_count(ip)
                            else:
                                print(f"❌ [{lab_id}] Healing failed for {result['label']} ({ip}): {healing_result.get('error', 'Unknown error')}")
                
                # Wait for next monitoring cycle
                time.sleep(self.ping_interval)
                
            except Exception as e:
                print(f"\n❌ Error in monitoring loop: {e}")
                time.sleep(5)  # Wait before retrying
    
    def start_monitoring(self):
        """Start the monitoring system."""
        if self.running:
            print("⚠️  Monitoring is already running!")
            return
        
        print("\n🚀 Starting Enterprise Monitoring System...")
        self.running = True
        
        # Start monitoring thread
        self.monitoring_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        # Start dashboard
        print(f"🌐 Dashboard starting on http://{self.config['dashboard']['host']}:{self.config['dashboard']['port']}")
        print("📊 Login with admin/admin123 to access the system")
        print("🔄 Monitoring is running in the background...")
        print("\n" + "="*70)
        
        try:
            run_dashboard(threaded=False)  # Run in main thread
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down system...")
            self.stop_monitoring()
    
    def stop_monitoring(self):
        """Stop the monitoring system."""
        print("🛑 Stopping monitoring system...")
        self.running = False
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
        
        if self.database:
            self.database.close()
        
        print("✅ System stopped successfully")


def main():
    """Main entry point."""
    try:
        system = EnterpriseMonitoringSystem()
        system.start_monitoring()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())