import cv2
import easyocr
import numpy as np
from datetime import datetime
import mysql.connector
import re
import time

# Load Haar Cascade for plate detection
plate_cascade = cv2.CascadeClassifier("haarcascade_russian_plate_number.xml")

# Initialize EasyOCR Reader
reader = easyocr.Reader(['en'])

# MySQL Database Configuration
DB_CONFIG = {
    "host": "localhost",
    "user": "root",  
    "password": "Unni2005!@#",  
    "database": "smart_parking",
}

def validate_plate_format(text):
    """Strict validation for Indian format: AA00BB0000"""
    pattern = r"^[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4}$"
    match = re.match(pattern, text)
    return bool(match)



# Function to correct common misreads of characters
def correct_character(char, position):
    """Correct common misreads of characters."""
    correction_map = {
        0: {'0':'D', '1':'D', '4':'A', '7':'D', '8':'B'},
        1: {'0':'L', '1':'I', '2':'Z', '4':'A', '5':'S', '7':'Z', '8':'B'},
        2: {'O':'0', 'I':'1', 'Z':'2', 'A':'4', 'S':'5', 'G':'6', 'Z':'7', 'B':'8'},
        3: {'O':'0', 'I':'1', 'Z':'2', 'A':'4', 'S':'5', 'G':'6', 'Z':'7', 'B':'8'},
        4: {'0':'D', '1':'I', '2':'Z', '4':'A', '5':'S', '7':'Z', '8':'B'},
        5: {'0':'D', '1':'I', '2':'Z', '4':'A', '5':'S', '7':'Z', '8':'B'},
        6: {'O':'0', 'I':'1', 'Z':'2', 'A':'4', 'S':'5', 'G':'6', 'Z':'7', 'B':'8'},
        7: {'O':'0', 'I':'1', 'Z':'2', 'A':'4', 'S':'5', 'G':'6', 'Z':'7', 'B':'8'},
        8: {'O':'0', 'I':'1', 'Z':'2', 'A':'4', 'S':'5', 'G':'6', 'Z':'7', 'B':'8'},
        9: {'O':'0', 'I':'1', 'Z':'2', 'A':'4', 'S':'5', 'G':'6', 'Z':'7', 'B':'8'}
    }
    return correction_map[position].get(char, char)

# Function to apply corrections to the entire plate text
def correct_plate_text(text):
    """Apply character corrections to the plate text based on position."""
    if len(text) != 10:
        return text
    
    corrected_text = ""
    for i, char in enumerate(text):
        corrected_text += correct_character(char, i)
    
    return corrected_text

# Function to check if a plate is green (EV detection)
def is_green_plate(plate):
    if plate is None or plate.size == 0:
        return False  

    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    lower_green = np.array([30, 40, 40])  
    upper_green = np.array([90, 255, 255])  

    mask = cv2.inRange(hsv, lower_green, upper_green)
    green_pixels = np.sum(mask == 255)
    total_pixels = plate.shape[0] * plate.shape[1]

    return (green_pixels / total_pixels) > 0.3  

# Function to preprocess plate for better OCR
def preprocess_plate(plate):
    if plate is None or plate.size == 0:
        return None

    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)  
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)  
    enhanced = cv2.equalizeHist(blurred)  
    return enhanced

# Function to find the next available EV slot
def find_next_ev_slot():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(buffered=True)
        cursor.execute("SELECT slot_number FROM SmartParking WHERE slot_number LIKE 'EV%' AND exit_time IS NULL")
        occupied_slots = {row[0] for row in cursor.fetchall()}
        
        for i in range(1, 6):  # EV1 to EV5
            ev_slot = f"EV{i}"
            if ev_slot not in occupied_slots:
                return ev_slot
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
    finally:
        cursor.close()
        connection.close()
    return None

# Function to find the next available regular slot
def find_next_regular_slot():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(buffered=True)
        cursor.execute("SELECT slot_number FROM SmartParking WHERE slot_number LIKE 'A%' AND exit_time IS NULL")
        occupied_slots = {row[0] for row in cursor.fetchall()}
        
        for i in range(1, 10):  # A1 to A9
            regular_slot = f"A{i}"
            if regular_slot not in occupied_slots:
                return regular_slot
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
    finally:
        cursor.close()
        connection.close()
    return None

