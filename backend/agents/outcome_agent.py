"""
FarmAI — OutcomeAgent
Assembles the final farmer-facing response from all agent outputs.
All farmer-visible text is in Pakistani Urdu script.
"""

import time
from utils.constants import DEFAULT_BUDGET_LIMIT_PKR, MANGO_ALTERNATIVE_COST_PKR
from services.logging_service import create_log, collect_logs, measure_latency_ms
from services.gemini_service import generate_gemini_farmer_response, generate_safe_tts_summary
from services.rag_service import detect_rag_crop, retrieve_chunks, format_rag_context, build_rag_status


from utils.helpers import get_weather_instruction

# ── Crop-specific Urdu fallback data ──────────────────────────────────
_FALLBACK_CROP_DATA = {
    "Cotton": {
        "problem": "کپاس کے پتوں کے مڑنے یا پیلے ہونے کا مسئلہ (لیف کرل وائرس/فلائی سٹریس)",
        "risk": "درمیانہ — پتے مڑنے اور پیلے ہونے سے پودے کی بڑھوتری اور خوراک بنانے کی صلاحیت متاثر ہو سکتی ہے۔",
        "actions": [
            "متاثرہ پتوں کا باریک بینی سے جائزہ لیں۔",
            "سفید مکھی یا سست تیلے کا حملہ چیک کریں اور تصدیق کے بغیر سپرے نہ کریں۔",
            "کیڑوں کی موجودگی کی صورت میں فوری مقامی زرعی ماہر سے مشورہ لیں۔"
        ],
        "next_step": "فصل کے متاثرہ حصے کی مزید صاف اور قریبی تصویر بھیجیں یا مقامی زرعی ماہر سے تصدیق کرائیں۔"
    },
    "Wheat": {
        "problem": "گندم میں زرد زنگ (پیلی کنگی) کا حملہ",
        "risk": "درمیانہ — زرد زنگ کی فنگس تیزی سے پھیل کر پیداوار کو شدید نقصان پہنچا سکتی ہے۔",
        "actions": [
            "متاثرہ پتوں کا قریب سے معائنہ کر کے نارنجی/زرد پاؤڈر جیسے نشانات دیکھیں۔",
            "بیماری پھیلنے کی صورت میں علاج یا اسپرے میں ہرگز تاخیر نہ کریں۔",
            "زرعی ماہر کے مشورے سے موزوں فنگس کش دوا کے استعمال کی تصدیق کریں۔"
        ],
        "next_step": "مقامی زرعی ماہر سے مشورہ کر کے ۲۴ سے ۴۸ گھنٹے کے اندر تصدیق کریں۔"
    },
    "Mango": {
        "problem": "آم کے پتوں پر سیاہ دھبے یعنی اینتھراکنوز کی بیماری",
        "risk": "درمیانہ — اینتھراکنوز نمی یا بارش کی وجہ سے پتوں اور پھلوں میں پھیل سکتا ہے۔",
        "actions": [
            "متاثرہ پتوں اور شاخوں کو کاٹ کر باغ سے دور کر دیں تاکہ بیماری نہ پھیلے۔",
            "باغ کو صاف اور ہوا دار رکھیں تاکہ نمی زیادہ دیر برقرار نہ رہے۔",
            "مناسب فنگس کش دوا کے استعمال کے لیے اپنے مقامی زرعی ماہر سے رابطہ کریں۔"
        ],
        "next_step": "بارش کے دوران سپرے سے مکمل پرہیز کریں اور مقامی زرعی ماہر سے مشورہ لیں۔"
    },
    "Unknown": {
        "problem": "فصل کا مسئلہ مکمل طور پر واضح نہیں ہے",
        "risk": "کم — درست تشخیص کے بغیر خطرے کا اندازہ ممکن نہیں۔",
        "actions": [
            "براہ کرم اپنی فصل کا نام لکھ کر بھیجیں۔",
            "متاثرہ حصے (پتے، پھل، تنا یا جڑ) کی تفصیل بتائیں۔",
            "اپنے علاقے کی موجودہ موسمی صورتحال سے آگاہ کریں۔"
        ],
        "next_step": "فصل کی قریبی اور واضح تصویر بھیجیں تاکہ زرعی ماہرین بہتر رہنمائی کر سکیں۔"
    }
}

