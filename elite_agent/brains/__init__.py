"""Brain modules for email classification and routing."""

from __future__ import annotations

import importlib

from elite_agent.brains.base import BaseBrain


def load_brain(cfg) -> BaseBrain:
    """
    Load a brain implementation based on configuration.

    Args:
        cfg: Config object with 'brain' field (defaults to "olympic")

    Returns:
        BaseBrain instance

    Raises:
        ImportError: If the brain module cannot be imported
        AttributeError: If get_brain() function is not found in the module
    """
    brain_name = getattr(cfg, "brain", "olympic")

    if brain_name == "olympic":
        # Built-in Olympic brain
        from elite_agent.brains.olympic import get_brain
        return get_brain(cfg)
    else:
        # Dynamic import via dotted path
        try:
            # Assume brain_name is a dotted path like "my.custom.brain"
            module = importlib.import_module(brain_name)
            get_brain = getattr(module, "get_brain")
            return get_brain(cfg)
        except (ImportError, AttributeError) as e:
            raise ImportError(
                f"Could not load brain '{brain_name}': {e}"
            ) from e
