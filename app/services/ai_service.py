import json
import os
import random
from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.models import QuestionTemplate

load_dotenv()

# Setup Client
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=GOOGLE_API_KEY)
MODEL_ID = "gemini-flash-latest"

# Rentang angka berdasarkan level kesulitan agar tiap soal punya angka variatif
_NUMBER_RANGES = {
    1: {"min": 1, "max": 50, "desc": "bilangan bulat kecil (1-50)"},
    2: {"min": 10, "max": 500, "desc": "bilangan bulat menengah (10-500), boleh desimal sederhana"},
    3: {"min": 50, "max": 10000, "desc": "bilangan besar (50-10000), boleh pecahan atau desimal"},
}

def _generate_random_seed_numbers(difficulty: int) -> str:
    """Buat 4 angka acak sebagai seed agar AI pakai angka berbeda tiap panggilan."""
    cfg = _NUMBER_RANGES.get(difficulty, _NUMBER_RANGES[3])
    nums = [random.randint(cfg["min"], cfg["max"]) for _ in range(4)]
    return ", ".join(str(n) for n in nums)


def generate_soal_with_ai(template: QuestionTemplate) -> dict:
    """
    Mengirim template ke AI dan menerima JSON soal baru.
    """
    
    # 1. Terjemahkan Level Angka ke Bahasa Manusia
    level_map = {
        1: "Mudah / Dasar (Pemahaman Konsep)",
        2: "Sedang / Menengah (Aplikasi Rumus)",
        3: "Sulit / Kompleks (Analisis / HOTS)"
    }
    level_context = level_map.get(template.difficulty, "Sangat Sulit")

    # 2. Generate angka acak sebagai seed variasi
    num_cfg = _NUMBER_RANGES.get(template.difficulty, _NUMBER_RANGES[3])
    seed_numbers = _generate_random_seed_numbers(template.difficulty)

    # 3. Prompt Engineering
    prompt = f"""
    Kamu adalah Guru Matematika SMP profesional yang menyusun soal ujian berstandar akademik.
    Tugas: Buat 1 variasi soal baru berdasarkan template berikut.
    
    DATA TEMPLATE:
    - Topik: {template.topic}
    - Level Difficulty: {template.difficulty} ({level_context})
    - Soal Asli: "{template.question_text}"
    
    ANGKA ACAK REFERENSI: {seed_numbers}
    Rentang angka yang sesuai level ini: {num_cfg["desc"]}
    
    INSTRUKSI WAJIB:
    1. Buat soal baru yang SETARA dengan Level {template.difficulty}.
    2. GUNAKAN angka-angka yang BERBEDA dari soal asli. Manfaatkan angka acak referensi di atas sebagai inspirasi, atau buat angka baru sendiri dalam rentang yang sesuai. JANGAN menggunakan angka yang sama dengan soal asli.
    3. Ubah konteks cerita/narasi soal agar berbeda dari soal asli, namun tetap realistis dan relevan dengan kehidupan sehari-hari.
    4. Gunakan bahasa Indonesia baku yang jelas dan formal, sesuai standar soal ujian akademik. JANGAN menggunakan humor, lelucon, atau punchline.
    5. Pastikan logika penyelesaian dan tingkat kesulitan tetap setara dengan soal asli.
    6. Pastikan tepat 1 jawaban benar dan 3 pengecoh (distractor) yang masuk akal.
    7. Output WAJIB JSON murni.
    8. Field 'difficulty' HARUS berupa ANGKA integer ({template.difficulty}), JANGAN string.
    
    FORMAT JSON RESPONSE PERSIS TANPA TAMBAHAN SYNTAX MARKDOWN SEPERTI ```json:
    {{
        "topic": "{template.topic}",
        "difficulty": {template.difficulty},
        "question_text": "Tulis narasi soal barumu di sini...",
        "answers": [
            {{ "label": "A", "text": "...", "is_correct": false }},
            {{ "label": "B", "text": "...", "is_correct": true }},
            {{ "label": "C", "text": "...", "is_correct": false }},
            {{ "label": "D", "text": "...", "is_correct": false }}
        ]
    }}
    """

    try:
        # Panggil Google Gemini
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        if response.text:
            ai_json = json.loads(response.text)
            
            # Info monitoring token
            usage = response.usage_metadata
            total_tok = usage.total_token_count if usage else 0
            ai_json["meta_info"] = f"Model: {MODEL_ID} | Level: {template.difficulty} | Token Used: {total_tok}"
            
            print(f"AI Response: {response.text}")
            return ai_json
        else:
            raise Exception("Response AI kosong")
    
    except Exception as e:
        print(f"Error AI Service: {e}")
        # Return object darurat biar server gak crash
        return {
            "topic": template.topic,
            "difficulty": template.difficulty,
            "question_text": f"DEBUG ERROR: {str(e)}",
            "answers": [],
            "meta_info": f"Error System: {str(e)}"
        }