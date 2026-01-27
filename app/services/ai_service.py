import json
import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from os import getenv

from app.models import QuestionTemplate

load_dotenv()

# Setup Client
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

model = init_chat_model(
    model="xiaomi/mimo-v2-flash:free",
    model_provider="openai",
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": getenv("YOUR_SITE_URL"),
        "X-Title": getenv("YOUR_SITE_NAME"),
    }
)

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
    2. Ubah angka dan cerita lebih natural dan lucu ada punchlinenya, tapi logika penyelesaian tetap setara.
    3. Output WAJIB JSON murni.
    4. Field 'difficulty' HARUS berupa ANGKA integer ({template.difficulty}), JANGAN string.
    
    FORMAT JSON RESPONSE PERSIS TANPA TAMBAHAN SYNTAX MARKDOWN SEPERTI ```json:
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
        response = model.invoke(prompt)
        ai_text = response.content.strip()

        cleaned_text = ai_text.replace("```json", "").replace("```", "").strip()
        print(f"AI Response: {ai_text}")
        ai_json = json.loads(cleaned_text)
        return ai_json
    
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