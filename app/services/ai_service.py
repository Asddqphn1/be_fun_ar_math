import json
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from app.models import QuestionTemplate

load_dotenv()

# Setup Client
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)
MODEL_ID = "gemini-flash-latest"

def generate_soal_with_ai(template: QuestionTemplate) -> dict:
    """
    Mengirim template ke Gemini dan menerima JSON soal baru.
    Versi: Pure SDK (Tanpa LangChain).
    """
    
    # 1. Terjemahkan Level Angka ke Bahasa Manusia (Biar AI paham konteks)
    level_map = {
        1: "Mudah / Dasar (Pemahaman Konsep)",
        2: "Sedang / Menengah (Aplikasi Rumus)",
        3: "Sulit / Kompleks (Analisis / HOTS)"
    }
    # Kalau ada level 4 dst, default ke 'Sangat Sulit'
    level_context = level_map.get(template.difficulty, "Sangat Sulit")

    # 2. Prompt Engineering
    prompt = f"""
    Kamu adalah Guru Matematika SMP Adaptif.
    Tugas: Buat 1 variasi soal baru berdasarkan template ini.
    
    DATA TEMPLATE:
    - Topik: {template.topic}
    - Level Difficulty: {template.difficulty} ({level_context})
    - Soal Asli: "{template.question_text}"
    
    INSTRUKSI:
    1. Buat soal baru yang setara dengan Level {template.difficulty}.
    2. Ubah angka dan cerita, tapi logika penyelesaian tetap setara.
    3. Output WAJIB JSON murni.
    4. Field 'difficulty' HARUS berupa ANGKA integer ({template.difficulty}), JANGAN string.
    
    FORMAT JSON RESPONSE:
    {{
        "topic": "{template.topic}",
        "difficulty": {template.difficulty},
        "question_text": "Tulis narasi soal barumu disini...",
        "answers": [
            {{ "label": "A", "text": "...", "is_correct": false }},
            {{ "label": "B", "text": "...", "is_correct": true }},
            {{ "label": "C", "text": "...", "is_correct": false }},
            {{ "label": "D", "text": "...", "is_correct": false }}
        ]
    }}
    """

    try:
        # 3. Panggil Google Gemini
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        if response.text:
            result = json.loads(response.text)
            
            # 4. Tambahkan Info Token (Fitur Monitoring)
            usage = response.usage_metadata
            total_tok = usage.total_token_count if usage else 0
            
            # Kita selipkan info teknis ini untuk debugging/log
            result["meta_info"] = f"Model: {MODEL_ID} | Level: {template.difficulty} | Token Used: {total_tok}"
            
            return result
        else:
            raise Exception("Response AI kosong")

    except Exception as e:
        print(f"Error AI Service: {e}")
        # Return object darurat biar server gak crash
        return {
            "topic": template.topic,
            "difficulty": template.difficulty,
            "question_text": "Maaf, AI gagal generate soal saat ini.",
            "answers": [],
            "meta_info": f"Error System: {str(e)}"
        }