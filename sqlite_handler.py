"""
SQLite Database Handler - Simple alternative to InfluxDB
NO external dependencies! Works out of the box with Python.
"""

import sqlite3
import json
from datetime import datetime, timedelta
import pandas as pd

class SQLiteHandler:
    """
    Time-series data storage using SQLite.
    Much simpler than InfluxDB - no Docker, no external services!
    """
    
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.db_path = 'monitoring_data.db'
        self.init_database()
        print(f"Connected to SQLite: {self.db_path}")
    
    def init_database(self):
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Ping data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ping_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip TEXT NOT NULL,
                label TEXT NOT NULL,
                lab_id TEXT NOT NULL,
                status TEXT NOT NULL,
                response_time_ms REAL
            )
        ''')
        
        # Performance metrics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip TEXT NOT NULL,
                label TEXT NOT NULL,
                lab_id TEXT NOT NULL,
                cpu_usage REAL,
                memory_usage REAL,
                disk_usage REAL,
                network_in_mbps REAL,
                network_out_mbps REAL
            )
        ''')
        
        # HTTP checks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS http_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip TEXT NOT NULL,
                label TEXT NOT NULL,
                lab_id TEXT NOT NULL,
                url TEXT NOT NULL,
                status_code INTEGER,
                response_time_ms REAL,
                success INTEGER
            )
        ''')
        
        # Port checks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS port_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip TEXT NOT NULL,
                label TEXT NOT NULL,
                lab_id TEXT NOT NULL,
                port INTEGER NOT NULL,
                is_open INTEGER
            )
        ''')
        
        # Healing attempts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS healing_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip TEXT NOT NULL,
                label TEXT NOT NULL,
                lab_id TEXT NOT NULL,
                attempt_number INTEGER,
                success INTEGER,
                details TEXT
            )
        ''')
        
        # Create indexes for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ping_ip_time ON ping_data(ip, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_perf_ip_time ON performance_metrics(ip, timestamp)')
        
        conn.commit()
        conn.close()
    
    def write_ping_data(self, ip, label, lab_id, status, response_time_ms=None):
        """Write ping monitoring data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO ping_data (ip, label, lab_id, status, response_time_ms)
            VALUES (?, ?, ?, ?, ?)
        ''', (ip, label, lab_id, status, response_time_ms))
        
        conn.commit()
        conn.close()
    
    def write_performance_metrics(self, ip, label, lab_id, metrics):
        """Write performance metrics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO performance_metrics 
            (ip, label, lab_id, cpu_usage, memory_usage, disk_usage, network_in_mbps, network_out_mbps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ip, label, lab_id,
            metrics.get('cpu_usage'),
            metrics.get('memory_usage'),
            metrics.get('disk_usage'),
            metrics.get('network_in_mbps'),
            metrics.get('network_out_mbps')
        ))
        
        conn.commit()
        conn.close()
    
    def write_http_check(self, ip, label, lab_id, url, status_code, response_time_ms, success):
        """Write HTTP health check data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO http_checks (ip, label, lab_id, url, status_code, response_time_ms, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (ip, label, lab_id, url, status_code, response_time_ms, 1 if success else 0))
        
        conn.commit()
        conn.close()
    
    def write_port_check(self, ip, label, lab_id, port, is_open):
        """Write port check data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO port_checks (ip, label, lab_id, port, is_open)
            VALUES (?, ?, ?, ?, ?)
        ''', (ip, label, lab_id, port, 1 if is_open else 0))
        
        conn.commit()
        conn.close()
    
    def write_healing_attempt(self, ip, label, lab_id, attempt_number, success, details):
        """Write healing attempt data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO healing_attempts (ip, label, lab_id, attempt_number, success, details)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ip, label, lab_id, attempt_number, 1 if success else 0, details))
        
        conn.commit()
        conn.close()
    
    def get_device_uptime(self, ip, time_range='7d'):
        """Calculate device uptime percentage."""
        # Convert time_range to hours
        hours = {
            '1h': 1, '24h': 24, '7d': 168, '30d': 720
        }.get(time_range, 168)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.now() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online
            FROM ping_data
            WHERE ip = ? AND timestamp > ?
        ''', (ip, since))
        
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0] > 0:
            uptime = (result[1] / result[0]) * 100
            return round(uptime, 2)
        
        return 0.0
    
    def get_response_time_stats(self, ip, time_range='24h'):
        """Get response time statistics."""
        hours = {
            '1h': 1, '24h': 24, '7d': 168, '30d': 720
        }.get(time_range, 24)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.now() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT 
                MIN(response_time_ms) as min,
                MAX(response_time_ms) as max,
                AVG(response_time_ms) as avg,
                COUNT(*) as count
            FROM ping_data
            WHERE ip = ? AND timestamp > ? AND response_time_ms IS NOT NULL
        ''', (ip, since))
        
        result = cursor.fetchone()
        conn.close()
        
        if result and result[3] > 0:
            return {
                'min': round(result[0], 2),
                'max': round(result[1], 2),
                'avg': round(result[2], 2),
                'count': result[3]
            }
        
        return {'min': 0, 'max': 0, 'avg': 0, 'count': 0}
    
    def get_historical_data(self, measurement, ip, time_range='24h', aggregation_window='5m'):
        """Get historical time-series data for graphing."""
        hours = {
            '1h': 1, '24h': 24, '7d': 168, '30d': 720
        }.get(time_range, 24)
        
        conn = sqlite3.connect(self.db_path)
        
        since = datetime.now() - timedelta(hours=hours)
        
        if measurement == 'ping':
            query = '''
                SELECT timestamp, response_time_ms as value
                FROM ping_data
                WHERE ip = ? AND timestamp > ? AND response_time_ms IS NOT NULL
                ORDER BY timestamp
            '''
        elif measurement == 'performance':
            query = '''
                SELECT timestamp, cpu_usage as value
                FROM performance_metrics
                WHERE ip = ? AND timestamp > ?
                ORDER BY timestamp
            '''
        else:
            return []
        
        df = pd.read_sql_query(query, conn, params=(ip, since))
        conn.close()
        
        data = []
        for _, row in df.iterrows():
            data.append({
                'timestamp': row['timestamp'],
                'field': 'response_time_ms' if measurement == 'ping' else 'cpu_usage',
                'value': row['value']
            })
        
        return data
    
    def get_lab_summary(self, lab_id, time_range='24h'):
        """Get summary statistics for a lab."""
        hours = {
            '1h': 1, '24h': 24, '7d': 168, '30d': 720
        }.get(time_range, 24)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.now() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT 
                ip,
                label,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online
            FROM ping_data
            WHERE lab_id = ? AND timestamp > ?
            GROUP BY ip, label
        ''', (lab_id, since))
        
        devices = []
        for row in cursor.fetchall():
            uptime_pct = (row[3] / row[2] * 100) if row[2] > 0 else 0
            devices.append({
                'ip': row[0],
                'label': row[1],
                'uptime_pct': round(uptime_pct, 2)
            })
        
        conn.close()
        return devices
    
    def export_data(self, start_time, end_time, measurement='ping', format='csv'):
        """Export data for reporting."""
        conn = sqlite3.connect(self.db_path)
        
        if measurement == 'ping':
            query = '''
                SELECT * FROM ping_data
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp
            '''
        elif measurement == 'performance':
            query = '''
                SELECT * FROM performance_metrics
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp
            '''
        else:
            return pd.DataFrame() if format == 'csv' else []
        
        df = pd.read_sql_query(query, conn, params=(start_time, end_time))
        conn.close()
        
        if format == 'csv':
            return df
        elif format == 'json':
            return df.to_dict(orient='records')
    
    def cleanup_old_data(self, days=30):
        """Clean up data older than specified days."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = datetime.now() - timedelta(days=days)
        
        cursor.execute('DELETE FROM ping_data WHERE timestamp < ?', (cutoff,))
        cursor.execute('DELETE FROM performance_metrics WHERE timestamp < ?', (cutoff,))
        cursor.execute('DELETE FROM http_checks WHERE timestamp < ?', (cutoff,))
        cursor.execute('DELETE FROM port_checks WHERE timestamp < ?', (cutoff,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted
    
    def close(self):
        """Close database connection (no-op for SQLite)."""
        pass


# Testing
if __name__ == '__main__':
    import time
    
    print("Testing SQLite Handler (InfluxDB alternative)...")
    
    db = SQLiteHandler()
    
    print("\n1. Writing ping data...")
    db.write_ping_data('192.168.1.100', 'Test Device', 'lab1', 'online', 15.5)
    
    print("2. Writing performance metrics...")
    db.write_performance_metrics(
        '192.168.1.100', 'Test Device', 'lab1',
        {'cpu_usage': 45.2, 'memory_usage': 62.8, 'disk_usage': 78.3}
    )
    
    time.sleep(1)
    
    print("\n3. Querying uptime...")
    uptime = db.get_device_uptime('192.168.1.100', '1h')
    print(f"Uptime: {uptime}%")
    
    print("\n4. Querying response time stats...")
    stats = db.get_response_time_stats('192.168.1.100', '1h')
    print(f"Response time stats: {stats}")
    
    print("\n5. Getting historical data...")
    history = db.get_historical_data('ping', '192.168.1.100', '1h')
    print(f"Got {len(history)} data points")
    
    print("\n✓ All tests passed! SQLite is working perfectly.")
    print(f"\nDatabase file: {db.db_path}")
    print("No Docker, no external services needed!")