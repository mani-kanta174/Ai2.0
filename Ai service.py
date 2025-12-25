"""
AI Service - Unified interface for AI providers

Supports: Gemini, OpenAI, Anthropic
Uses prompts.py for schemas and ai_config.py for provider configuration
"""

import os
import json
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from openai import OpenAI
from flask import current_app

# Import new centralized prompts
from prompts import SCHEMAS as PROMPT_SCHEMAS

# Import provider config (minimal use of ai_config)
try:
    from ai_config import ACTIVE_PROVIDER, PROVIDER_DEFAULTS
except ImportError:
    ACTIVE_PROVIDER = "gemini"
    PROVIDER_DEFAULTS = {
        "gemini": {"model": "gemini-2.0-flash", "api_key_env": "GEMINI_API_KEY"},
        "openai": {"model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"},
        "anthropic": {"model": "claude-3-5-sonnet-20241022", "api_key_env": "ANTHROPIC_API_KEY"}
    }


class AIProvider:
    """Base class for AI providers."""
    
    def generate_content(self, prompt: str) -> str:
        """Generate unstructured text content."""
        raise NotImplementedError
    
    def generate_with_schema(self, prompt: str, response_schema: dict) -> dict:
        """Generate content with a structured response schema."""
        # Default fallback: generate and parse JSON
        response = self.generate_content(prompt)
        return json.loads(response)


class GeminiProvider(AIProvider):
    """Google Gemini AI provider with native structured output support."""
    
    def __init__(self, api_key: str, model_name: str):
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(model_name)

    def generate_content(self, prompt: str) -> str:
        response = self.model.generate_content(prompt)
        return response.text
    
    def generate_with_schema(self, prompt: str, response_schema: dict) -> dict:
        """Generate using Gemini's native response_schema parameter."""
        try:
            model = genai.GenerativeModel(
                self.model_name,
                generation_config=GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema
                )
            )
            response = model.generate_content(prompt)
            return json.loads(response.text)
        except Exception as e:
            print(f"[AIService] Gemini structured generation failed, falling back: {e}")
            return self._fallback_parse(self.generate_content(prompt))
    
    def _fallback_parse(self, text: str) -> dict:
        """Parse JSON from text, handling markdown code blocks."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())


class OpenAIProvider(AIProvider):
    """OpenAI provider with JSON mode structured output."""
    
    def __init__(self, api_key: str, model_name: str, base_url: str = None):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    def generate_content(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    
    def generate_with_schema(self, prompt: str, response_schema: dict) -> dict:
        """Generate using OpenAI's json_object mode (gpt-4o-mini doesn't support strict schemas)."""
        try:
            # For gpt-4o-mini, use json_object mode with modified prompt
            # Add "json" to prompt as required by OpenAI
            json_prompt = f"{prompt}\n\nRespond with valid JSON only."
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": json_prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[AIService] OpenAI json_object failed: {e}")
            # Final fallback: plain text and try to parse
            try:
                content = self.generate_content(prompt)
                # Try to extract JSON from markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                return json.loads(content)
            except Exception as e2:
                print(f"[AIService] OpenAI fallback also failed: {e2}")
                raise


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider with tool-use structured output."""
    
    def __init__(self, api_key: str, model_name: str):
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            self.model_name = model_name
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

    def generate_content(self, prompt: str) -> str:
        message = self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    
    def generate_with_schema(self, prompt: str, response_schema: dict) -> dict:
        """Generate using Anthropic's tool_use for structured output."""
        try:
            # Use tool_use to enforce structured output
            message = self.client.messages.create(
                model=self.model_name,
                max_tokens=4096,
                tools=[{
                    "name": "structured_response",
                    "description": "Return the response in the required structured format",
                    "input_schema": response_schema
                }],
                tool_choice={"type": "tool", "name": "structured_response"},
                messages=[{"role": "user", "content": prompt}]
            )
            # Extract tool use result
            for block in message.content:
                if block.type == "tool_use":
                    return block.input
            raise ValueError("No tool_use block in response")
        except Exception as e:
            print(f"[AIService] Anthropic structured generation failed: {e}")
            # Fallback to regular generation with JSON parsing
            response = self.generate_content(prompt + "\n\nRespond with valid JSON only.")
            return json.loads(response)


