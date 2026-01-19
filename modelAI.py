import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("❌ API Key tidak ditemukan di file .env!")
    exit()

print("🔍 Sedang mengecek daftar model yang tersedia untuk akunmu...")
try:
    client = genai.Client(api_key=api_key)
    
    # Ambil semua list model
    # Di library baru, client.models.list() mengembalikan generator
    for model in client.models.list():
        # Cek apakah model mendukung 'generateContent'
        # Perhatikan: Atributnya sekarang 'supported_actions', bukan 'supported_generation_methods'
        if model.supported_actions and "generateContent" in model.supported_actions:
            # Kita ambil display_name juga biar jelas
            print(f"✅ {model.name} ({model.display_name})")
            
except Exception as e:
    print(f"❌ Error ngecek model: {e}")
    # Tips debugging: Print error lengkap
    import traceback
    traceback.print_exc()