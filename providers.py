import abc
import os
import requests
import logging
from typing import Optional
from pydantic import BaseModel


class AgentResponse(BaseModel):
    success: bool
    message: str
    code_generated: Optional[str] = None
    tokens_used: int = 0


class BaseProvider(abc.ABC):
    @abc.abstractmethod
    def generate(self, prompt: str) -> AgentResponse:
        pass

    @property
    def max_context_chars(self) -> int:
        env_val = os.getenv("MAX_CONTEXT_CHARS")
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                pass
        return 100000  # Default for cloud providers

    def get_available_models(self) -> list[str]:
        return []

    def embed(self, text: str) -> list[float]:
        return []


class OllamaProvider(BaseProvider):
    def __init__(self, model: str = "llama3"):
        self.model = model
        self.url = "http://localhost:11434/api/generate"

    @property
    def max_context_chars(self) -> int:
        env_val = os.getenv("MAX_CONTEXT_CHARS")
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                pass
        return 12000  # Default for local Ollama to avoid context overflow

    def generate(self, prompt: str) -> AgentResponse:
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False}
            response = requests.post(self.url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                return AgentResponse(
                    success=True,
                    message=f"Ollama ({self.model}): Successfully generated",
                    code_generated=data.get("response", ""),
                    tokens_used=data.get("eval_count", 0),
                )
            return AgentResponse(
                success=False, message=f"Ollama Error: {response.status_code}"
            )
        except Exception as e:
            return AgentResponse(
                success=False, message=f"Local Ollama not reachable: {str(e)}"
            )

    def get_available_models(self) -> list[str]:
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logging.debug(f"Ollama get_available_models failed: {e}")
        return ["llama3", "codegemma", "mistral", "phi3"]

    def embed(self, text: str) -> list[float]:
        try:
            payload = {"model": self.model, "prompt": text}
            response = requests.post("http://localhost:11434/api/embeddings", json=payload, timeout=10)
            if response.status_code == 200:
                return response.json().get("embedding", [])
        except Exception as e:
            logging.debug(f"Ollama embed failed: {e}")
        return []


class GeminiProvider(BaseProvider):
    def __init__(self, model: Optional[str] = None):
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
        model_name = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.model = genai.GenerativeModel(model_name)

    def generate(self, prompt: str) -> AgentResponse:
        if not os.getenv("GEMINI_API_KEY"):
            return AgentResponse(success=False, message="GEMINI_API_KEY missing")
        try:
            response = self.model.generate_content(prompt)
            return AgentResponse(
                success=True,
                message="Gemini: Successfully generated",
                code_generated=response.text,
                tokens_used=getattr(response.usage_metadata, "total_token_count", 150)
                if hasattr(response, "usage_metadata")
                else 150,
            )
        except Exception as e:
            return AgentResponse(success=False, message=str(e))

    def get_available_models(self) -> list[str]:
        models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash"]
        if os.getenv("GEMINI_API_KEY"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                dynamic = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        name = m.name.replace("models/", "")
                        if name not in models:
                            dynamic.append(name)
                models.extend(sorted(dynamic))
            except Exception as e:
                logging.debug(f"Gemini get_available_models failed: {e}")
        return models

    def embed(self, text: str) -> list[float]:
        if not os.getenv("GEMINI_API_KEY"):
            return []
        try:
            import google.generativeai as genai
            # Use standard Google Generative AI embeddings model
            result = genai.embed_content(model="models/text-embedding-004", content=text)
            return result.get("embedding", [])
        except Exception as e:
            logging.debug(f"Gemini embed failed: {e}")
        return []


class AnthropicProvider(BaseProvider):
    def __init__(self, model: Optional[str] = None):
        from anthropic import Anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = Anthropic(api_key=api_key or "missing-key")
        self.model = model or "claude-3-5-sonnet-20240620"

    def generate(self, prompt: str) -> AgentResponse:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return AgentResponse(success=False, message="ANTHROPIC_API_KEY missing")
        try:
            system_msg = []
            if prompt.startswith("Context: [") and "Task: " in prompt:
                parts = prompt.split("Task: ", 1)
                context_str = parts[0]
                user_str = "Task: " + parts[1]
                system_msg = [
                    {
                        "type": "text",
                        "text": context_str,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                user_str = prompt

            # Use beta for prompt caching if it's a larger context window
            if system_msg:
                message = self.client.beta.prompt_caching.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=system_msg,
                    messages=[{"role": "user", "content": user_str}],
                )
            else:
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": user_str}],
                )

            # Read cache_creation_input_tokens if available
            cache_hits = 0
            if (
                hasattr(message.usage, "cache_read_input_tokens")
                and message.usage.cache_read_input_tokens
            ):
                cache_hits = message.usage.cache_read_input_tokens

            return AgentResponse(
                success=True,
                message=f"Anthropic: Successfully generated (Cache-Hits: {cache_hits})",
                code_generated=message.content[0].text,
                tokens_used=message.usage.input_tokens + message.usage.output_tokens,
            )
        except Exception as e:
            return AgentResponse(success=False, message=str(e))

    def get_available_models(self) -> list[str]:
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-5-sonnet-20240620",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307"
        ]


class OpenAIProvider(BaseProvider):
    def __init__(self, model: Optional[str] = None):
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key or "missing-key")
        self.model = model or "gpt-4o"

    def generate(self, prompt: str) -> AgentResponse:
        if not os.getenv("OPENAI_API_KEY"):
            return AgentResponse(success=False, message="OPENAI_API_KEY missing")
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": prompt}]
            )
            return AgentResponse(
                success=True,
                message="OpenAI: Successfully generated",
                code_generated=response.choices[0].message.content,
                tokens_used=response.usage.total_tokens,
            )
        except Exception as e:
            return AgentResponse(success=False, message=str(e))

    def get_available_models(self) -> list[str]:
        models = ["gpt-4o", "gpt-4o-mini", "o1-mini", "o1-preview", "gpt-4-turbo"]
        if os.getenv("OPENAI_API_KEY"):
            try:
                res = self.client.models.list()
                dynamic = []
                for m in res.data:
                    if m.id.startswith(("gpt-", "o1-")) and m.id not in models:
                        dynamic.append(m.id)
                models.extend(sorted(dynamic))
            except Exception as e:
                logging.debug(f"OpenAI get_available_models failed: {e}")
        return models

    def embed(self, text: str) -> list[float]:
        if not os.getenv("OPENAI_API_KEY"):
            return []
        try:
            response = self.client.embeddings.create(input=[text], model="text-embedding-3-small")
            return response.data[0].embedding
        except Exception as e:
            logging.debug(f"OpenAI embed failed: {e}")
        return []


