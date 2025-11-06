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
    "password": "...",  
    "database": "smart_parking",
}

# Function to validate the format of the detected plate
def validate_plate_format(text):
    """Validate the format of the detected plate."""
    if len(text) != 10:
        return False
    return (text[0].isalpha() and text[1].isalpha() and
            text[2].isdigit() and text[3].isdigit() and
            text[4].isalpha() and text[5].isalpha() and
            text[6].isdigit() and text[7].isdigit() and
            text[8].isdigit() and text[9].isdigit())

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
corrected_texts = []
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
            else:
                # Still collect the original text for review
                plate_texts.append(best_text)

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