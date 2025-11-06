from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import mysql.connector
from datetime import datetime
from waitress import serve
import os

app = Flask(__name__)
CORS(app)

# Database configuration
db_config = {
    'host': 'localhost',
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'Unni2005!@#'),
    'database': 'smart_parking'
}

def get_db_connection():
    """Create and return a connection to the database"""
    try:
        conn = mysql.connector.connect(**db_config)
        return conn, conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL database: {err}")
        return None, None

@app.route('/')
def home():
    """Render the home page with search form"""
    return render_template('vsearch.html')

@app.route('/search', methods=['POST'])
def search_vehicle():
    """Search for a vehicle by number plate"""
    vehicle_number = request.form.get('vehicle_number')
    
    if not vehicle_number:
        return jsonify({'error': 'Vehicle number is required'}), 400
    
    conn, cursor = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        query = "SELECT * FROM SmartParking WHERE vehicle_number = %s"
        cursor.execute(query, (vehicle_number,))
        results = cursor.fetchall()
        
        # Format timestamps for JSON response
        for result in results:
            if 'entry_time' in result and isinstance(result['entry_time'], datetime):
                result['entry_time'] = result['entry_time'].strftime('%Y-%m-%d %H:%M:%S')
                
        return jsonify({'results': results})
    
    except mysql.connector.Error as err:
        return jsonify({'error': f'Database error: {err}'}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/vehicles', methods=['GET'])
def get_all_vehicles():
    """Get all vehicles (for initial display)"""
    conn, cursor = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        query = "SELECT * FROM SmartParking ORDER BY entry_time DESC LIMIT 100"
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Format timestamps for JSON response
        for result in results:
            if 'entry_time' in result and isinstance(result['entry_time'], datetime):
                result['entry_time'] = result['entry_time'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({'results': results})
    
    except mysql.connector.Error as err:
        return jsonify({'error': f'Database error: {err}'}), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    print("🚀 Server running on http://localhost:9871")
    serve(app, host='0.0.0.0', port=9871)