_FALLBACK_RESPONSE = (
    "ممکنہ مسئلہ:\n"
    "فصل کا مسئلہ مکمل طور پر واضح نہیں ہے\n\n"
    "خطرے کی سطح:\n"
    "کم — معلومات کی کمی کی وجہ سے فوری تشخیص ممکن نہیں۔\n\n"
    "تجویز کردہ عمل:\n"
    "1. براہ کرم اپنی فصل کا نام لکھ کر بھیجیں۔\n"
    "2. متاثرہ حصے (پتے، پھل، تنا یا جڑ) کی تفصیل بتائیں۔\n"
    "3. اپنے علاقے کی موجودہ موسمی صورتحال سے آگاہ کریں۔\n\n"
    "موسم کا خیال:\n"
    "موسم کی معلومات دستیاب نہیں، اس لیے سپرے سے پہلے مقامی موسم ضرور چیک کریں۔\n\n"
    "اگلا قدم:\n"
    "فصل کی قریبی اور واضح تصویر بھیجیں تاکہ زرعی ماہرین بہتر رہنمائی کر سکیں۔"
)


def _build_farmer_response(
    crop: str,
    weather: dict,
    recovery_result: dict,
    diagnosis: dict,
    contradictions: list,
) -> str:
    """
    Build a detailed, crop-specific, weather-aware Urdu response
    for the farmer following the structured Urdu advisory format.

    Never returns empty — falls back to a safe Urdu message.
    """
    try:
        # Get crop data
        crop_info = _FALLBACK_CROP_DATA.get(crop, _FALLBACK_CROP_DATA["Unknown"])

        # ── 1. Diagnosis Section ──
        # Use diagnosis disease_urdu if available, else crop default
        problem_text = diagnosis.get("disease_urdu") or crop_info["problem"]

        # ── 2. Risk Level Section ──
        risk_val = diagnosis.get("risk_level", "Medium")
        # Map risk level to Urdu
        risk_map = {
            "High": "زیادہ",
            "Medium": "درمیانہ",
            "Low": "کم"
        }
        risk_level_urdu = risk_map.get(risk_val, "درمیانہ")

        # Determine explanation reason
        if crop == "Cotton":
            reason_urdu = "پتے مڑنے اور پیلے ہونے سے پودے کی بڑھوتری اور خوراک بنانے کی صلاحیت متاثر ہو سکتی ہے۔"
        elif crop == "Wheat":
            reason_urdu = "زرد زنگ کی فنگس تیزی سے پھیل کر پیداوار کو شدید نقصان پہنچا سکتی ہے۔"
        elif crop == "Mango":
            reason_urdu = "اینتھراکنوز نمی یا بارش کی وجہ سے پتوں اور پھلوں میں پھیل سکتا ہے۔"
        else:
            reason_urdu = "معلومات کی کمی کی وجہ سے فوری تشخیص ممکن نہیں۔"

        risk_text = f"{risk_level_urdu} — {reason_urdu}"

        # ── 3. Actions Section ──
        actions = list(crop_info["actions"])
        # Check budget recovery
        recovery_actions = recovery_result.get("recovery_actions", [])
        has_budget_issue = any(
            ra.get("type") == "budget_alternative" for ra in recovery_actions
        )
        if has_budget_issue:
            actions.append("مہنگی دوا کے بجائے کم قیمت مناسب متبادل استعمال کیا جا سکتا ہے، مگر مقامی زرعی ماہر سے تصدیق ضرور کریں۔")

        actions_text = "\n".join(f"{i+1}. {act}" for i, act in enumerate(actions))

        # ── 4. Weather Section ──
        weather_advice = get_weather_instruction(weather)

        # ── 5. Next Step Section ──
        next_step_text = crop_info["next_step"]
        if diagnosis.get("needs_second_photo", False):
            next_step_text = f"تشخیص کا اعتماد کم ہے، براہ کرم ایک اور واضح تصویر بھیجیں۔ {next_step_text}"

        # Assemble final structured response
        lines = [
            "ممکنہ مسئلہ:",
            problem_text,
            "",
            "خطرے کی سطح:",
            risk_text,
            "",
            "تجویز کردہ عمل:",
            actions_text,
            "",
            "موسم کا خیال:",
            weather_advice,
            "",
            "اگلا قدم:",
            next_step_text
        ]

        farmer_response = "\n".join(lines).strip()

        # ── Contradiction warnings ──
        for contradiction in contradictions:
            msg = contradiction.get("message_urdu", "")
            if msg:
                farmer_response += f"\n\n⚠ {msg}"

        return farmer_response if farmer_response else _FALLBACK_RESPONSE

    except Exception:
        return _FALLBACK_RESPONSE


