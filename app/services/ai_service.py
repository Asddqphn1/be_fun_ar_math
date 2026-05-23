import json
import logging
import os
import random
from typing import Any, Dict, Iterator, List, Tuple
from dotenv import load_dotenv
from fastapi import HTTPException
from app.models import QuestionTemplate
from app.schemas.soal_generated import BatchQuestionsGenerated

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
_bulk_model = None

def _get_model():
    """Lazy init LangChain model — hemat RAM saat startup."""
    global _model
    if _model is None:
        logger.info("Initializing LangChain model (first call)...")
        from langchain.chat_models import init_chat_model
        _model = init_chat_model(
            model=os.getenv("MODEL_NAME"),
            model_provider="openai",
            base_url=os.getenv("AI_BASE_URL"),
            api_key=OPENROUTER_API_KEY,
            model_kwargs={
                "response_format": { "type": "json_object" },
                "max_tokens": 2500
            }
        )
    return _model


def _get_bulk_model():
    """Lazy init model for large bulk generation responses."""
    global _bulk_model
    if _bulk_model is None:
        logger.info("Initializing LangChain bulk model (first call)...")
        from langchain.chat_models import init_chat_model
        max_tokens = int(os.getenv("BULK_MAX_TOKENS", "64000"))
        _bulk_model = init_chat_model(
            model=os.getenv("MODEL_NAME"),
            model_provider="openai",
            base_url=os.getenv("AI_BASE_URL"),
            api_key=OPENROUTER_API_KEY,
            model_kwargs={
                "response_format": {"type": "json_object"},
                "max_tokens": max_tokens,
            },
        )
    return _bulk_model

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




def generate_soal_with_ai(template: QuestionTemplate) -> BatchQuestionsGenerated:
    """
    Mengirim template ke AI dan menerima JSON 3 soal baru.
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
    Tugas: Buat TEPAT 3 variasi soal baru berdasarkan template berikut.
    
    DATA TEMPLATE:
    - Topik: {template.topic}
    - Level Difficulty: {template.difficulty} ({level_context})
    - Soal Asli: "{template.question_text}"
    
    ANGKA ACAK REFERENSI: {seed_numbers}
    Rentang angka yang sesuai level ini: {num_cfg["desc"]}
    
    INSTRUKSI WAJIB:
    1. Buat 3 soal baru yang SETARA dengan Level {template.difficulty}.
    2. GUNAKAN angka-angka yang BERBEDA dari soal asli. Manfaatkan angka acak referensi di atas sebagai inspirasi, atau buat angka baru sendiri dalam rentang yang sesuai.
    3. Ubah konteks cerita/narasi setiap soal agar berbeda dari soal asli dan satu sama lain, namun tetap realistis.
    4. Gunakan bahasa Indonesia baku yang jelas dan formal.
    5. Pastikan logika penyelesaian dan tingkat kesulitan tetap setara dengan soal asli.
    6. Pastikan setiap soal memiliki tepat 1 jawaban benar dan 3 pengecoh (distractor).
    7. Output WAJIB JSON murni sesuai skema.
    
    FORMAT JSON RESPONSE PERSIS TANPA TAMBAHAN SYNTAX MARKDOWN SEPERTI ```json:
    {{
        "questions": [
            {{
                "question_text": "Tulis narasi soal variasi ke-1 di sini...",
                "answers": [
                    {{ "label": "A", "text": "...", "is_correct": false }},
                    {{ "label": "B", "text": "...", "is_correct": true }},
                    {{ "label": "C", "text": "...", "is_correct": false }},
                    {{ "label": "D", "text": "...", "is_correct": false }}
                ]
            }},
            {{
                "question_text": "Tulis narasi soal variasi ke-2 di sini...",
                "answers": [ ... ]
            }},
            {{
                "question_text": "Tulis narasi soal variasi ke-3 di sini...",
                "answers": [ ... ]
            }}
        ]
    }}
    """

    try:
        model = _get_model().with_structured_output(BatchQuestionsGenerated, method="json_mode")
        response = model.invoke(prompt)
        return response
        
    except Exception as e:
        # Pengecekan fallback manual jika json_mode gagal di parsing
        logger.error(f"Structured output failed. Fallback to manual parsing. Error: {e}")
        try:
            raw_response = _get_model().invoke(prompt)
            clean_soal = raw_response.content.replace("```json", "").replace("```", "").strip()
            soal_json = json.loads(clean_soal)
            return BatchQuestionsGenerated(**soal_json)
        except Exception as fallback_e:
            logger.error(f"Error AI Service: {fallback_e}", exc_info=True)
            raise HTTPException(
                status_code=502,
                detail=f"Koneksi ke layanan AI gagal atau format tidak sesuai: {str(fallback_e)}"
            )


