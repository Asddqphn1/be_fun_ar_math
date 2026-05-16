import json
import logging
import os
import random
from dotenv import load_dotenv
from fastapi import HTTPException
from app.models import QuestionTemplate

load_dotenv()

logger = logging.getLogger(__name__)

# Setup Client
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ============================================
# LAZY MODEL: Jangan init langchain saat import
# Init hanya saat generate_soal_with_ai() dipanggil
# Ini menghemat ~200MB RAM saat startup!
# ============================================
_model = None

def _get_model():
    """Lazy init LangChain model — hemat RAM saat startup."""
    global _model
    if _model is None:
        logger.info("Initializing LangChain model (first call)...")
        from langchain.chat_models import init_chat_model
        _model = init_chat_model(
            model="minimax/MiniMax-M2.7",
            model_provider="openai",
            base_url="https://9router.ruanjitech.com/v1",
            api_key=OPENROUTER_API_KEY,
            model_kwargs={
                "response_format": { "type": "json_object" }
            }
        )
    return _model

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
        response = _get_model().invoke(prompt)
        soal_baru = response.content.strip()

        clean_soal = soal_baru.replace("```json", "").replace("```", "").strip()
        logger.debug(f"Raw AI Response: {soal_baru}")
        logger.debug(f"Cleaned AI Response: {clean_soal}")
        soal_json = json.loads(clean_soal)
        return soal_json
        
    except json.JSONDecodeError as e:
        # Menangani kasus jika AI nge-halu dan return teks biasa, bukan JSON
        logger.error(f"Error Parsing JSON dari AI: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Gagal memproses format soal dari AI. Silakan coba lagi."
        )
    
    except Exception as e:
        # Menangani error dari provider AI (seperti 403 Forbidden, timeout, limit habis, dll)
        logger.error(f"Error AI Service: {e}", exc_info=True)
        raise HTTPException(
            status_code=502, # 502 Bad Gateway lebih cocok untuk error dari third-party API
            detail=f"Koneksi ke layanan AI gagal: {str(e)}"
        )