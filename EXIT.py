import cv2
import easyocr
import numpy as np
import time
import mysql.connector

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

# Function to preprocess plate for better OCR
def preprocess_plate(plate):
    if plate is None or plate.size == 0:
        return None
    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)  
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)  
    enhanced = cv2.equalizeHist(blurred)  
    return enhanced

# Function to check if a vehicle is parked and get slot number
def get_parked_vehicle_slot(vehicle_number):
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(buffered=True)
        
        print(f"🔍 Checking parking status for: {vehicle_number}")
        
        cursor.execute(
            "SELECT slot_number FROM SmartParking WHERE vehicle_number = %s AND exit_time IS NULL",
            (vehicle_number,)
        )
        result = cursor.fetchone()
        
        if result:
            print(f"✅ Vehicle {vehicle_number} is parked in slot: {result[0]}")
        else:
            print(f"⚠️ No active parking record found for {vehicle_number}")

        return result[0] if result else None
    
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
        return None
    finally:
        cursor.close()
        connection.close()

# Function to completely remove a vehicle from the database
def remove_from_database(vehicle_number):
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()
        
        print(f"🛠 Removing vehicle: {vehicle_number} from the database.")
        
        # DELETE the vehicle record from the database
        cursor.execute(
            "DELETE FROM SmartParking WHERE vehicle_number = %s AND exit_time IS NULL",
            (vehicle_number,)
        )
        connection.commit()

        # Check if any row was deleted
        if cursor.rowcount > 0:
            print(f"✅ Vehicle {vehicle_number} has exited and record removed from database.")
        else:
            print(f"⚠️ No active parking record found for {vehicle_number}. Check OCR result or database records.")

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
            best_text = max(result, key=len).upper().strip()  # Convert to uppercase & remove spaces
            if len(best_text) >= 6:  
                plate_texts.append(best_text)

        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(frame, f"Capturing {captured_images+1}/{max_images}", (x, y - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        captured_images += 1
        time.sleep(0.25)  

    cv2.imshow("Number Plate Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Process the best detected plate
if plate_texts:
    final_plate_text = max(set(plate_texts), key=plate_texts.count)  

    print("\n🚗 Final Detected Plate Number:", final_plate_text)

    # Check if vehicle is currently parked
    existing_slot = get_parked_vehicle_slot(final_plate_text)
    if existing_slot:
        
        print(f"🚗 {final_plate_text} is parked in slot {existing_slot}. Removing from database...")
        remove_from_database(final_plate_text)
    else:
        print(f"⚠️ No active parking record found for {final_plate_text}. Possible issues:\n"
              f"  - No matching record in database\n"
              f"  - Vehicle already exited")


else:
    print("\n❌ No plate detected.")

cap.release()
cv2.destroyAllWindows()