class LMStudioProvider(BaseProvider):
    def __init__(self, model: Optional[str] = None):
        from openai import OpenAI

        # LM Studio runs on port 1234 by default and uses an OpenAI compatible API
        self.client = OpenAI(
            base_url="http://127.0.0.1:1234/v1",
            api_key=os.getenv("LMSTUDIO_API_KEY", "lm-studio")
        )
        self.model = model or "local-model"

    @property
    def max_context_chars(self) -> int:
        env_val = os.getenv("MAX_CONTEXT_CHARS")
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                pass
        return 12000  # Default for local LM Studio to avoid context overflow

    def generate(self, prompt: str) -> AgentResponse:
        try:
            response = self.client.chat.completions.create(
                model=self.model,  # LM Studio mostly ignores the model name
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            return AgentResponse(
                success=True,
                message="LM Studio: Successfully generated",
                code_generated=response.choices[0].message.content,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            import openai
            if isinstance(e, openai.APIStatusError):
                return AgentResponse(
                    success=False, message=f"Local LM Studio API Error (Status {e.status_code}): {e.message}"
                )
            elif isinstance(e, openai.APIConnectionError):
                return AgentResponse(
                    success=False, message=f"Local LM Studio connection failed: {str(e)}"
                )
            return AgentResponse(
                success=False, message=f"Local LM Studio error: {str(e)}"
            )

    def get_available_models(self) -> list[str]:
        try:
            import requests
            response = requests.get("http://127.0.0.1:1234/v1/models", timeout=2)
            if response.status_code == 200:
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logging.debug(f"LMStudio get_available_models failed: {e}")
        return ["local-model"]

    def embed(self, text: str) -> list[float]:
        try:
            response = self.client.embeddings.create(input=[text], model=self.model)
            return response.data[0].embedding
        except Exception as e:
            logging.debug(f"LMStudio embed failed: {e}")
        return []


class CodestralProvider(BaseProvider):
    def __init__(self, model: Optional[str] = None):
        from openai import OpenAI

        api_key = os.getenv("CODESTRAL_API_KEY") or os.getenv("MISTRAL_API_KEY")
        self.client = OpenAI(
            base_url="https://codestral.mistral.ai/v1",
            api_key=api_key or "missing-key"
        )
        self.model = model or "codestral-latest"

    def generate(self, prompt: str) -> AgentResponse:
        api_key = os.getenv("CODESTRAL_API_KEY") or os.getenv("MISTRAL_API_KEY")
        if not api_key:
            return AgentResponse(success=False, message="CODESTRAL_API_KEY or MISTRAL_API_KEY missing")
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": prompt}]
            )
            return AgentResponse(
                success=True,
                message=f"Codestral ({self.model}): Successfully generated",
                code_generated=response.choices[0].message.content,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return AgentResponse(success=False, message=str(e))

    def get_available_models(self) -> list[str]:
        return ["codestral-latest", "codestral-2405"]


class OpenRouterProvider(BaseProvider):
    def __init__(self, model: Optional[str] = None):
        from openai import OpenAI

        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or "missing-key"
        )
        self.model = model or os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-70b-instruct:free")

    def generate(self, prompt: str) -> AgentResponse:
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return AgentResponse(success=False, message="OPENROUTER_API_KEY or OPENAI_API_KEY missing")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                extra_headers={
                    "HTTP-Referer": "https://github.com/peppi/mini-cli",
                    "X-Title": "mini-cli",
                }
            )
            return AgentResponse(
                success=True,
                message=f"OpenRouter ({self.model}): Successfully generated",
                code_generated=response.choices[0].message.content,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
        except Exception as e:
            return AgentResponse(success=False, message=str(e))

    def get_available_models(self) -> list[str]:
        return [
            "meta-llama/llama-3-70b-instruct:free",
            "meta-llama/llama-3-8b-instruct:free",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-pro-1.5",
            "mistralai/mixtral-8x7b-instruct",
        ]

    def embed(self, text: str) -> list[float]:
        try:
            response = self.client.embeddings.create(input=[text], model="openai/text-embedding-3-small")
            return response.data[0].embedding
        except Exception as e:
            logging.debug(f"OpenRouter embed failed: {e}")
        return []


class ProviderFactory:
    @staticmethod
    def get_provider(name: str) -> BaseProvider:
        parts = name.split(":", 1)
        provider_type = parts[0].lower()
        model_name = parts[1] if len(parts) > 1 else None

        if provider_type == "gemini":
            return GeminiProvider(model_name)
        elif provider_type == "anthropic":
            return AnthropicProvider(model_name)
        elif provider_type == "openai":
            return OpenAIProvider(model_name)
        elif provider_type == "lmstudio":
            return LMStudioProvider(model_name)
        elif provider_type == "codestral":
            return CodestralProvider(model_name)
        elif provider_type == "openrouter":
            return OpenRouterProvider(model_name)
        else:
            if model_name:
                return OllamaProvider(model_name)
            return OllamaProvider()
