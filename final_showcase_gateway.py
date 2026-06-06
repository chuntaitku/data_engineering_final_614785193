import os
import sys
import time
import json
import random
import queue
import threading
import statistics
import math
import cv2
import numpy as np

# Handle conditional imports for Edge Inference
try:
    import tflite_runtime.interpreter as tflite
    print("[*] Init: tflite_runtime loaded successfully.")
except ImportError:
    try:
        import tensorflow.lite as tflite
        print("[*] Init: Falling back to full tensorflow.lite interpreter.")
    except ImportError:
        print("[!] Warning: TFLite not found. Vision inference will run in Mock YOLOv10 mode.")
        tflite = None

# =================================================================
# Course: Data Engineering (CSIE, Tamkang University)
# Week 16 Showcase: Disaster Resilience & Flood Monitoring (Topic II)
# =================================================================

# --- Core System Thresholds ---
WINDOW_SIZE = 10
MODIFIED_Z_THRESHOLD = 3.5
BLUR_THRESHOLD = 50.0       # Lowered to prevent silent drops on mock frames
MIN_BRIGHTNESS = 20.0       # Lowered to prevent silent drops on mock frames
MAX_BRIGHTNESS = 240.0
WAKE_THRESHOLD_M = 0.15     # Power-saving delta wake threshold
CRITICAL_WATER_LEVEL = 2.2  # Absolute wake threshold

# --- Bounded Thread-Safe Queues (OOM Prevention) ---
raw_sensor_stream = queue.Queue(maxsize=100)
vision_payload_queue = queue.Queue(maxsize=1) # Drops stale frames instantly
stop_event = threading.Event()

# Global variable for power-saving difference detector
current_water_level = 1.5 

# =================================================================
# MODULE 1: Huanggang Creek Sensor Playback (20Hz)
# =================================================================

def sensor_producer_thread():
    """Simulates an Ultrasonic Water Level Sensor using mathematical wave patterns."""
    global current_water_level
    print("[Thread 1] Huanggang Creek Sensor active (20Hz)...")
    window = queue.deque(maxlen=WINDOW_SIZE)
    start_sim_time = time.time()
    
    while not stop_event.is_set():
        elapsed = time.time() - start_sim_time
        
        # 1. Base Wave Function: Sine wave + noise + increasing storm surge
        base_tide = 1.5 + math.sin(elapsed * 0.5) * 0.1
        storm_surge = 0.08 * (elapsed - 5) if elapsed > 5 else 0.0 # Flood starts at 5s
        noise = np.random.normal(0, 0.02)
        
        raw_value = base_tide + storm_surge + noise
        
        # 2. Showcase Requirement: Inject a sudden sensor spike (Debris) at t=12s
        if 12.0 <= elapsed <= 12.5:
            raw_value += 1.5 # Massive spike
            
        # 3. W3: MAD Outlier Filter
        if len(window) < WINDOW_SIZE:
            window.append(raw_value)
            continue
            
        current_median = statistics.median(window)
        deviations = [abs(x - current_median) for x in window]
        mad = statistics.median(deviations) + 0.0001
        m_score = 0.6745 * (raw_value - current_median) / mad
        
        if abs(m_score) > MODIFIED_Z_THRESHOLD:
            # We log the anomaly but reject it from the rolling baseline
            pass 
        else:
            window.append(raw_value)
            
        # Update global state for Vision Thread's Power-Saving logic
        current_water_level = round(raw_value, 3)
        
        sensor_data = {"ts": time.time(), "val": current_water_level}
        
        # OOM Safe Insert
        try:
            raw_sensor_stream.put_nowait(sensor_data)
        except queue.Full:
            try: raw_sensor_stream.get_nowait()
            except queue.Empty: pass
            raw_sensor_stream.put(sensor_data)
            
        time.sleep(0.05) # 20Hz

# =================================================================
# MODULE 2: Vision Pipeline & Power-Saving Mode (2Hz)
# =================================================================

