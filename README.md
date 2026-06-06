# 🌊 Edge AI Gateway: Disaster Resilience & Flood Monitoring

A highly fault-tolerant, multi-threaded Edge AI gateway designed for real-time flood and debris monitoring at Huanggang Creek. This system tackles the "NMS Latency Tax" and extreme data frequency mismatches by decoupling I/O from inference, fusing heterogeneous sensor data, and implementing robust graceful degradation for remote edge nodes.

---

## 🏗️ System Architecture

The pipeline strictly decouples high-frequency scalar data from low-frequency tensor data to prevent deadlocks and Out-Of-Memory (OOM) crashes on constrained 2-Core edge hardware.

```mermaid
graph TD
    subgraph Edge Device
        direction TB
        
        %% Producers
        S[Ultrasonic Sensor Simulation<br/>20Hz] -->|math.sin + noise| SQ[Bounded Queue<br/>maxsize=100]
        C[Surveillance Camera Feed<br/>Mock Frames] --> QC[QC & Diff Detector<br/>Wake Threshold: 0.15m]
        
        %% Consumer / Inference
        QC -- Active Alarm --> Y[YOLOv10 / TFLite INT8<br/>2Hz Inference]
        QC -- Calm Water --> Z[Power-Saving Mode<br/>Sleep]
        Y --> VQ[Bounded Queue<br/>maxsize=1<br/>Drop-and-Replace]
        
        %% Orchestrator
        SQ --> F{Temporal Alignment<br/>Orchestrator}
        VQ --> F
        
        F -->|Nearest-Neighbor Join<br/>Tolerance < 100ms| P[Protocol Packager]
    end

    subgraph Cloud Exfiltration
        P -->|70% Success| M((MQTT Broker<br/>QoS 1))
        P -->|30% Failure / No Network| L[(local_backup.jsonl<br/>Graceful Degradation)]
    end


🎯 Engineering Trade-offs & Architecture Decisions

This architecture is explicitly engineered to address the core requirements of modern Edge AI systems:
1. System Architecture (OOM Prevention & Stability)

    Decoupling I/O and Inference: Python's threading module isolates the 20Hz sensor stream from the heavy 2Hz computer vision inference.

    Queue Stability (Active Frame Dropping): The vision queue implements a strict maxsize=1 constraint with put_nowait() and get_nowait() eviction logic. If the CPU bottlenecks, stale frames are actively dropped rather than accumulating in memory. We trade redundant historical data for absolute system stability and real-time freshness.

    Deadlock Prevention: Global threading.Event() hooks and queue timeouts ensure clean, safe shutdowns across all components without thread hanging.

2. Data Engineering (Heterogeneous Fusion)

    Nearest-Neighbor Temporal Join: The synchronization orchestrator "latches" onto the slower 2Hz vision timestamp. It then searches the 20Hz sensor buffer for the closest corresponding temporal data point, enforcing a strict <100ms synchronization tolerance.

    Graceful Degradation (MQTT Fallback): Simulates a volatile edge network. If the cloud connection drops, the pipeline catches the failure and dynamically redirects the packaged JSON payload to a local disk append log (local_backup.jsonl) for future batch transmission.

3. Optimization (Latency & Power)

    Power-Saving Difference Detector: A baseline delta tracker monitors the scalar water level. If the water is calm (delta < 0.15m and level < 2.2m), the system bypasses the computationally expensive YOLO inference entirely, conserving critical edge battery life.

    Quantized Inference: Designed to support INT8 quantized models (.tflite) or NMS-Free architectures (YOLOv10) to reduce memory footprint and bypass the Non-Maximum Suppression latency tax on edge CPUs.

💻 Environment Setup

Designed and profiled for lightweight environments (e.g., Linux Mint, Python 3.12, GitHub Codespaces 2-Core VM).
Prerequisites

    Clone this repository.

    Create and activate a Python virtual environment:

Bash

python3.12 -m venv .venv
source .venv/bin/activate

    Install the required dependencies:

Bash

pip install -r requirements.txt

(Note: Linux users may need to run sudo apt-get install libopenblas-dev liblapack-dev if OpenCV raises backend array errors).
🚀 Execution & Results
Running the Gateway
Bash

python final_showcase_gateway.py

Expected Output & Terminal Profiling

The terminal will actively log the system state, demonstrating the power-saving mode, visual QC drops, and successful fusion joins. At t=12s, the system injects a massive debris spike to trigger the Active Alarm.
Plaintext

[Thread 1] Huanggang Creek Sensor active (20Hz)...
[Thread 2] Vision Surveillance Engine active (2Hz)...
[Thread 3] Temporal Alignment Orchestrator active...
[GATEWAY] Status: Calm (1.52m). YOLO sleeping to save power.
...
[GATEWAY] ACTIVE ALARM! (2.35m). Executing YOLO Driftwood Detection.

[FUSION ENGINE] Synced Payload Compiled!
    | Time Error: 24.15 ms | Level: 2.35m | Debris: 2
    -> [CLOUD] Upload success (MQTT QoS 1).
    -> [FATAL COMM] Network down. Triggering DLQ Local Cache.

Local Fallback Validation (local_backup.jsonl)

When the network fails, payloads are serialized to disk locally. You can inspect the output:
JSON

{"timestamp": 1715692801.45, "water_level_m": 2.35, "driftwood_detections": 2, "sync_error_ms": 24.15, "ai_latency_ms": 145.2}
{"timestamp": 1715692802.12, "water_level_m": 2.41, "driftwood_detections": 3, "syn