def format_outcome(
    parsed_input: dict,
    diagnosis: dict,
    context: dict,
    action_chain: list,
    execution_result: dict,
    recovery_result: dict,
) -> dict:
    """
    Produce the final structured response sent to the frontend.

    Parameters
    ----------
    parsed_input : dict
        Output of InputParserAgent.
    diagnosis : dict
        Output of DiagnosisAgent.
    context : dict
        Output of ContextAgent.
    action_chain : list
        Output of ActionPlannerAgent.
    execution_result : dict
        Output of ExecutionAgent.
    recovery_result : dict
        Output of RecoveryAgent.

    Returns
    -------
    dict — the complete API response body.
    """
    t0 = time.perf_counter()

    try:
        weather = context.get("weather", {})
        crop = diagnosis.get("crop", "Unknown")
        contradictions = context.get("contradictions", [])

        # Normalize language_hint
        language_hint = parsed_input.get("language_hint", "ur") if parsed_input else "ur"
        if language_hint in ("ur", "urdu"):
            language_hint = "ur"
        elif language_hint not in ("roman_urdu", "english"):
            language_hint = "ur"

        # ---- Farmer response (Urdu) — always non-empty ----
        # Step A: Build rule-based fallback (always available)
        fallback_response = _build_farmer_response(
            crop=crop,
            weather=weather,
            recovery_result=recovery_result,
            diagnosis=diagnosis,
            contradictions=contradictions,
        )
        farmer_response = fallback_response
        tts_summary = generate_safe_tts_summary(fallback_response, language_hint)

        # Step B: Try Gemini text response if user sent text or image exists
        user_text = parsed_input.get("text", "")
        has_image = parsed_input.get("has_image", False)
        
        gemini_result = None
        gemini_status = {
            "used": False,
            "success": False,
            "error_type": None,
            "model_used": None,
            "available_models": [],
            "tested_models": [],
            "working_model": None,
            "pool": "CHAT",
            "key_index_used": 0,
            "attempts": []
        }

        # ── RAG retrieval (safe — never crashes) ────────────────────────────
        rag_crop = None
        rag_chunks = []
        rag_context_text = ""
        rag_error = None

        if user_text or has_image:
            from utils.helpers import is_agriculture_related, is_image_blank_or_solid
            
            image_bytes = parsed_input.get("image_bytes") if parsed_input else None
            
            # Relevance Check
            if is_image_blank_or_solid(image_bytes) or not is_agriculture_related(user_text, has_image):
                gemini_status["used"] = True
                gemini_status["success"] = False
                gemini_status["error_type"] = "irrelevant_query"
                
                # Polite refusal based on language_hint
                if language_hint == "ur":
                    farmer_response = "یہ سسٹم صرف فصل، پودوں کی بیماری، کیڑے، کھاد، پانی، موسم، اور زرعی مسائل کے لیے بنایا گیا ہے۔ براہ کرم اپنی فصل کا مسئلہ، تصویر، یا وائس نوٹ بھیجیں۔"
                elif language_hint == "roman_urdu":
                    farmer_response = "Yeh system sirf faslon, podon ki bemari, keeron, khaad, pani, mosam, aur zaraati masail ke liye banaya gaya hai. Barah-e-karam apni fasal ka masla, tasveer, ya voice note bhejein."
                else: # english
                    farmer_response = "This system is only built for crops, plant diseases, pests, fertilizer, irrigation, weather impact, and farming problems. Please send your crop issue, image, or voice note."
                
                tts_summary = generate_safe_tts_summary(farmer_response, language_hint)
                # RAG skipped for irrelevant queries
            else:
                # ── RAG: detect crop and retrieve chunks ──
                try:
                    rag_crop = detect_rag_crop(user_text or "")
                    if rag_crop:
                        rag_chunks = retrieve_chunks(user_text or "", detected_crop=rag_crop)
                    else:
                        # Unknown crop — light search across all
                        rag_chunks = retrieve_chunks(user_text or "", detected_crop=None)
                    if rag_chunks:
                        rag_context_text = format_rag_context(rag_chunks)
                except Exception as rag_exc:
                    logger.warning("[RAG] Retrieval failed safely: %s", rag_exc)
                    rag_error = "RAG failed safely"
                    rag_chunks = []
                    rag_context_text = ""

                gemini_result = generate_gemini_farmer_response(
                    user_text=user_text,
                    parsed_input=parsed_input,
                    diagnosis=diagnosis,
                    weather=weather,
                    rag_context=rag_context_text,
                )
                gemini_status["used"] = True
                gemini_status["success"] = gemini_result.get("success", False) if gemini_result else False
                gemini_status["error_type"] = gemini_result.get("error_type") if gemini_result else "unknown_error"
                gemini_status["model_used"] = gemini_result.get("model_used") if gemini_result else None
                gemini_status["available_models"] = gemini_result.get("available_models", []) if gemini_result else []
                gemini_status["tested_models"] = gemini_result.get("tested_models", []) if gemini_result else []
                gemini_status["working_model"] = gemini_result.get("working_model") if gemini_result else None
                gemini_status["pool"] = gemini_result.get("pool", "CHAT") if gemini_result else "CHAT"
                gemini_status["key_index_used"] = gemini_result.get("key_index_used", 1) if gemini_result else 1
                gemini_status["attempts"] = gemini_result.get("attempts", []) if gemini_result else []

                # Step C: Prefer Gemini, fall back to error
                if gemini_result.get("success"):
                    farmer_response = gemini_result.get("text")
                    tts_summary = gemini_result.get("tts_summary") or generate_safe_tts_summary(farmer_response, language_hint)
                else:
                    if language_hint == "ur":
                        farmer_response = "Gemini API اس وقت جواب نہیں دے رہی۔ براہ کرم تھوڑی دیر بعد دوبارہ کوشش کریں۔"
                    elif language_hint == "roman_urdu":
                        farmer_response = "Gemini API is waqt jawab nahi de rahi. Barah-e-karam thori dair baad dobara koshish karein."
                    else: # english
                        farmer_response = "Gemini API is not responding right now. Please try again after a short while."
                    
                    tts_summary = generate_safe_tts_summary(farmer_response, language_hint)
        else:
            # Gemini not used because both text and image are missing
            farmer_response = "براہ کرم اپنا مسئلہ لکھیں، تصویر بھیجیں، یا دونوں فراہم کریں۔"
            tts_summary = generate_safe_tts_summary(farmer_response, language_hint)

        # ---- Irrigation advice (Urdu) ----
        has_weather_source = bool(weather) and weather.get("source", "") != ""
        if not has_weather_source:
            irrigation_message = (
                "موسم کی معلومات دستیاب نہیں، پانی دینے سے پہلے "
                "مقامی موسم ضرور چیک کریں۔"
            )
        elif weather.get("rain_expected", False):
            irrigation_message = "بارش متوقع ہے، اس لیے ابھی پانی نہ دیں۔"
        else:
            irrigation_message = (
                "بارش متوقع نہیں، اگر زمین خشک ہے تو ہلکا پانی "
                "دیا جا سکتا ہے۔"
            )

        irrigation_advice = {
            "heading": "پانی کا مشورہ",
            "message": irrigation_message,
            "based_on": "weather",
        }

        # ---- Cost summary ----
        total_cost = sum(
            a.get("estimated_cost_pkr", 0) for a in action_chain
        )
        # If recovery reduced cost, reflect that
        for ra in recovery_result.get("recovery_actions", []):
            if ra.get("type") == "budget_alternative":
                original = ra.get("original_cost_pkr", 0)
                alternative = ra.get("alternative_cost_pkr", MANGO_ALTERNATIVE_COST_PKR)
                total_cost = total_cost - original + alternative

        cost_summary = {
            "budget_limit_pkr": DEFAULT_BUDGET_LIMIT_PKR,
            "estimated_total_pkr": max(total_cost, 0),
            "currency": "PKR",
        }

        # ---- Before / After ----
        before_after = {
            "before_risk": "Unknown",
            "after_risk": diagnosis.get("risk_level", "Unknown"),
        }

        # ---- Collect all agent logs ----
        agent_logs = collect_logs(
            parsed_input.get("log"),
            diagnosis.get("log"),
            context.get("log"),
            create_log(
                agent_name="ActionPlannerAgent",
                input_summary=f"crop={diagnosis.get('crop')}, risk={diagnosis.get('risk_level')}",
                decision=f"Generated {len(action_chain)} action steps",
                status="success",
                latency_ms=action_chain[0].get("latency_ms", 0) if action_chain else 0,
            ),
            execution_result.get("log"),
            recovery_result.get("log"),
        )

        latency = measure_latency_ms(t0)
        outcome_log = create_log(
            agent_name="OutcomeAgent",
            input_summary="All agent outputs received",
            decision="Final response assembled",
            status="success",
            latency_ms=latency,
        )
        agent_logs.append(outcome_log)

        return {
            "farmer_response": farmer_response,
            "tts_summary": tts_summary,
            "diagnosis": {
                "crop": diagnosis.get("crop"),
                "disease": diagnosis.get("disease"),
                "disease_urdu": diagnosis.get("disease_urdu"),
                "confidence": diagnosis.get("confidence"),
                "risk_level": diagnosis.get("risk_level"),
                "evidence": diagnosis.get("evidence", []),
                "needs_second_photo": diagnosis.get("needs_second_photo", False),
            },
            "action_chain": execution_result.get("executed_actions", action_chain),
            "weather": weather,
            "irrigation_advice": irrigation_advice,
            "before_after": before_after,
            "cost_summary": cost_summary,
            "agent_logs": agent_logs,
            "contradictions": context.get("contradictions", []),
            "recovery": {
                "status": recovery_result.get("recovery_status", "stable"),
                "actions": recovery_result.get("recovery_actions", []),
            },
            "gemini_status": gemini_status,
            "rag_status": build_rag_status(rag_crop, rag_chunks, rag_error),
        }

    except Exception:
        # Absolute fallback — farmer_response is NEVER empty
        return {
            "farmer_response": _FALLBACK_RESPONSE,
            "tts_summary": generate_safe_tts_summary(_FALLBACK_RESPONSE, "ur"),
            "diagnosis": {},
            "action_chain": [],
            "weather": {},
            "irrigation_advice": {"heading": "پانی کا مشورہ", "message": "", "based_on": "weather"},
            "before_after": {},
            "cost_summary": {},
            "agent_logs": [],
            "contradictions": [],
            "recovery": {"status": "stable", "actions": []},
            "gemini_status": {
                "used": False,
                "success": False,
                "error_type": "unknown_error",
                "model_used": None,
                "available_models": [],
                "tested_models": [],
                "working_model": None
            },
            "rag_status": build_rag_status(None, [], "RAG failed safely"),
        }