class AIService:
    """
    Unified AI Service
    
    Usage:
        # Simple text generation
        text = AIService.generate_content("What is Python?")
        
        # Task-based structured generation (recommended)
        result = AIService.generate_for_task("validate_topic", topic="Machine Learning")
        
        # Direct structured generation
        result = AIService.generate_with_schema(prompt, schema)
    """
    
    MODEL_ALIASES = {
        'gemini-flash': 'gemini-2.0-flash',
        'gemini-pro': 'gemini-2.5-pro',
        'openai-mini': 'gpt-4o-mini',
        'openai-best': 'gpt-4o',
        'claude-sonnet': 'claude-3-5-sonnet-20241022',
        'claude-haiku': 'claude-3-haiku-20240307',
    }

    @staticmethod
    def resolve_model(model_name: str) -> str:
        """Resolve model alias to actual model name."""
        return AIService.MODEL_ALIASES.get(model_name, model_name)

    @staticmethod
    def get_provider(provider_name: str = None, model: str = None) -> AIProvider:
        """
        Get an AI provider instance.
        
        Args:
            provider_name: Override provider (uses ACTIVE_PROVIDER from config if None)
            model: Override model (uses provider default if None)
        """
        provider_type = (provider_name or ACTIVE_PROVIDER).lower()
        provider_config = PROVIDER_DEFAULTS.get(provider_type, PROVIDER_DEFAULTS["gemini"])
        
        if provider_type == 'gemini':
            api_key = current_app.config.get('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY')
            model_name = AIService.resolve_model(model or provider_config["model"])
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set")
            return GeminiProvider(api_key, model_name)
            
        elif provider_type == 'openai':
            api_key = current_app.config.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
            model_name = AIService.resolve_model(model or provider_config["model"])
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set")
            return OpenAIProvider(api_key, model_name)
            
        elif provider_type == 'anthropic':
            api_key = current_app.config.get('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
            model_name = AIService.resolve_model(model or provider_config["model"])
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is not set")
            return AnthropicProvider(api_key, model_name)
            
        elif provider_type == 'perplexity':
            api_key = current_app.config.get('PERPLEXITY_API_KEY') or os.getenv('PERPLEXITY_API_KEY')
            model_name = model or 'llama-3-sonar-large-32k-online'
            if not api_key:
                raise ValueError("PERPLEXITY_API_KEY is not set")
            return OpenAIProvider(api_key, model_name, base_url="https://api.perplexity.ai")
            
        else:
            raise ValueError(f"Unsupported AI provider: {provider_type}")

    @staticmethod
    def generate_content(prompt: str, provider: str = None, model: str = None) -> str:
        """Generate unstructured text content."""
        ai_provider = AIService.get_provider(provider, model)
        return ai_provider.generate_content(prompt)
    
    @staticmethod
    def generate_with_schema(prompt: str, response_schema: dict, provider: str = None, model: str = None) -> dict:
        """Generate structured JSON content using provider-specific schema parameter."""
        ai_provider = AIService.get_provider(provider, model)
        return ai_provider.generate_with_schema(prompt, response_schema)
    
    @staticmethod
    def generate_for_task(task_name: str, **variables) -> dict:
        """
        Generate content for a predefined task from ai_config.py.
        
        This is the RECOMMENDED way to use AI in the application.
        All prompts and schemas are centralized in ai_config.py.
        
        Args:
            task_name: Name of the task (e.g., "validate_topic", "generate_curriculum")
            **variables: Variables to substitute into the prompt template
            
        Returns:
            Structured response as a dictionary
            
        Example:
            result = AIService.generate_for_task(
                "validate_topic",
                topic="Machine Learning"
            )
        """
        # Get task configuration
        config = get_task_config(task_name)
        
        # Format the prompt with variables
        prompt = get_prompt(task_name, **variables)
        
        # Get the schema
        schema = config["response_schema"]
        
        # Get provider (may be task-specific override)
        provider = AIService.get_provider(config["provider"], config["model"])
        
        # Generate with schema
        if schema:
            return provider.generate_with_schema(prompt, schema)
        else:
            # No schema, return text in a dict
            return {"response": provider.generate_content(prompt)}