# Function to check if a vehicle is already in the parking lot
def is_vehicle_already_parked(vehicle_number):
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(buffered=True)
        cursor.execute("SELECT slot_number FROM SmartParking WHERE vehicle_number = %s AND exit_time IS NULL", (vehicle_number,))
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        return result[0] if result else None
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
        return None

def save_to_database(vehicle_number, is_ev, slot_number):
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()
        sql = """
        INSERT INTO SmartParking (vehicle_number, is_ev, slot_number, entry_time, exit_time)
        VALUES (%s, %s, %s, %s, NULL)
        """
        entry_time = datetime.now()
        cursor.execute(sql, (vehicle_number, int(is_ev), slot_number, entry_time))
        connection.commit()
        print(f"✅ Stored {vehicle_number} in the database with slot {slot_number} at {entry_time}")
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
    finally:
        cursor.close()
        connection.close()

# Open webcam
cap = cv2.VideoCapture(0)
cap.set(3, 1920)  
cap.set(4, 1080)  

time.sleep(2)  

plate_texts = []
corrected_texts = []
green_detections = []
captured_images = 0
max_images = 5  

while captured_images < max_images:
    ret, frame = cap.read()
    if not ret or frame is None or frame.size == 0:
        print("⚠️ Error: Could not read frame from camera.")
        continue  

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    plates = plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 50))

    if len(plates) > 0:
        x, y, w, h = plates[0]  
        plate = frame[y:y+h, x:x+w]

        # Preprocess plate before OCR
        processed_plate = preprocess_plate(plate)

        # OCR for number plate text
        result = reader.readtext(processed_plate, detail=0, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

        if result:
            best_text = max(result, key=len).upper()  
            
            # Apply character correction if text length matches expected format
            if len(best_text) == 10:
                corrected_text = correct_plate_text(best_text)
                corrected_texts.append(corrected_text)
                
                # Display both original and corrected text for debugging
                cv2.putText(frame, f"Original: {best_text}", (x, y - 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.putText(frame, f"Corrected: {corrected_text}", (x, y - 20), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Only add to plates list if format is valid
                if validate_plate_format(corrected_text):
                    plate_texts.append(corrected_text)
                    green_detections.append(is_green_plate(plate))
            else:
                # Still collect the original text for review
                plate_texts.append(best_text)
                green_detections.append(is_green_plate(plate))

        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(frame, f"Capturing {captured_images+1}/{max_images}", (x, y - 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

        captured_images += 1
        time.sleep(0.25)  

    cv2.imshow("Number Plate Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Process the best detected plate
if plate_texts:
    # Prioritize valid formatted plates if any
    valid_plates = [text for text in plate_texts if validate_plate_format(text)]
    
    if valid_plates:
        final_plate_text = max(set(valid_plates), key=valid_plates.count)
        print("\n🔍 Valid plate format detected!")
    else:
        # If no valid plates, use the most common detection
        final_plate_text = max(set(plate_texts), key=plate_texts.count)
        print("\n⚠️ No valid plate format detected. Using best guess.")
    
    is_ev = max(set(green_detections), key=green_detections.count)  

    print("\n🚗 Final Detected Plate Number:", final_plate_text)
    print(f"⚡ EV Detected: {'Yes ✅' if is_ev else 'No ❌'}")

    # Check if vehicle is already parked
    existing_slot = is_vehicle_already_parked(final_plate_text)
    if existing_slot:
        print(f"⚠️ Vehicle already allocated to slot: {existing_slot}")
    else:
        parking_slot = None

        if is_ev:
            parking_slot = find_next_ev_slot()
            if not parking_slot:
                parking_slot = find_next_regular_slot()
        else:
            parking_slot = find_next_regular_slot()
            if not parking_slot:
                parking_slot = find_next_ev_slot()

        if parking_slot:
            print(f"🚗 DETECTED LICENSE PLATE: {final_plate_text} | Assigned Slot: {parking_slot}")
            save_to_database(final_plate_text, is_ev, parking_slot)
        else:
            print("❌ All slots are full. Please proceed to the exit.")
else:
    print("\n❌ No plate detected.")

cap.release()
cv2.destroyAllWindows()