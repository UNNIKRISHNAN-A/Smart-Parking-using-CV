from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import mysql.connector

app = Flask(__name__)  # Corrected __name__
CORS(app)  # Enable CORS for AJAX requests

# MySQL Database Configuration
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "...",  # Update if needed
    "database": "smart_parking",
}

@app.route('/')
def dashboard():
    """Render the dashboard HTML page."""
    return render_template('dashboard01.html')

@app.route('/parking-entries', methods=['GET'])
def get_parking_entries():
    """Fetches the latest parking entries from MySQL, including EV slot status."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT entry_id, vehicle_number, slot_number, entry_time, is_ev FROM SmartParking ORDER BY entry_time DESC")
        entries = cursor.fetchall()
        return jsonify(entries)
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()

@app.route('/parking-entries', methods=['POST'])
def add_parking_entry():
    """Adds a new parking entry to the database, including EV slot information."""
    data = request.json
    vehicle_number = data.get('vehicle_number')
    slot_number = data.get('slot_number')
    is_ev = data.get('is_ev', False)  # Default to False if not provided

    if not vehicle_number or not slot_number:
        return jsonify({"error": "Vehicle number and slot number are required"}), 400

    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        # Check if the slot is already occupied
        cursor.execute("SELECT COUNT(*) FROM SmartParking WHERE slot_number = %s AND is_ev = %s", (slot_number, is_ev))
        slot_count = cursor.fetchone()[0]

        if slot_count > 0:
            return jsonify({"error": "Slot is already occupied"}), 400

        sql = "INSERT INTO SmartParking (vehicle_number, slot_number, entry_time, is_ev) VALUES (%s, %s, NOW(), %s)"
        cursor.execute(sql, (vehicle_number, slot_number, is_ev))
        connection.commit()
        return jsonify({"message": "Entry added successfully"}), 201
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()

@app.route('/parking-entries/<int:entry_id>', methods=['DELETE'])
def delete_parking_entry(entry_id):
    """Deletes a parking entry from the database."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()
        cursor.execute("DELETE FROM SmartParking WHERE entry_id = %s", (entry_id,))
        connection.commit()
        return jsonify({"message": "Entry deleted successfully"}), 200
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()

if __name__ == '__main__':  # Corrected __name__
    from waitress import serve
    print("🚀 Server running on http://localhost:9843")
    serve(app, host="0.0.0.0", port=9843)

