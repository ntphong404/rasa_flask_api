"""
Configuration constants for Flask API
"""
import os

# File paths
ACTIONS_FILE = "actions/actions.py"
MODELS_DIR = "models"

# Supported model file extensions
SUPPORTED_MODEL_EXTENSIONS = (".tar.gz", ".tar.zip")

# Process management
PROCESS_ATTRIBUTES = ['pid', 'name', 'cmdline']

# Regex patterns
CLASS_DEFINITION_PATTERN = r'class\s+(\w+)\s*\('
ACTION_CLASS_PATTERN = r'class\s+(\w+)\s*\(.*Action.*\):'

# Flask app configuration
DEBUG_MODE = True
USE_RELOADER = False

# Ensure required directories exist
os.makedirs(MODELS_DIR, exist_ok=True)
