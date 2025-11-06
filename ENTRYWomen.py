import cv2
import easyocr
import numpy as np
import time
import mysql.connector
from collections import Counter

# Load Haar Cascade for plate detection
plate_cascade = cv2.CascadeClassifier("haarcascade_russian_plate_number.xml")

# Initialize EasyOCR Reader with optimized settings
reader = easyocr.Reader(['en'], gpu=False)  # Disable GPU if not available

# MySQL Database Configuration
DB_CONFIG = {
    "host": "localhost",
    "user": "root",  
    "password": "...",  
    "database": "smart_parking",
}

def is_green_plate(plate):
    """Optimized green plate detection"""
    if plate is None or plate.size == 0:
        return False
    
    # Downsample for faster processing
    small_plate = cv2.resize(plate, (100, 50), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small_plate, cv2.COLOR_BGR2HSV)
    
    # Define green color range
    lower_green = np.array([35, 50, 50])  # Adjusted for better green detection
    upper_green = np.array([85, 255, 255])
    
    mask = cv2.inRange(hsv, lower_green, upper_green)
    return (np.count_nonzero(mask) / mask.size > 0.3)

def preprocess_plate(plate):
    """Optimized plate preprocessing"""
    if plate is None or plate.size == 0:
        return None
    
    # Convert to grayscale and enhance contrast
    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    
    # Apply adaptive thresholding
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 11, 2)
    return thresh

def validate_and_correct_plate(text):
    """Validate and correct Indian plate format"""
    if len(text) < 6:  # Minimum length for partial plates
        return None
    
    # Common OCR corrections
    corrections = {
        '0': 'O', '1': 'I', '2': 'Z', '4': 'A', '5': 'S',
        '6': 'G', '7': 'Z', '8': 'B', 'B': '8', 'D': '0',
        'I': '1', 'O': '0', 'Q': '0', 'S': '5', 'Z': '2'
    }
    
    # Apply corrections
    corrected = []
    for i, char in enumerate(text.upper()):
        if char in corrections:
            corrected.append(corrections[char])
        else:
            corrected.append(char)
    
    # Take first 10 characters for full plates
    plate = ''.join(corrected)[:10]
    
    # Basic validation - at least 2 letters followed by 2 numbers
    if (len(plate) >= 4 and 
        plate[0].isalpha() and plate[1].isalpha() and
        plate[2].isdigit() and plate[3].isdigit()):
        return plate
    return None

def find_next_slot(is_ev):
    """Optimized slot finding with single DB connection"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(buffered=True)
        
        if is_ev:
            cursor.execute("SELECT slot_number FROM SmartParking WHERE slot_number LIKE 'EV%' AND exit_time IS NULL")
            occupied = {row[0] for row in cursor.fetchall()}
            for i in range(1, 6):
                if f"EV{i}" not in occupied:
                    return f"EV{i}"
        else:
            # Check A6-A9 first
            cursor.execute("SELECT slot_number FROM SmartParking WHERE slot_number LIKE 'A%' AND exit_time IS NULL")
            occupied = {row[0] for row in cursor.fetchall()}
            for i in range(6, 10):
                if f"A{i}" not in occupied:
                    return f"A{i}"
            # Then check A1-A5
            for i in range(1, 6):
                if f"A{i}" not in occupied:
                    return f"A{i}"
        return None
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return None
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

def main():
    # Initialize video capture with reduced resolution for better performance
    cap = cv2.VideoCapture(0)
    cap.set(3, 1280)  # Reduced from 1920 for better performance
    cap.set(4, 720)   # Reduced from 1080
    
    plate_candidates = []
    green_detections = []
    start_time = time.time()
    
    print("Starting license plate detection...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera error")
            break
        
        # Convert to grayscale for detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect plates with optimized parameters
        plates = plate_cascade.detectMultiScale(
            gray, 
            scaleFactor=1.05,  # Reduced from 1.1 for better detection
            minNeighbors=3,    # Reduced from 5
            minSize=(100, 30), # Minimum plate size
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        # Process detected plates
        if len(plates) > 0:
            x, y, w, h = plates[0]  # Take the most prominent plate
            plate_img = frame[y:y+h, x:x+w]
            
            # Preprocess and read plate
            processed = preprocess_plate(plate_img)
            if processed is not None:
                results = reader.readtext(
                    processed,
                    detail=0,
                    allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                    paragraph=True,
                    min_size=20,
                    text_threshold=0.6
                )
                
                if results:
                    # Get the longest detected text
                    raw_text = max(results, key=len)
                    plate_text = validate_and_correct_plate(raw_text)
                    
                    if plate_text:
                        plate_candidates.append(plate_text)
                        green_detections.append(is_green_plate(plate_img))
                        
                        # Visual feedback
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                        cv2.putText(frame, plate_text, (x, y-10), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            # Break after 4 seconds of detection
            if time.time() - start_time >= 4:
                break
        else:
            # Break if no plate detected for 5 seconds
            if time.time() - start_time >= 5:
                print("No plate detected within 5 seconds")
                break
        
        # Show frame
        cv2.imshow("License Plate Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    # Release resources
    cap.release()
    cv2.destroyAllWindows()
    
    # Process results
    if plate_candidates:
        # Get most common plate
        final_plate = Counter(plate_candidates).most_common(1)[0][0]
        is_ev = Counter(green_detections).most_common(1)[0][0]
        
        print(f"\nDetected Plate: {final_plate}")
        print(f"Vehicle Type: {'EV' if is_ev else 'Regular'}")
        
        # Check if already parked
        parked_slot = is_vehicle_already_parked(final_plate)
        if parked_slot:
            print(f"Already parked at {parked_slot}")
        else:
            # Find available slot
            slot = find_next_slot(is_ev)
            if slot:
                save_to_database(final_plate, is_ev, slot)
                print(f"Assigned to {slot}")
            else:
                print("No available slots")
    else:
        print("\nNo valid plates detected")

if __name__ == "__main__":
    main()