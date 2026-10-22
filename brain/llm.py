# brain/llm.py
"""LLM provider abstraction with support for Mock, Ollama, and OpenAI-compatible endpoints."""

from abc import ABC, abstractmethod
import json
import logging
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

logger = logging.getLogger("jarvis.brain.llm")


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate raw text response."""
        pass

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate response from a conversation message history."""
        pass


class MockLLMProvider(BaseLLMProvider):
    """Built-in conversational assistant that provides warm, natural, intelligent Jarvis responses."""

    def __init__(self):
        logger.info("Initialized MockLLMProvider (Conversational mode).")

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        clean = (prompt or "").strip()
        # If wrapped in a template (e.g. "System: ...\nUser: <query>\nJarvis:"), extract the actual user query
        import re
        m_user = re.search(r'(?:^|\n)User:\s*(.*?)(?:\nJarvis:|$)', clean, re.DOTALL | re.IGNORECASE)
        user_msg = m_user.group(1).strip() if m_user else clean
        lower = user_msg.lower()

        # 0. Time & Date Queries
        from core.time_context import get_time_context
        tc = get_time_context()
        time_query_ans = tc.resolve_time_query(user_msg)
        if time_query_ans:
            return time_query_ans

        # 1. Exact / Common Greetings using TimeContext
        if lower in ("hi", "hi jarvis", "hey", "hey jarvis", "yo", "sup", "heyy", "hii", "hello", "hello jarvis", "helo", "hlo", "hello there", "namaste", "namaskar", "pranam"):
            return tc.get_greeting(user_said=user_msg)

        # Casual Hinglish Conversation Examples
        if any(w in lower for w in ["kya kar raha hai", "kya kar rahe ho", "what are you doing"]):
            return "Bas tumhara wait kar raha tha 😄\nBolo, aaj kya karna hai?"

        if any(w in lower for w in ["kuch nahi yaar", "kuch nahi", "nothing much"]):
            return "😄 Theek hai. Kabhi-kabhi kuch na karna bhi zaroori hai."

        if any(w in lower for w in ["achha ek baat bata", "ek baat bata", "suno ek baat"]):
            return "Haan bolo."

        if any(w in lower for w in ["yaad rakhoge", "yaad rakhna", "sikhau to yaad"]):
            return "Haan. Agar tum chaho to main usse future ke liye remember kar sakta hoon."

        if lower in ("jaise", "jaise?", "jaise ki?", "like what"):
            return "Jaise tumhari preferred settings, tum kis tarah ka workflow pasand karte ho,\nya kisi particular kaam ko tum kis tarah karwana chahte ho."

        if any(w in lower for w in ["mood kharab", "sad hoon", "thak gaya", "bore ho raha"]):
            return "Arre yaar, kya hua? Kabhi-kabhi thoda break lena hi best hota hai. Chill karo!"

        if any(w in lower for w in ["joke suna", "chutkula", "koi funny", "hasao"]):
            return "Ek baar ek programmer ne shopping list banayi:\n'1 bread lana, agar eggs hon to 10 le aana.'\nWo 10 bread le aaya kyunki eggs the! 😄"

        if any(w in lower for w in ["kaunsa better hai", "mujhe kya karna chahiye", "tumhare hisaab se"]):
            return "Mere hisaab se pehle requirement aur simplicity dekhni chahiye. Aapka primary goal kya hai, bataiye fir main best suggest karta hoon!"

        if any(g in lower for g in [
            "good morning", "good moring", "gud morning", "gud moring", "morning", "gm",
            "shubh prabhat", "suprabhat", "subah bakhair",
            "good afternoon", "gud afternoon", "afternoon", "shubh dopahar",
            "good evening", "gud evening", "evening", "shubh sandhya",
            "good night", "gud night", "shubh ratri", "gn",
            "hello", "helo", "hallo", "namaste", "pranam"
        ]):
            return tc.get_greeting(user_said=user_msg)

        if any(w in lower for w in ["kaise ho", "kya haal hai", "kaisa chal raha hai", "sab theek"]):
            return "Main bilkul theek hoon! Aap bataiye, kya karna hai?"

        # 1b. Presence & Microphone / Voice Hearing Check
        if any(w in lower for w in [
            "meri awaaz sun", "awaaz sun rahe ho", "sun rahe ho",
            "can you hear me", "are you listening", "am i audible",
            "awaaz aa rahi hai", "sun raha hai", "sun rhe ho", "sun pa rahe ho",
            "kya tum meri awaaz"
        ]):
            return "Haan Boss, main aapki awaaz bilkul saaf sun raha hoon! Boliye, main aapki kya madad kar sakta hoon?"

        # 1c. Screen Viewing & Vision Capability Check
        if any(w in lower for w in [
            "see my screen", "view my screen", "screen dekh", "screen dikh rahi",
            "able to see my screen", "look at my screen", "screen visible"
        ]):
            if any(w in lower for w in ["are you", "can you", "able to"]):
                return "Yes Boss! I can see and inspect your screen, check active windows, and capture screenshots anytime."
            return "Ji haan Boss! Main aapki screen bilkul dekh aur inspect kar sakta hoon, open windows detect kar sakta hoon aur screenshot le sakta hoon."

        # 1d. Open Windows & Screen Activity Inquiries Fallback
        if any(w in lower for w in ["konsi windows", "kaunsi windows", "what windows", "which windows", "screen pe kya", "screen par kya"]):
            return "Aapki screen par open windows aur running applications inspect kar raha hoon, Boss."

        # 2. Identity & Capabilities
        if any(w in lower for w in ["who are you", "who made you", "tum kaun ho", "aap kaun ho"]):
            return "I am JARVIS — your autonomous, real-time AI assistant with voice, desktop automation, and cognitive learning."

        if any(w in lower for w in ["how are you", "how are things", "how's it going", "status batao"]):
            return "All systems are operational and running at peak performance, Boss! Ready for your command."

        if lower in ("what can you do", "help", "kya kar sakte ho", "commands", "what are your capabilities", "show commands") or any(re.search(r'\b' + re.escape(w) + r'\b', lower) for w in ["what can you do", "kya kar sakte ho", "show commands"]):
            return "I can automate desktop apps (Chrome, Excel, VLC), control volume and system settings, take screenshots, manage audio, and learn your workflows! Just give me a command."

        # 3. Courtesy & Appreciation
        if any(w in lower for w in ["thank you", "thanks", "dhanyawad", "shukriya", "thx"]):
            return "You're welcome, Boss! Always at your service. ✨"

        if any(w in lower for w in ["good job", "well done", "shabash", "great job", "nice"]):
            return "Thank you, Boss! Happy to help. 😊"

        if any(w in lower for w in ["bye", "goodbye", "alvida", "see you"]):
            return "Goodbye, Boss! Have a great day. Call me anytime you need assistance. 👋"

        # 3b. User Wellbeing & Casual Chit-Chat ("main achha hun", "theek hun", "sab badhiya", "i'm good")
        wellbeing_words = [
            "main achha", "main accha", "main theek", "main thik", "main badhiya", "main badiya",
            "ekdam badhiya", "ekdam theek", "ekdam mast", "sab badhiya", "sab theek", "sab sahi",
            "achha hun", "accha hun", "achha hoon", "accha hoon", "theek hun", "theek hoon",
            "thik hun", "thik hoon", "badhiya hoon", "badhiya hun", "mast hoon", "mast hun",
            "i'm good", "i am good", "i'm fine", "i am fine", "doing well", "all good", "all well"
        ]
        if any(w in lower for w in wellbeing_words) or lower.strip() in ("achha", "accha", "theek", "thik", "badhiya", "mast", "fine", "good"):
            if any(w in lower for w in ["tum batao", "aap batao", "aap sunao", "tum sunao", "and you", "what about you"]):
                return "Yeh sunkar achha laga! Main bhi ekdam badhiya hoon, Sir. Bataiye, aaj kya plan hai?"
            return "Yeh sunkar achha laga, Sir! Aur bataiye, aaj kya chal raha hai?"

        # 3c. Reciprocal Questions & Small Talk ("tum batao", "aur batao", "kya chal raha hai")
        if any(w in lower for w in ["tum batao", "aap batao", "aap sunao", "tum sunao", "aur batao", "aur sunao", "what about you", "what's up", "whats up"]):
            return "Bas sab badhiya chal raha hai, Sir! Aapki commands ka wait kar raha tha. Bataiye aaj kya naya karein?"

        # 3d. Boredom & Idle Chat ("bore ho raha hoon", "kuch khas nahi", "bas aise hi")
        if any(w in lower for w in ["bore ho raha", "boring lag raha", "i'm bored", "kuch interesting batao"]):
            return "Koi baat nahi Sir, thoda refresh ho lijiye! Koi accha music chalaun ya YouTube par kuch interesting dekhna chahenge?"
        if any(w in lower for w in ["kuch khas nahi", "kuch nahi", "bas aise hi", "nothing much", "not much", "just chilling"]):
            return "Theek hai Sir, aaram se chill kijiye. Jab bhi meri zaroorat ho, bas batayein!"

        # 4. Time & Date Queries Fallback via centralized TimeContext
        if any(w in lower for w in ["time", "samay", "kitne baje", "date", "tarikh", "din"]):
            ans = tc.resolve_time_query(user_msg)
            if ans:
                return ans

        # 4b. General Knowledge & Reasoning Engine Fallback
        try:
            from core.knowledge import get_knowledge_engine, ConfidenceLevel
            ke = get_knowledge_engine()
            if ke.is_knowledge_candidate(user_msg):
                res = ke.query(user_msg)
                if res.found and res.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM):
                    return res.answer_text
                elif res.found or res.confidence == ConfidenceLevel.LOW:
                    return res.answer_text
        except Exception:
            pass

        # 5. Natural Clarification Fallback (Never give fake understanding acknowledgment)
        is_english = not any(w in lower for w in [
            "kya", "aap", "tum", "mera", "meri", "mere", "mujhe", "hai", "hain", "karo",
            "kholo", "batao", "dikhao", "chalao", "samajh", "bhai", "yaar", "ho", "hun",
            "hoon", "hu", "achha", "accha", "theek", "thik", "badhiya", "badiya", "mast",
            "sab", "main", "suno", "bolo"
        ])
        if is_english:
            return "Sir, I need a little more context. What are you referring to?"
        return "Sir, mujhe thoda context chahiye. Aap kis cheez ki baat kar rahe hain?"

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        last_msg = messages[-1]["content"] if messages else ""
        return self.generate(last_msg)


