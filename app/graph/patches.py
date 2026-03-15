"""State patch system for concurrent node execution."""

from typing import Dict, Any, List, Union
import logging

logger = logging.getLogger(__name__)


class StatePatch:
    """Represents changes to be applied to workflow state."""
    
    def __init__(self):
        self.sets: Dict[str, Any] = {}
        self.appends: Dict[str, List[Any]] = {}
        self.deltas: Dict[str, Union[int, float]] = {}
        self.node_name: str = "unknown"
    
    def set(self, key: str, value: Any):
        """Set a scalar value."""
        self.sets[key] = value
        return self
    
    def append(self, key: str, items: List[Any]):
        """Append items to a list."""
        if key not in self.appends:
            self.appends[key] = []
        self.appends[key].extend(items)
        return self
    
    def delta(self, key: str, change: Union[int, float]):
        """Add numeric delta."""
        self.deltas[key] = self.deltas.get(key, 0) + change
        return self
    
    def from_node(self, node_name: str):
        """Set the source node name."""
        self.node_name = node_name
        return self


def merge_patches(state: Dict[str, Any], patches: List[StatePatch]) -> Dict[str, Any]:
    """
    Merge patches into state in a deterministic order.
    
    Args:
        state: Current workflow state
        patches: List of patches to apply
        
    Returns:
        Updated state
    """
    # Process patches in deterministic order
    node_order = ["customer_node", "market_node", "policy_rag_node"]
    ordered_patches = []
    
    # Sort patches by node order
    for node_name in node_order:
        for patch in patches:
            if patch.node_name == node_name:
                ordered_patches.append(patch)
                break
    
    # Add any patches not in the order (shouldn't happen)
    for patch in patches:
        if patch not in ordered_patches:
            ordered_patches.append(patch)
    
    # Apply patches
    for patch in ordered_patches:
        # Apply sets
        for key, value in patch.sets.items():
            if key in state and key != patch.sets.get(key):
                logger.info(f"patch_overwrite key={key} from_node={patch.node_name}")
            state[key] = value
        
        # Apply appends
        for key, items in patch.appends.items():
            if key not in state:
                state[key] = []
            state[key].extend(items)
        
        # Apply deltas
        for key, delta in patch.deltas.items():
            current = state.get(key, 0)
            state[key] = max(0.0, min(1.0, current + delta)) if isinstance(delta, float) else current + delta
    
    return state


def enforce_readonly_keys(patches: List[StatePatch], forbidden_keys: List[str]):
    """Enforce that certain keys are not written during data gathering phase."""
    for patch in patches:
        for forbidden in forbidden_keys:
            if forbidden in patch.sets:
                raise ValueError(f"Node {patch.node_name} illegally tried to set read-only key '{forbidden}'")
