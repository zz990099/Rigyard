"""Inline runtime-value acquisition and resolution."""

from .context import ResolvedContext, ResolvedValue, ValueSource
from .models import PromptMerge, PromptMode, PromptSpec, PromptValue
from .resolver import RuntimeValueResolver, collect_prompts
from .sources import DynamicOption, DynamicOptionsProvider, DynamicSources, PromptSource
from .templates import StringTemplateRenderer, TemplateContext, validate_template_syntax

__all__ = [
    "DynamicOption",
    "DynamicOptionsProvider",
    "DynamicSources",
    "PromptMode",
    "PromptMerge",
    "PromptSource",
    "PromptSpec",
    "PromptValue",
    "ResolvedContext",
    "ResolvedValue",
    "RuntimeValueResolver",
    "StringTemplateRenderer",
    "TemplateContext",
    "ValueSource",
    "collect_prompts",
    "validate_template_syntax",
]
