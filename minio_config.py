# MinIO Configuration
import os

# Use environment variables if available, otherwise fall back to defaults
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_strong_minio_password_here")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "103.101.163.198:9000")
MINIO_HOST = os.getenv("MINIO_HOST", "103.101.163.198")
MINIO_PORT = int(os.getenv("MINIO_PORT", "9000"))
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "model")  # Bucket name for storing models
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"  # Set to True for HTTPS
