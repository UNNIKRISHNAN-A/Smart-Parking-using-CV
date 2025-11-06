from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
import mysql.connector
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Load MySQL credentials from environment variables
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'Unni2005!@#'),  # Update as needed
    'database': os.getenv('DB_NAME', 'smart_parking')
}

# Get database connection (using Flask's `g` for better management)
def get_db_connection():
    if 'db_conn' not in g:
        g.db_conn = mysql.connector.connect(**DB_CONFIG)
        g.db_cursor = g.db_conn.cursor(dictionary=True)
    return g.db_conn, g.db_cursor

# Close database connection after each request
@app.teardown_appcontext
def close_db_connection(exception=None):
    db_conn = g.pop('db_conn', None)
    db_cursor = g.pop('db_cursor', None)
    if db_cursor:
        db_cursor.close()
    if db_conn:
        db_conn.close()

# Serve the HTML file
@app.route('/')
def index():
    return send_file('pslot.html')

# Get parking status from database
@app.route('/get_parking_status', methods=['GET'])
def get_parking_status():
    try:
        conn, cursor = get_db_connection()
        cursor.execute("SELECT entry_id, slot_number, is_ev, vehicle_number, entry_time, exit_time FROM SmartParking")
        results = cursor.fetchall()

        parking_status = {
            row['slot_number']: {
                'entry_id': row['entry_id'],
                'is_ev': bool(row['is_ev']),
                'status': 'available' if row['exit_time'] else 'occupied',
                'vehicle_number': row['vehicle_number'],
                'entry_time': row['entry_time'].isoformat() if row['entry_time'] else None,
                'exit_time': row['exit_time'].isoformat() if row['exit_time'] else None
            } for row in results
        }
        return jsonify(parking_status)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500

# Update parking slot status
@app.route('/update_slot', methods=['POST'])
def update_slot():
    try:
        data = request.json
        slot_number = data.get('slot_number')
        is_ev = data.get('is_ev', False)
        action = data.get('action')
        vehicle_number = data.get('vehicle_number', '')

        if not slot_number or not action:
            return jsonify({'error': 'Missing required fields'}), 400

        conn, cursor = get_db_connection()
        current_time = datetime.now()

        if action == 'entry':
            cursor.execute("SELECT slot_number, exit_time FROM SmartParking WHERE slot_number = %s AND exit_time IS NULL", (slot_number,))
            if cursor.fetchone():
                return jsonify({'error': 'Slot is already occupied'}), 400

            cursor.execute(
                "INSERT INTO SmartParking (slot_number, is_ev, vehicle_number, entry_time, exit_time) VALUES (%s, %s, %s, %s, NULL)",
                (slot_number, is_ev, vehicle_number, current_time)
            )

        elif action == 'exit':
            cursor.execute("SELECT entry_id FROM SmartParking WHERE slot_number = %s AND exit_time IS NULL", (slot_number,))
            if not cursor.fetchone():
                return jsonify({'error': 'No vehicle found in this slot'}), 400

            cursor.execute("UPDATE SmartParking SET exit_time = %s WHERE slot_number = %s AND exit_time IS NULL", (current_time, slot_number))

        conn.commit()
        return jsonify({'success': True})
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500

if __name__ == '__main__':
    from waitress import serve
    print("🚀 Server running on http://localhost:9854")
    serve(app, host='0.0.0.0', port=9854)
