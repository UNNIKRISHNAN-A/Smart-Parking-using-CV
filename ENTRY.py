import cv2
import easyocr
import numpy as np
import time
import mysql.connector
import re

# Load Haar Cascade
plate_cascade = cv2.CascadeClassifier("haarcascade_russian_plate_number.xml")
reader = easyocr.Reader(['en'])

# MySQL Configuration
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Unni2005!@#",
    "database": "smart_parking",
}

# Validate Indian format: AA00BB0000
def validate_plate_format(text):
    pattern = r"^[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4}$"
    return bool(re.match(pattern, text))

# Correct character misreads
def correct_character(char, position):
    correction_map = {
        0: {'0':'D','1':'D','4':'A','7':'D','8':'B'}, 1: {'0':'L','1':'I','2':'Z','4':'A','5':'S','7':'Z','8':'B'},
        2: {'O':'0','I':'1','Z':'2','A':'4','S':'5','G':'6','Z':'7','B':'8'}, 3: {'O':'0','I':'1','Z':'2','A':'4','S':'5','G':'6','Z':'7','B':'8'},
        4: {'0':'D','1':'I','2':'Z','4':'A','5':'S','7':'Z','8':'B'}, 5: {'0':'D','1':'I','2':'Z','4':'A','5':'S','7':'Z','8':'B'},
        6: {'O':'0','I':'1','Z':'2','A':'4','S':'5','G':'6','Z':'7','B':'8'}, 7: {'O':'0','I':'1','Z':'2','A':'4','S':'5','G':'6','Z':'7','B':'8'},
        8: {'O':'0','I':'1','Z':'2','A':'4','S':'5','G':'6','Z':'7','B':'8'}, 9: {'O':'0','I':'1','Z':'2','A':'4','S':'5','G':'6','Z':'7','B':'8'}
    }
    return correction_map[position].get(char, char)

def correct_plate_text(text):
    if len(text) != 10:
        return text
    return ''.join(correct_character(c, i) for i, c in enumerate(text))

def is_green_plate(plate):
    if plate is None or plate.size == 0:
        return False
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([30,40,40]), np.array([90,255,255]))
    return np.sum(mask == 255) / (plate.shape[0] * plate.shape[1]) > 0.3

def preprocess_plate(plate):
    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.equalizeHist(blur)

def find_next_slot(is_ev):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        prefix = "EV" if is_ev else "A"
        limit = 5 if is_ev else 9
        cursor.execute(f"SELECT slot_number FROM SmartParking WHERE slot_number LIKE '{prefix}%' AND exit_time IS NULL")
        occupied = {row[0] for row in cursor.fetchall()}
        for i in range(1, limit + 1):
            slot = f"{prefix}{i}"
            if slot not in occupied:
                return slot
    except mysql.connector.Error as err:
        print(f"❌ DB error: {err}")
    finally:
        cursor.close()
        conn.close()
    return None

def is_vehicle_already_parked(vehicle_number):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT slot_number FROM SmartParking WHERE vehicle_number = %s AND exit_time IS NULL", (vehicle_number,))
        result = cursor.fetchone()
        return result[0] if result else None
    except mysql.connector.Error as err:
        print(f"❌ DB error: {err}")
    finally:
        cursor.close()
        conn.close()

def save_to_database(vehicle_number, is_ev, slot_number):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO SmartParking (vehicle_number, is_ev, slot_number, entry_time, exit_time)
            VALUES (%s, %s, %s, NOW(), NULL)
        """, (vehicle_number, int(is_ev), slot_number))
        conn.commit()
        print(f"✅ Saved {vehicle_number} in slot {slot_number}")
    except mysql.connector.Error as err:
        print(f"❌ DB error: {err}")
    finally:
        cursor.close()
        conn.close()

# Start webcam
cap = cv2.VideoCapture(0)
cap.set(3, 1920)
cap.set(4, 1080)
time.sleep(2)

plate_texts, green_flags = [], []
frame_limit = 5

while len(plate_texts) < frame_limit:
    ret, frame = cap.read()
    if not ret:
        continue

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    plates = plate_cascade.detectMultiScale(gray, 1.1, 5, minSize=(100, 50))

    for x, y, w, h in plates:
        plate_img = frame[y:y+h, x:x+w]
        processed = preprocess_plate(plate_img)
        ocr_result = reader.readtext(processed, detail=0, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

        for raw_text in ocr_result:
            cleaned = correct_plate_text(raw_text.upper())
            if validate_plate_format(cleaned):
                plate_texts.append(cleaned)
                green_flags.append(is_green_plate(plate_img))
                cv2.putText(frame, f"Detected: {cleaned}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
                cv2.rectangle(frame, (x,y), (x+w,y+h), (0,255,0), 2)
                break

    cv2.imshow("License Plate Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# Final decision block
if plate_texts:
    final_plate = max(set(plate_texts), key=plate_texts.count)
    is_ev = max(set(green_flags), key=green_flags.count)

    print(f"\n🚗 Final Plate: {final_plate}")
    print(f"⚡ EV Detected: {'Yes ✅' if is_ev else 'No ❌'}")

    if not validate_plate_format(final_plate):
        print("❌ Invalid plate format. Skipping entry.")
    else:
        existing_slot = is_vehicle_already_parked(final_plate)
        if existing_slot:
            print(f"🚧 Vehicle is already parked at slot: {existing_slot}")
        else:
            slot = find_next_slot(is_ev)
            if slot:
                save_to_database(final_plate, is_ev, slot)
            else:
                print("❌ No available slots.")
else:
    print("❌ No valid plate detected.")
