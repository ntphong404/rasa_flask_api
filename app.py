from flask import Flask, request, jsonify
import os
import re
import textwrap
import subprocess
import psutil
import traceback
import sys
import threading
import time
import glob
from utils.api_response import ApiResponse
from config import (
    ACTIONS_FILE, MODELS_DIR, SUPPORTED_MODEL_EXTENSIONS,
    PROCESS_ATTRIBUTES, CLASS_DEFINITION_PATTERN, ACTION_CLASS_PATTERN,
    DEBUG_MODE, USE_RELOADER
)
from minio_config import (
    MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_ENDPOINT, 
    MINIO_BUCKET, MINIO_SECURE
)
from mongo_config import (
    MONGO_USERNAME, MONGO_PASSWORD, MONGO_DATABASE, 
    MONGO_URI, MODELS_COLLECTION
)

# Import MinIO
try:
    from minio import Minio
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    print("MinIO library not installed. Run: pip install minio")

# Import MongoDB
try:
    from pymongo import MongoClient
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False
    print("MongoDB library not installed. Run: pip install pymongo")

# Check MinIO connection on startup
def check_minio_connection_on_startup():
    """Check MinIO connection when Flask app starts"""
    if not MINIO_AVAILABLE:
        print("MinIO: Library not available - model upload will be disabled")
        return False
        
    try:
        # Create MinIO client
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        
        # Test connection by listing buckets
        buckets = list(minio_client.list_buckets())
        bucket_names = [bucket.name for bucket in buckets]
        
        # Check if our target bucket exists
        bucket_exists = minio_client.bucket_exists(MINIO_BUCKET)
        
        print(f"MinIO: Connected to {MINIO_ENDPOINT}")
        
        return True
        
    except Exception as e:
        print(f"MinIO: Connection failed - {str(e)}")
        return False

# Check MongoDB connection on startup
def check_mongo_connection_on_startup():
    """Check MongoDB connection when Flask app starts"""
    if not MONGO_AVAILABLE:
        print("MongoDB: Library not available - database update will be disabled")
        return False
        
    try:
        # Create MongoDB client
        client = MongoClient(MONGO_URI)
        
        # Test connection by pinging the database
        client.admin.command('ping')
        
        # Get database info
        db = client[MONGO_DATABASE]
        
        # Check if models collection exists
        collections = db.list_collection_names()
        collection_exists = MODELS_COLLECTION in collections
        
        print(f"MongoDB: Connected to {MONGO_DATABASE}")
        print(f"MongoDB: Target collection '{MODELS_COLLECTION}' {'exists' if collection_exists else 'will be created'}")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"MongoDB: Connection failed - {str(e)}")
        return False

app = Flask(__name__)

# --- Training Status Global Variable --- #
training_status = {
    "is_training": False,
    "start_time": None,
    "model_file": None,
    "model_name": None,  # MongoDB Model Name (unique)
    "status": "idle",  # idle, training, completed, failed, stopped
    "error_message": None,
    "upload_success": None,
    "mongo_update": None
}

