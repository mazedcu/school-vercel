"""
Attendance Gateway Script for ZKTeco Machines
----------------------------------------------
Usage:
1. Install dependencies: pip install pyzk requests
2. Update the config variables below.
3. Run: python attendance_gateway.py
"""

import time
import requests
from zk import ZK, const

# --- CONFIGURATION ---
MACHINE_IP = '192.168.1.201' # Local IP of the machine
MACHINE_PORT = 4370
SERVER_URL = 'https://www.opdevsystems.xyz/attendance/api/sync/'
API_TOKEN = 'opdev_default_secret' # Must match your server setting
SYNC_INTERVAL = 300 # Seconds (5 minutes)

def sync_logs():
    zk = ZK(MACHINE_IP, port=MACHINE_PORT, timeout=5, password=0, force_udp=False, ommit_ping=False)
    conn = None
    try:
        print(f"Connecting to machine at {MACHINE_IP}...")
        conn = zk.connect()
        print("Connected! Fetching logs...")
        
        # Pull attendance logs
        attendance = conn.get_attendance()
        
        payload_logs = []
        for entry in attendance:
            # entry.user_id is the Biometric ID we mapped in the dashboard
            # entry.timestamp is the time of scan
            payload_logs.append({
                "biometric_id": str(entry.user_id),
                "timestamp": entry.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                "type": "in"
            })
        
        if not payload_logs:
            print("No logs found on machine.")
            return

        print(f"Sending {len(payload_logs)} logs to server...")
        
        response = requests.post(
            SERVER_URL,
            json={
                "token": API_TOKEN,
                "logs": payload_logs
            },
            timeout=10
        )
        
        if response.status_code == 200:
            res_data = response.json()
            print(f"Success! Processed: {res_data.get('processed')}")
            if res_data.get('errors'):
                print(f"Warnings: {res_data.get('errors')}")
            
            # Optional: Clear logs from machine after successful sync
            # conn.clear_attendance() 
        else:
            print(f"Server Error: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        if conn:
            conn.disconnect()
            print("Disconnected.")

if __name__ == "__main__":
    print("OpDevSM Attendance Gateway Started.")
    while True:
        sync_logs()
        print(f"Waiting {SYNC_INTERVAL} seconds for next sync...")
        time.sleep(SYNC_INTERVAL)