def vision_pipeline_thread():
    """Captures frames and executes YOLOv10 ONLY when water is turbulent."""
    print("[Thread 2] Vision Surveillance Engine active (2Hz)...")
    
    last_processed_level = 1.5
    
    # Create a light gray mock image so it passes the Brightness QC
    mock_frame = np.full((1080, 1920, 3), 120, dtype=np.uint8)
    # Add random edges so it passes the Laplacian Blur QC
    cv2.putText(mock_frame, "HUANGGANG CREEK", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)

    while not stop_event.is_set():
        t_start = time.perf_counter()
        
        # --- POWER SAVING DIFFERENCE DETECTOR (W13/W16 Req) ---
        level_delta = abs(current_water_level - last_processed_level)
        
        if level_delta < WAKE_THRESHOLD_M and current_water_level < CRITICAL_WATER_LEVEL:
            print(f"[GATEWAY] Status: Calm ({current_water_level}m). YOLO sleeping to save power.")
            time.sleep(0.5) 
            continue
            
        print(f"[GATEWAY] ACTIVE ALARM! ({current_water_level}m). Executing YOLO Driftwood Detection.")
        last_processed_level = current_water_level
        
        # --- VISION QC & PREPROCESSING ---
        gray_image = cv2.cvtColor(mock_frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray_image, cv2.CV_64F).var()
        mean_brightness = gray_image.mean()
        
        if laplacian_var < BLUR_THRESHOLD or mean_brightness < MIN_BRIGHTNESS:
            print(f"[Vision QC] Frame dropped! Blur: {laplacian_var:.1f}, Bright: {mean_brightness:.1f}")
            time.sleep(0.5)
            continue
            
        # Simulate Inference computation time (Simulating YOLOv10 on CPU)
        time.sleep(0.15) 
        
        vision_result = {
            "ts": time.time(),
            "driftwood_count": random.randint(1, 3) if current_water_level > 2.0 else 0,
            "latency_ms": round((time.perf_counter() - t_start) * 1000, 2)
        }
        
        # Bounded Frame Dropping Queue Delivery
        try:
            vision_payload_queue.put_nowait(vision_result)
        except queue.Full:
            try: vision_payload_queue.get_nowait()
            except queue.Empty: pass
            vision_payload_queue.put(vision_result)
            
        time.sleep(0.35) # Balance to hit ~2Hz max

# =================================================================
# MODULE 3: Latching, Fusion & Cloud Exfiltration
# =================================================================

def cloud_publish_with_fallback(payload):
    """Graceful Degradation: Simulates MQTT drop and writes to local.jsonl."""
    # Simulate network dropping 30% of the time to prove fallback works
    if random.random() > 0.30:
        print(f"    -> [CLOUD] Upload success (MQTT QoS 1).")
    else:
        print("    -> [FATAL COMM] Network down. Triggering DLQ Local Cache.")
        with open("local_backup.jsonl", "a") as backup_file:
            backup_file.write(json.dumps(payload) + "\n")

def synchronization_orchestrator():
    """Latching engine executing Temporal Nearest-Neighbor Joins."""
    print("[Thread 3] Temporal Alignment Orchestrator active...")
    last_known_sensor = None
    
    while not stop_event.is_set():
        try:
            # Latch onto the Vision output
            vision_packet = vision_payload_queue.get(timeout=1.0)
        except queue.Empty:
            continue
            
        best_match = last_known_sensor
        min_temporal_delta = abs(vision_packet["ts"] - last_known_sensor["ts"]) if last_known_sensor else 999.0
        
        # Retrieve historical readings to compute optimal match
        while not raw_sensor_stream.empty():
            sensor_packet = raw_sensor_stream.get()
            current_delta = abs(vision_packet["ts"] - sensor_packet["ts"])
            
            if current_delta < min_temporal_delta:
                min_temporal_delta = current_delta
                best_match = sensor_packet
                
            last_known_sensor = sensor_packet
            
        # Match Constraint Validation (< 100ms offset window)
        if best_match and min_temporal_delta < 0.10:
            integrated_payload = {
                "timestamp": vision_packet["ts"],
                "water_level_m": best_match["val"],
                "driftwood_detections": vision_packet["driftwood_count"],
                "sync_error_ms": round(min_temporal_delta * 1000, 2),
                "ai_latency_ms": vision_packet["latency_ms"]
            }
            
            print(f"\n[FUSION ENGINE] Synced Payload Compiled!")
            print(f"    | Time Error: {integrated_payload['sync_error_ms']} ms | Level: {integrated_payload['water_level_m']}m | Debris: {integrated_payload['driftwood_detections']}")
            
            cloud_publish_with_fallback(integrated_payload)
        else:
            print(f"[!] Fusion Drop: Temporal delta outside bounds ({min_temporal_delta * 1000:.2f} ms).")

# =================================================================
# MAIN EXECUTION
# =================================================================

if __name__ == "__main__":
    print("=================================================================")
    print("=== FINAL SHOWCASE: DISASTER RESILIENCE & FLOOD MONITORING    ===")
    print("=================================================================\n")
    
    # Clear old cache
    if os.path.exists("local_backup.jsonl"):
        os.remove("local_backup.jsonl")
    
    t1 = threading.Thread(target=sensor_producer_thread, daemon=True)
    t2 = threading.Thread(target=vision_pipeline_thread, daemon=True)
    t3 = threading.Thread(target=synchronization_orchestrator, daemon=True)
    
    t1.start()
    t2.start()
    t3.start()
    
    try:
        print("[System] Press Ctrl+C to terminate cleanly...\n")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Interruption detected. Initiating clean termination sequence...")
        stop_event.set()
        time.sleep(1)
        print("[+] System terminated gracefully. Check local_backup.jsonl for cached data.")