# --- Upload to MinIO Function --- #
def upload_model_to_minio(model_path):
    """Upload model to MinIO storage"""
    if not MINIO_AVAILABLE:
        print("MinIO library not available - skipping upload")
        return {
            "success": False,
            "error": "MinIO library not installed"
        }
        
    try:
        model_filename = os.path.basename(model_path)
        # Create MinIO client
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        
        # Check if bucket exists, create if not
        if not minio_client.bucket_exists(MINIO_BUCKET):
            minio_client.make_bucket(MINIO_BUCKET)
        
        # Upload file
        result = minio_client.fput_object(
            bucket_name=MINIO_BUCKET,
            object_name=model_filename,
            file_path=model_path,
            content_type="application/octet-stream"
        )
        
        print(f"Model uploaded to MinIO: {model_filename}")
        
        return {
            "success": True,
            "filename": model_filename,
            "bucket": MINIO_BUCKET,
            "etag": result.etag,
            "url": f"http://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{model_filename}"
        }
        
    except Exception as e:
        print(f"MinIO upload failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# --- Update Model URL in MongoDB --- #
def update_model_url_in_mongo(model_name, model_filename, model_url):
    """Update model URL in MongoDB after successful upload to MinIO"""
    if not MONGO_AVAILABLE:
        print("MongoDB library not available - skipping database update")
        return {
            "success": False,
            "error": "MongoDB library not installed"
        }
    
    try:
        # Create MongoDB client
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DATABASE]
        collection = db[MODELS_COLLECTION]
        
        # Update document by model name  
        result = collection.update_one(
            {"name": model_name},  # Filter by name field
            {
                "$set": {
                    "url": model_url,  # Store filename only (BE expects this format)
                    "updatedAt": time.time()  # Use updatedAt to match schema timestamps
                }
            },
            upsert=False  # Don't create new document if not found
        )
        
        if result.matched_count > 0:
            print(f"MongoDB: Updated model URL for name '{model_name}'")
            return {
                "success": True,
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "model_name": model_name,
                "model_filename": model_filename,
                "model_url": model_url
            }
        else:
            print(f"MongoDB: No document found with name '{model_name}'")
            return {
                "success": False,
                "error": f"No document found with name '{model_name}'",
                "matched_count": 0
            }
            
    except Exception as e:
        print(f"MongoDB update failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        try:
            client.close()
        except:
            pass

# --- Training Process Monitor --- #
def run_training_with_monitoring(command, working_dir="."):
    """Run training and monitor completion"""
    global training_status
    
    def training_worker():
        try:
            print(f"Starting training process: {' '.join(command)}")
            
            # Run training process and wait for completion
            process = subprocess.Popen(
                command,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                # Training successful
                print("Training completed successfully!")
                
                # Find newest model
                models = glob.glob(os.path.join(MODELS_DIR, "*.tar.gz"))
                if models:
                    newest_model = max(models, key=os.path.getctime)
                    model_filename = os.path.basename(newest_model)
                    
                    print(f"New model created: {model_filename}")
                    
                    # Upload to MinIO
                    upload_success = upload_model_to_minio(newest_model)
                    
                    # Update MongoDB with model filename (BE expects filename not full URL)
                    mongo_update_success = None
                    if upload_success.get("success", False) and training_status.get("model_name"):
                        # BE wants filename only, not full URL
                        model_name = training_status.get("model_name")
                        mongo_update_success = update_model_url_in_mongo(model_name, model_filename, model_filename)
                    
                    # Update training status
                    training_status.update({
                        "is_training": False,
                        "status": "completed",
                        "model_file": model_filename,
                        "upload_success": upload_success,
                        "mongo_update": mongo_update_success,
                        "error_message": None
                    })
                else:
                    # No model found
                    training_status.update({
                        "is_training": False,
                        "status": "failed",
                        "error_message": "No model file generated after training"
                    })
                    print("Training completed but no model file found!")
                

                    
            else:
                # Training failed
                error_msg = f"Training failed with return code {process.returncode}"
                if stderr:
                    error_msg += f": {stderr}"
                
                training_status.update({
                    "is_training": False,
                    "status": "failed",
                    "error_message": error_msg
                })
                print(f"Error: {error_msg}")
                
        except Exception as e:
            error_msg = f"Training process error: {str(e)}"
            training_status.update({
                "is_training": False,
                "status": "failed",
                "error_message": error_msg
            })
            print(f"Error: {error_msg}")
    
    # Start training in background thread
    training_thread = threading.Thread(target=training_worker)
    training_thread.daemon = True
    training_thread.start()

# --- Quản lý process --- #

def kill_old_process(command: list):
    for proc in psutil.process_iter(PROCESS_ATTRIBUTES):
        try:
            cmdline_raw = proc.info.get('cmdline', [])
            if not isinstance(cmdline_raw, list) or not all(isinstance(arg, str) for arg in cmdline_raw):
                continue  # bỏ qua process không hợp lệ

            cmdline = " ".join(cmdline_raw)

            if all(arg.lower() in cmdline for arg in command):
                proc.kill()
                print(f"Killed process: {proc.pid}: {' '.join(command)}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

def start_new_process(command: list, working_dir="."):
    try:
        subprocess.Popen(
            command,
            cwd=working_dir,
            stdout=None,
            stderr=None
        )
        print(f"Started process: {' '.join(command)}")
    except Exception as e:
        print(f"Failed to start process: {e}")

# --- API: Chạy lệnh Rasa --- #
@app.route('/run-command', methods=['POST'])
def run_command():
    try:
        data = request.get_json()
        main = data.get("main", [])
        expand = data.get("expand", [])
        command = main + expand
        working_dir = data.get("working_dir", ".")

        if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
            return ApiResponse.bad_request("Invalid 'command'. Must be a list of strings.")

        # Thêm sys.executable vào đầu
        full_command = [sys.executable] + command

        # Kill nếu có
        kill_old_process(main)
        # Start lại
        start_new_process(full_command, working_dir)

        return ApiResponse.success(
            "Command started successfully",
            {
                "command": ' '.join(full_command),
                "working_dir": working_dir
            }
        )

    except Exception as e:
        traceback.print_exc()
        return ApiResponse.internal_error("Internal server error", {"error": str(e)})

# --- API: Chạy Rasa Server --- #
@app.route('/rasa-run', methods=['POST'])
def rasa_run():
    try:
        data = request.get_json() or {}
        
        # Main command cố định
        main = ["-m", "rasa", "run"]
        
        # Chỉ nhận expand từ input, mặc định như cũ
        expand = data.get("expand", ["--enable-api", "--cors", "*"])
        working_dir = data.get("working_dir", ".")
        
        # Ghép command
        command = main + expand
        
        if not isinstance(expand, list) or not all(isinstance(c, str) for c in expand):
            return ApiResponse.bad_request("Invalid 'expand' format. Must be a list of strings.")

        # Thêm sys.executable vào đầu
        full_command = [sys.executable] + command

        # Kill old Rasa processes
        kill_old_process(main)
        
        # Start new Rasa server
        start_new_process(full_command, working_dir)

        return ApiResponse.success(
            "Rasa server started successfully",
            {
                "command": ' '.join(full_command),
                "working_dir": working_dir,
                "main": main,
                "expand": expand
            }
        )

    except Exception as e:
        traceback.print_exc()
        return ApiResponse.internal_error("Rasa server start failed", {"error": str(e)})

# --- API: Chạy Actions Server --- #
@app.route('/run-actions', methods=['POST'])
def run_actions():
    try:
        # Xử lý JSON an toàn - không bị lỗi khi không có body
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}
        
        # Main command cố định cho actions server
        main = ["-m", "rasa", "run", "actions"]
        
        # Nhận expand từ input, mặc định trống
        expand = data.get("expand", [])
        working_dir = "."
        
        # Validate expand parameter
        if not isinstance(expand, list) or not all(isinstance(c, str) for c in expand):
            return ApiResponse.bad_request("Invalid 'expand' format. Must be a list of strings.")
        
        # Ghép command
        command = main + expand
        
        # Thêm sys.executable vào đầu
        full_command = [sys.executable] + command

        # Kill old Actions server processes
        kill_old_process(main)
        
        # Start new Actions server
        start_new_process(full_command, working_dir)

        return ApiResponse.success(
            "Actions server started successfully",
            {
                "command": ' '.join(full_command),
                "working_dir": working_dir,
                "main": main,
                "expand": expand,
                "port": "5055"
            }
        )

    except Exception as e:
        traceback.print_exc()
        return ApiResponse.internal_error("Actions server start failed", {"error": str(e)})

# --- API: Health Check --- #
@app.route('/health', methods=['GET'])
def health_check():
    try:
        import requests
        from datetime import datetime
        
        # Kiểm tra Rasa server status
        def check_rasa_status():
            try:
                # Kiểm tra Rasa server (port 5005)
                rasa_response = requests.get("http://localhost:5005/status", timeout=3)
                if rasa_response.status_code == 200:
                    rasa_data = rasa_response.json()
                    return {
                        "status": "running",
                        "model_file": rasa_data.get("model_file", "no model loaded"),
                    }
                else:
                    return {"status": "not_responding", "error": f"HTTP {rasa_response.status_code}"}
            except requests.exceptions.RequestException as e:
                return {"status": "offline", "error": str(e)}
        
        # Kiểm tra Rasa Actions server status  
        def check_rasa_actions_status():
            try:
                # Kiểm tra Actions server (port 5055) 
                actions_response = requests.get("http://localhost:5055/health", timeout=3)
                if actions_response.status_code == 200:
                    return {"status": "running"}
                else:
                    return {"status": "not_responding", "error": f"HTTP {actions_response.status_code}"}
            except requests.exceptions.RequestException as e:
                return {"status": "offline", "error": str(e)}
        
        # Lấy thông tin Rasa
        rasa_status = check_rasa_status()
        actions_status = check_rasa_actions_status()
        
        return ApiResponse.success(
            "Rasa health check completed",
            {
                "RasaServer": rasa_status,
                "ActionsServer": actions_status
            }
        )
        
    except Exception as e:
        return ApiResponse.internal_error("Rasa health check failed", {"error": str(e)})

# --- API: Lấy danh sách tên actions --- #
@app.route('/list-actions', methods=['GET'])
def get_action_names():
    try:
        if not os.path.exists(ACTIONS_FILE):
            return ApiResponse.success(
                "No actions file found",
                {"action_names": []}
            )

        with open(ACTIONS_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        # Tìm tất cả các return value trong method name()
        action_names = re.findall(r'def name\(self\) -> Text:\s*return\s*["\']([^"\']+)["\']', content)
        
        return ApiResponse.success(
            "Action names retrieved successfully",
            {
                "actions": action_names,
                "total": len(action_names)
            }
        )

    except Exception as e:
        return ApiResponse.internal_error("Internal server error", {"error": str(e)})

# --- API: Ghi đè toàn bộ actions.py với mảng actions --- #
@app.route('/push-actions', methods=['POST'])
def set_actions():
    try:
        data = request.get_json()
        if not data:
            return ApiResponse.bad_request("Invalid JSON data")
        
        actions = data.get("actions")

        if not isinstance(actions, list):
            return ApiResponse.bad_request("Missing or invalid 'actions' array")

        # Tạo nội dung file mới với imports cơ bản
        file_content = """from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher


"""

        # Thêm từng action class vào
        for i, action_code in enumerate(actions):
            if not isinstance(action_code, str) or not action_code.strip():
                return ApiResponse.bad_request(f"Action at index {i} is empty or invalid")
            
            # Dedent và clean code
            clean_code = textwrap.dedent(action_code).strip()
            
            # Kiểm tra có class definition không
            class_match = re.search(CLASS_DEFINITION_PATTERN, clean_code)
            if not class_match:
                return ApiResponse.bad_request(f"Action at index {i} has no valid class definition")
            
            # Thêm vào file content
            file_content += clean_code + "\n\n\n"

        # Ghi đè file actions.py
        with open(ACTIONS_FILE, "w", encoding="utf-8") as f:
            f.write(file_content)

        # Restart Rasa action server
        kill_old_process(["-m", "rasa", "run", "actions"])
        action_command = [sys.executable, "-m", "rasa", "run", "actions"]
        start_new_process(action_command, working_dir=os.path.dirname(ACTIONS_FILE))

        return ApiResponse.success(
            "Actions file updated and action server restarted successfully",
            {
                "total_actions": len(actions),
                "action_server_restarted": True
            }
        )

    except Exception as e:
        traceback.print_exc()
        return ApiResponse.internal_error("Internal server error", {"error": str(e)})


# --- API: Liệt kê models --- #
@app.route('/list-models', methods=['GET'])
def list_models():
    try:
        models = [
            f for f in os.listdir(MODELS_DIR)
            if os.path.isfile(os.path.join(MODELS_DIR, f)) and f.endswith(SUPPORTED_MODEL_EXTENSIONS)
        ]
        return ApiResponse.success(
            "Models listed successfully",
            {
                "models": models,
                "total": len(models)
            }
        )
    except Exception as e:
        return ApiResponse.internal_error("Internal server error", {"error": str(e)})


# --- API: Download Model from URL --- #
@app.route('/upload-model', methods=['POST'])
def upload_model():
    """Download model from URL to local models directory"""
    try:
        data = request.get_json()
        if not data:
            return ApiResponse.bad_request("Invalid JSON data")
        print("Received upload-model request:", data)
        
        # Get model URL from request
        model_url = data.get("url")
        if not isinstance(model_url, str) or not model_url.strip():
            return ApiResponse.bad_request("Missing or invalid 'url'")
        
        # Extract filename from URL
        import urllib.parse
        parsed_url = urllib.parse.urlparse(model_url)
        model_name = os.path.basename(parsed_url.path)
        print(f"Extracted filename: {model_name}")
        
        # Check if filename is valid and has supported extension
        is_valid_extension = any(model_name.endswith(ext) for ext in SUPPORTED_MODEL_EXTENSIONS)
        if not model_name or not is_valid_extension:
            print(f"Invalid filename: {model_name}, supported extensions: {SUPPORTED_MODEL_EXTENSIONS}")
            return ApiResponse.bad_request("Invalid model filename in URL")

        # Prepare local path
        local_path = os.path.join(MODELS_DIR, model_name)
        os.makedirs(MODELS_DIR, exist_ok=True)
        print(f"Target local path: {local_path}")
        
        # Check if file already exists locally
        if os.path.exists(local_path):
            print(f"File already exists: {local_path}")
            return ApiResponse.bad_request(f"Model '{model_name}' already exists locally")
        
        try:
            # Download file from URL
            import requests
            
            print(f"Downloading model from URL: {model_url}")
            
            response = requests.get(model_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Save file to local directory
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print(f"Downloaded: {model_name} from {model_url}")
            
            return ApiResponse.success("Model downloaded successfully", {
                "filename": model_name,
                "local_path": local_path,
                "source_url": model_url,
                "size": os.path.getsize(local_path)
            })
            
        except requests.RequestException as e:
            print(f"Failed to download from URL {model_url}: {e}")
            # Clean up partial file if exists
            if os.path.exists(local_path):
                os.remove(local_path)
            return ApiResponse.error(f"Download failed from URL", {
                "error": str(e),
                "url": model_url
            })
            
    except Exception as e:
        return ApiResponse.error("Failed to download model", {
            "error": str(e)
        })


# --- API: Chạy model cụ thể --- #
@app.route('/run-model', methods=['POST'])
def run_model():
    try:
        data = request.get_json()
        model_file = data.get("model")

        if not model_file or not model_file.endswith(SUPPORTED_MODEL_EXTENSIONS):
            return ApiResponse.bad_request("Invalid or missing model filename")

        model_path = os.path.join(MODELS_DIR, model_file)
        if not os.path.exists(model_path):
            return ApiResponse.not_found(f"Model file '{model_file}' not found")

        model_command = [sys.executable, "-m", "rasa", "run", "--model", model_path, "--enable-api", "--cors", "*"]

        kill_old_process(["-m", "rasa", "run"])  # Giết tất cả tiến trình `rasa run`
        start_new_process(model_command)

        return ApiResponse.success(
            f"Model '{model_file}' is now running",
            {
                "model_file": model_file,
                "model_path": model_path,
                "status": "running"
            }
        )
    except Exception as e:
        return ApiResponse.internal_error("Internal server error", {"error": str(e)})

# --- API: Train Rasa Model --- #
@app.route('/train', methods=['POST'])
def train_rasa_model():
    try:
        data = request.get_json()
        
        if not data:
            return ApiResponse.bad_request("Invalid JSON data")
        
        print("Starting Rasa training process...")
        
        # Extract data từ request
        model_name = data.get("modelName")  # Model name từ BE (unique, theo thời gian)
        firetune = data.get("firetune", False)
        actions = data.get("actions", [])  # List các action code
        nlu_yaml = data.get("nlu", "")
        stories_yaml = data.get("stories", "")
        rules_yaml = data.get("rules", "")
        domain_yaml = data.get("domain", "")
        
        # Validate required fields
        if not all([nlu_yaml, stories_yaml, domain_yaml]):
            return ApiResponse.bad_request("Missing required fields: nlu, stories, or domain")
        
        if not model_name:
            return ApiResponse.bad_request("Missing required field: modelName")
        
        # Check if training is already in progress
        global training_status
        if training_status["is_training"]:
            elapsed_time = time.time() - training_status["start_time"] if training_status["start_time"] else 0
            return ApiResponse.bad_request(
                "Training is already in progress", 
                {
                    "current_status": training_status["status"],
                    "elapsed_time": elapsed_time,
                    "elapsed_time_formatted": f"{int(elapsed_time//60)}m {int(elapsed_time%60)}s",
                    "message": "Please wait for current training to complete or check /training-status"
                }
            )
        
        # Tạo các file YAML
        files_created = []
        
        try:
            # 1. Tạo file nlu.yml
            nlu_path = os.path.join("data", "nlu.yml")
            os.makedirs(os.path.dirname(nlu_path), exist_ok=True)
            with open(nlu_path, "w", encoding="utf-8") as f:
                f.write(nlu_yaml)
            files_created.append(nlu_path)
            
            # 2. Tạo file stories.yml
            stories_path = os.path.join("data", "stories.yml")
            with open(stories_path, "w", encoding="utf-8") as f:
                f.write(stories_yaml)
            files_created.append(stories_path)
            
            # 3. Tạo file rules.yml (nếu có)
            if rules_yaml.strip():
                rules_path = os.path.join("data", "rules.yml")
                with open(rules_path, "w", encoding="utf-8") as f:
                    f.write(rules_yaml)
                files_created.append(rules_path)
            
            # 4. Tạo file domain.yml
            domain_path = "domain.yml"
            with open(domain_path, "w", encoding="utf-8") as f:
                f.write(domain_yaml)
            files_created.append(domain_path)
            
            # 5. Cập nhật actions.py nếu có
            if actions and len(actions) > 0:
                # Tạo nội dung file actions.py mới
                file_content = """from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher


"""
                for i, action_code in enumerate(actions):
                    if isinstance(action_code, str) and action_code.strip():
                        clean_code = textwrap.dedent(action_code).strip()
                        file_content += clean_code + "\n\n\n"
                
                # Ghi file actions.py
                with open(ACTIONS_FILE, "w", encoding="utf-8") as f:
                    f.write(file_content)
                files_created.append(ACTIONS_FILE)
                
                # Restart actions server
                print("Restarting actions server...")
                kill_old_process(["-m", "rasa", "run", "actions"])
                action_command = [sys.executable, "-m", "rasa", "run", "actions"]
                start_new_process(action_command, working_dir=".")
            
            # 6. Chạy lệnh train với monitoring
            train_command = [sys.executable, "-m", "rasa", "train"]
            if firetune:
                train_command.extend(["--finetune"])
                print("Training with finetune mode")
            
            # Set training status
            training_status.update({
                "is_training": True,
                "start_time": time.time(),
                "status": "training",
                "model_file": None,
                "model_name": model_name,  # Store model name for later use
                "error_message": None
            })
            
            # Start training with monitoring
            print(f"Training files prepared. Starting training process...")
            run_training_with_monitoring(train_command, working_dir=".")
            
            return ApiResponse.success(
                "Training started successfully",
                {
                    "firetune": firetune,
                    "files_created": files_created,
                    "actions_count": len(actions),
                    "train_command": ' '.join(train_command),
                    "status": "training_in_progress",
                    "message": "Training process has been started. Check models directory for completed model."
                }
            )
            
        except IOError as e:
            return ApiResponse.internal_error(f"File creation failed: {str(e)}")
            
    except Exception as e:
        print(f"ERROR in train API: {e}")
        return ApiResponse.internal_error("Training failed", {"error": str(e)})

# --- API: Training Status --- #
@app.route('/training-status', methods=['GET'])
def get_training_status():
    """API để BE check training status"""
    global training_status
    
    # Calculate elapsed time
    elapsed_time = None
    if training_status["start_time"]:
        elapsed_time = time.time() - training_status["start_time"]
    
    return ApiResponse.success(
        "Training status retrieved successfully",
        {
            "is_training": training_status["is_training"],
            "status": training_status["status"],  # idle, training, completed, failed
            "start_time": training_status["start_time"],
            "model_file": training_status["model_file"],
            "model_name": training_status.get("model_name"),
            "elapsed_time": elapsed_time,
            "elapsed_time_formatted": f"{int(elapsed_time//60)}m {int(elapsed_time%60)}s" if elapsed_time else None,
            "error_message": training_status.get("error_message"),
            "upload_success": training_status.get("upload_success"),
            "mongo_update": training_status.get("mongo_update")
        }
    )

# --- API: Stop Training --- #
@app.route('/stop-training', methods=['POST'])
def stop_training():
    """Force stop current training process"""
    try:
        global training_status
        
        # Check if training is running
        if not training_status["is_training"]:
            return ApiResponse.bad_request("No training process is currently running")
        
        # Kill all rasa train processes using existing function
        kill_old_process(["-m", "rasa", "train"])
        
        # Reset training status
        training_status.update({
            "is_training": False,
            "status": "stopped",
            "error_message": "Training was manually stopped"
        })
        
        print("🛑 Training process manually stopped")
        
        return ApiResponse.success("Training stopped successfully", {
            "message": "All RASA training processes have been terminated",
            "new_status": "stopped"
        })
        
    except Exception as e:
        return ApiResponse.error("Failed to stop training", {
            "error": str(e)
        })

# --- API: List Models on MinIO --- #
@app.route('/minio-models', methods=['GET'])
def list_minio_models():
    """List all models stored in MinIO bucket"""
    try:
        if not MINIO_AVAILABLE:
            return ApiResponse.error("MinIO library not available")
        
        # Create MinIO client
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        
        # Check if bucket exists
        if not minio_client.bucket_exists(MINIO_BUCKET):
            return ApiResponse.success("No models found", {
                "bucket": MINIO_BUCKET,
                "bucket_exists": False,
                "models": []
            })
        
        # List objects in bucket
        objects = minio_client.list_objects(MINIO_BUCKET)
        models = []
        
        for obj in objects:
            models.append({
                "filename": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat(),
                "etag": obj.etag,
                "url": f"http://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{obj.object_name}"
            })
        
        return ApiResponse.success("Models retrieved successfully", {
            "bucket": MINIO_BUCKET,
            "bucket_exists": True,
            "total_models": len(models),
            "models": models
        })
        
    except Exception as e:
        return ApiResponse.error("Failed to list MinIO models", {
            "error": str(e)
        })

# --- Chạy Flask app --- #
if __name__ == '__main__':
    print("Starting Flask API server...")
    print("=" * 50)
    
    # Check MinIO connection on startup
    check_minio_connection_on_startup()
    
    # Check MongoDB connection on startup
    check_mongo_connection_on_startup()
    
    print("=" * 50)
    print("Flask API running on http://localhost:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=DEBUG_MODE, use_reloader=USE_RELOADER)
