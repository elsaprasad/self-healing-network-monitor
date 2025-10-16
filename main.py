import json
import time
import threading
from datetime import datetime
from monitor import NetworkMonitor
from healer import DeviceHealer
from dashboard import init_dashboard, run_dashboard
from notifications import NotificationManager

class SelfHealingMonitor:
    """
    Main orchestrator for the self-healing network monitoring system.
    Coordinates monitoring, healing, notifications, and dashboard display.
    """
    
    def __init__(self, config_path='config.json'):
        """
        Initialize the self-healing monitoring system.
        
        Args:
            config_path (str): Path to configuration file
        """
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Initialize components
        self.monitor = NetworkMonitor(config_path)
        self.healer = DeviceHealer(config_path)
        self.notifier = NotificationManager(config_path)
        
        # Initialize dashboard with references
        init_dashboard(self.monitor, self.healer)
        
        # Track previous device states for change detection
        self.previous_states = {}
        
        # Control flags
        self.running = False
        self.monitoring_thread = None
        self.dashboard_thread = None
        
        # Get monitoring interval
        self.ping_interval = self.config['monitoring']['ping_interval_seconds']
        
        print("Self-Healing Network Monitor Initialized")
        print(f"Monitoring {len(self.config['devices'])} devices")
        print(f"Ping interval: {self.ping_interval} seconds")
        print(f"Failure threshold: {self.config['monitoring']['failure_threshold']}")
        print(f"Healing enabled: {self.config['healing']['enabled']}")
        print(f"Email notifications: {self.notifier.email_enabled}")
        print(f"WhatsApp notifications: {self.notifier.whatsapp_enabled}\n")
    
    def monitoring_loop(self):
        """
        Main monitoring loop that checks devices and triggers healing.
        Runs in a separate thread.
        """
        print("Starting monitoring loop...\n")
        
        while self.running:
            try:
                print(f"\n{'='*60}")
                print(f"Monitoring Cycle - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*60}")
                
                # Check all devices
                results = self.monitor.check_all_devices()
                
                # Check if any devices need healing
                for result in results:
                    ip = result['ip']
                    
                    # If device is offline and exceeds threshold, trigger healing
                    if not result['online'] and self.monitor.should_trigger_healing(ip):
                        print(f"\n⚠️  Device {result['label']} ({ip}) has failed threshold - triggering healing...")
                        
                        # Attempt healing
                        healing_attempted = self.healer.heal_device(ip)
                        
                        if healing_attempted:
                            # Reset monitor failure count after healing attempt
                            self.monitor.reset_failure_count(ip)
                            
                            # Wait a bit before next check
                            print(f"Waiting {self.config['healing']['wait_between_attempts_seconds']}s before next check...")
                            time.sleep(self.config['healing']['wait_between_attempts_seconds'])
                    
                    # If device comes back online, reset healing history
                    elif result['online']:
                        self.healer.reset_healing_history(ip)
                
                print(f"\n{'='*60}")
                print(f"Next check in {self.ping_interval} seconds...")
                print(f"{'='*60}\n")
                
                # Wait for next interval
                time.sleep(self.ping_interval)
            
            except KeyboardInterrupt:
                print("\nMonitoring interrupted by user")
                self.running = False
                break
            except Exception as e:
                print(f"\nError in monitoring loop: {str(e)}")
                time.sleep(self.ping_interval)
    
    def start_dashboard(self):
        """
        Start the Flask dashboard in a separate thread.
        """
        dashboard_config = self.config['dashboard']
        print(f"\nStarting dashboard on http://{dashboard_config['host']}:{dashboard_config['port']}")
        print("Access the dashboard in your web browser\n")
        
        # Run dashboard with threaded=True to disable debug mode
        run_dashboard(threaded=True)
    
    def start(self):
        """
        Start the entire monitoring system (monitoring + dashboard).
        """
        if self.running:
            print("System is already running!")
            return
        
        self.running = True
        
        # Start monitoring in a separate thread
        self.monitoring_thread = threading.Thread(
            target=self.monitoring_loop,
            daemon=True
        )
        self.monitoring_thread.start()
        
        # Start dashboard in a separate thread
        self.dashboard_thread = threading.Thread(
            target=self.start_dashboard,
            daemon=True
        )
        self.dashboard_thread.start()
        
        print("System started successfully!")
        print("Press Ctrl+C to stop\n")
        
        try:
            # Keep main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nShutting down...")
            self.stop()
    
    def stop(self):
        """
        Stop the monitoring system gracefully.
        """
        self.running = False
        
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        print("System stopped")
    
    def run_single_check(self):
        """
        Run a single monitoring check (useful for testing).
        """
        print("Running single check...\n")
        results = self.monitor.check_all_devices()
        
        print("\nCheck complete!")
        print(f"Results logged to {self.config['logging']['log_directory']}/{self.config['logging']['log_file']}")
        
        return results


def main():
    """
    Main entry point for the application.
    """
    print("\n" + "="*60)
    print("  SELF-HEALING NETWORK MONITORING SYSTEM")
    print("="*60 + "\n")
    
    try:
        # Initialize system
        system = SelfHealingMonitor()
        
        # Start monitoring and dashboard
        system.start()
    
    except FileNotFoundError:
        print("Error: config.json not found!")
        print("Please create a config.json file in the current directory")
    except json.JSONDecodeError:
        print("Error: Invalid JSON in config.json")
        print("Please check your configuration file")
    except Exception as e:
        print(f"Error starting system: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()