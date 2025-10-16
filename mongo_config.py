# MongoDB Configuration
import os

# Use environment variables if available, otherwise fall back to defaults
MONGO_USERNAME = os.getenv("MONGO_USERNAME", "horob1")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "ILUKn5cnbaOhYOva")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "base_be")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://horob1:ILUKn5cnbaOhYOva@cluster0.ok7ukdo.mongodb.net/base_be")

# Collection name for models
MODELS_COLLECTION = os.getenv("MODELS_COLLECTION", "mymodels")  # Có thể thay đổi theo tên collection của BE
