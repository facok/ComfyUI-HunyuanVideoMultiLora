"""
Hunyuan Video LoRA Loader
支持选择性加载single blocks或double blocks的混元视频LoRA加载器
"""

from .lora_loader import HunyuanVideoLoraLoader

NODE_CLASS_MAPPINGS = {
    "HunyuanVideoLoraLoader": HunyuanVideoLoraLoader
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "HunyuanVideoLoraLoader": "Hunyuan Video LoRA Loader"
}

__version__ = "1.0.0" 