def generate_bulk_soal_with_ai(
    template: QuestionTemplate,
    total_questions: int = 100,
) -> List[Dict[str, Any]]:
    """Mengirim template ke AI dan menerima JSON banyak soal sekaligus."""
    if total_questions <= 0:
        raise ValueError("total_questions harus lebih dari 0")

    level_map = {
        1: "Mudah / Dasar (Pemahaman Konsep)",
        2: "Sedang / Menengah (Aplikasi Rumus)",
        3: "Sulit / Kompleks (Analisis / HOTS)",
    }
    level_context = level_map.get(template.difficulty, "Sangat Sulit")

    num_cfg = _NUMBER_RANGES.get(template.difficulty, _NUMBER_RANGES[3])
    seed_numbers = _generate_random_seed_numbers(template.difficulty)

    prompt = f"""
    Kamu adalah Guru Matematika SMP profesional yang menyusun soal ujian berstandar akademik.
    Tugas: Buat TEPAT {total_questions} variasi soal baru berdasarkan template berikut.

    DATA TEMPLATE:
    - Topik: {template.topic}
    - Level Difficulty: {template.difficulty} ({level_context})
    - Soal Asli: "{template.question_text}"

    ANGKA ACAK REFERENSI: {seed_numbers}
    Rentang angka yang sesuai level ini: {num_cfg["desc"]}

    INSTRUKSI WAJIB:
    1. Buat {total_questions} soal baru yang SETARA dengan Level {template.difficulty}.
    2. GUNAKAN angka-angka yang BERBEDA dari soal asli. Manfaatkan angka acak referensi di atas sebagai inspirasi, atau buat angka baru sendiri dalam rentang yang sesuai.
    3. Ubah konteks cerita/narasi setiap soal agar berbeda dari soal asli dan satu sama lain, namun tetap realistis.
    4. Gunakan bahasa Indonesia baku yang jelas dan formal.
    5. Pastikan logika penyelesaian dan tingkat kesulitan tetap setara dengan soal asli.
    6. Pastikan setiap soal memiliki tepat 1 jawaban benar dan 3 pengecoh (distractor).
    7. Output WAJIB JSON murni sesuai skema dan TANPA markdown.

    FORMAT JSON RESPONSE PERSIS:
    {{
        "questions": [
            {{
                "question_text": "Tulis narasi soal variasi di sini...",
                "answers": [
                    {{ "label": "A", "text": "...", "is_correct": false }},
                    {{ "label": "B", "text": "...", "is_correct": true }},
                    {{ "label": "C", "text": "...", "is_correct": false }},
                    {{ "label": "D", "text": "...", "is_correct": false }}
                ]
            }}
        ]
    }}
    """

    try:
        raw_response = _get_bulk_model().invoke(prompt)
        payload = _safe_json_load(raw_response.content)
        questions = _normalize_bulk_questions(payload, total_questions)
        if not questions:
            raise HTTPException(
                status_code=502,
                detail="AI tidak mengembalikan daftar soal dengan benar.",
            )
        return questions
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error AI Service (bulk): {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Koneksi ke layanan AI gagal atau format tidak sesuai: {str(e)}",
        )


def _safe_json_load(content: str) -> Dict[str, Any]:
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.replace("```json", "").replace("```", "").strip()

    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1:
        clean = clean[start : end + 1]

    return json.loads(clean)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return False


def _normalize_bulk_questions(payload: Dict[str, Any], max_questions: int) -> List[Dict[str, Any]]:
    questions = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(questions, list):
        return []

    normalized: List[Dict[str, Any]] = []
    dropped = 0

    for item in questions:
        if not isinstance(item, dict):
            dropped += 1
            continue

        question_text = item.get("question_text") or item.get("question")
        if not question_text:
            dropped += 1
            continue

        answers_raw = item.get("answers")
        if not isinstance(answers_raw, list):
            dropped += 1
            continue

        answers: List[Dict[str, Any]] = []
        for ans in answers_raw:
            if not isinstance(ans, dict):
                continue
            is_correct = ans.get("is_correct", ans.get("isorrect"))
            text = ans.get("text") or ans.get("option_text")
            if text is None or is_correct is None:
                continue
            answers.append({"text": str(text), "is_correct": _to_bool(is_correct)})

        if len(answers) < 4:
            dropped += 1
            continue

        correct_indices = [i for i, a in enumerate(answers) if a["is_correct"]]
        if len(correct_indices) == 0:
            dropped += 1
            continue
        if len(correct_indices) > 1:
            first = correct_indices[0]
            for idx in correct_indices[1:]:
                answers[idx]["is_correct"] = False

        normalized.append(
            {
                "question_text": str(question_text).strip(),
                "answers": answers[:4],
            }
        )

        if len(normalized) >= max_questions:
            break

    if dropped:
        logger.warning("Bulk normalize dropped %s invalid questions", dropped)

    return normalized


def iter_generate_bulk_questions(
    templates: List[QuestionTemplate],
    total_questions: int = 100,
    batch_size: int = 3,
) -> Iterator[Tuple[QuestionTemplate, BatchQuestionsGenerated, int]]:
    """Iterasi batch soal AI untuk kebutuhan streaming (total default 180)."""
    if not templates:
        raise ValueError("Daftar template kosong")
    if total_questions <= 0:
        raise ValueError("total_questions harus lebih dari 0")
    if batch_size <= 0:
        raise ValueError("batch_size harus lebih dari 0")

    full_batches, remainder = divmod(total_questions, batch_size)
    total_batches = full_batches + (1 if remainder else 0)

    for idx in range(total_batches):
        selected_template = random.choice(templates)
        expected_count = batch_size if idx < full_batches else remainder or batch_size
        yield selected_template, generate_soal_with_ai(selected_template), expected_count