class OllamaProvider(BaseLLMProvider):
    """Local Ollama REST API integration."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "")
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            return f"[Ollama Error: {e}]"

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            return f"[Ollama Error: {e}]"


class OpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI-compatible REST API (OpenAI, Groq, DeepSeek, vLLM, LMStudio)."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: int = 30
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, **kwargs)

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
        except Exception as e:
            logger.error(f"OpenAI compatible API error: {e}")
            return f"[LLM Provider Error: {e}]"


def get_llm_provider(config: Dict[str, Any]) -> BaseLLMProvider:
    """Factory to instantiate the configured LLM provider."""
    brain_cfg = config.get("brain", {})
    provider_type = brain_cfg.get("llm_provider", "mock").lower()

    if provider_type == "ollama":
        return OllamaProvider(
            base_url=brain_cfg.get("api_base_url", "http://localhost:11434"),
            model=brain_cfg.get("model", "llama3"),
            timeout=brain_cfg.get("timeout", 30)
        )
    elif provider_type in ("openai", "groq", "deepseek", "custom"):
        return OpenAICompatibleProvider(
            api_key=brain_cfg.get("api_key", ""),
            base_url=brain_cfg.get("api_base_url", "https://api.openai.com/v1"),
            model=brain_cfg.get("model", "gpt-4o-mini"),
            timeout=brain_cfg.get("timeout", 30)
        )
    return MockLLMProvider()
