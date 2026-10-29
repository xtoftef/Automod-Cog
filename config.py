"""
Master config file for the cog (does not care about the config of the bot itself)
"""
from typing import TYPE_CHECKING, Literal, TypedDict
from utils import get_env_bool

from src.memory_manager_implementations import JSONMemoryManager
from src.automod_components.image_rate_limiter import ImageRateLimiterComponent, ImageRateLimiterComponentConfig
from src.automod_components.reply_chain_prevention import ReplyChainPreventionComponent, ReplyChainPreventionComponentConfig
from DiscordUI.modals import EditImageRateLimiterSpecificModal, EditChainPreventionSpecificModal

# =============================================================================
# TYPED DICTIONARY DECLARATIONS
# =============================================================================
class CogConfigDict(TypedDict):
    engine : EngineConfigDict
    memory: BaseAutomodMemoryManager

class EngineConfigDict(TypedDict):
    components : dict[str,ComponentDict]

class ComponentDict(TypedDict):
    activate : bool
    config_type : type[BaseAutomodComponentConfig]
    component_type : type[BaseAutomodComponent]
    modal_type : type[BaseComponentSpecificModal]


# =============================================================================
# CONFIG VARIABLES/CONSTANTS
# =============================================================================

TEST = get_env_bool("TESTING", True)

MEMORY = JSONMemoryManager("guild_data.json")

ENGINE_CONFIG : EngineConfigDict = {
    "components" : {
        "image_rate_limiter" : {
            "activate" : True, # Set to false to prevent the automod engine from loading this config
            "config_type" : ImageRateLimiterComponentConfig,
            "component_type" : ImageRateLimiterComponent,
            "modal_type" : EditImageRateLimiterSpecificModal 
        },
        "reply_chain_prevention" : {
            "activate" : True,
            "config_type" : ReplyChainPreventionComponentConfig,
            "component_type" : ReplyChainPreventionComponent,
            "modal_type" : EditChainPreventionSpecificModal
        }

    }
}

COG_CONFIG : CogConfigDict = {
    "engine" : ENGINE_CONFIG,
    "memory" : MEMORY,
}

if TYPE_CHECKING:
    from DiscordUI.modals import BaseComponentSpecificModal
    from src.automod_models import BaseAutomodComponentConfig, BaseAutomodComponent, BaseAutomodMemoryManager
    

# =============================================================================
# USEFUL FUNCTIONS
# =============================================================================

def get_component_related_class(component_key: str, return_class: Literal['config_type', 'component_type', 'modal_type']) -> type[BaseAutomodComponent] | type[BaseAutomodComponentConfig] | type[BaseComponentSpecificModal]:
    "Router that returns the callable class of a specific component implementation from its key."

    try:
        component_related_type = ENGINE_CONFIG["components"][component_key][return_class]
        return component_related_type
    except KeyError as e:
        raise KeyError(f"Invalid component key was passed ({component_key}). Valid component keys include the following: {", ".join([key for key in ENGINE_CONFIG['components'].keys()])}")

def verify_key_matching(components: dict[str, ComponentDict]):
    "Checks if the keys of added components are matching"
    key_mismatches = ["Format: engine config key - config class key - component class key - modal class key\n"]
    for component_key, component_dict in components.items():
        ConfigClass_key = component_dict["config_type"].COMPONENT_KEY
        ComponentClass_key = component_dict['component_type'].COMPONENT_KEY
        ModalClass_key = component_dict['modal_type'].COMPONENT_KEY
        key_match = (component_key == ConfigClass_key == ComponentClass_key == ModalClass_key)

        if not key_match:
            key_mismatches.append((
                f"Key mismatch: {component_key} - {ConfigClass_key} - {ComponentClass_key} - {ModalClass_key}\n"
            ))

    if len(key_mismatches) > 1:
        raise ValueError(f"The keys found in the ENGINE_CONFIG dictionary are not matching with their respective components:\n{"".join(key_mismatches)}")

verify_key_matching(ENGINE_CONFIG["components"]) # leaving this there, though it might need to be moved somewhere more reliable to 
# actually do the validation BEFORE the bot is even fired.
