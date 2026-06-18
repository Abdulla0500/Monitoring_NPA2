import os
from dotenv import load_dotenv
load_dotenv()
class Config:
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', '127.0.0.1'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME', 'monitoring_db'),
        'user': os.getenv('DB_USER', 'Abdulla'),
        'password': os.getenv('DB_PASSWORD', '12332144'),
    }
    
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

config1 = Config()