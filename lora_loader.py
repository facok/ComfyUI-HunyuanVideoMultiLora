import os
import folder_paths
import torch
from typing import Dict

class HunyuanVideoLoraLoader:
    """
    混元视频LoRA加载器,支持选择性加载blocks
    
    这个节点允许您:
    1. 从下拉列表选择LoRA文件
    2. 调整LoRA的强度
    3. 选择要加载的blocks类型(all/single/double)
    """
    
    def __init__(self):
        self.blocks_type = ["all", "single_blocks", "double_blocks"]
        self.loaded_lora = None
        
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",),
                "lora_name": (folder_paths.get_filename_list("loras"),),
                "strength": ("FLOAT", {
                    "default": 1.0,
                    "min": -10.0,
                    "max": 10.0,
                    "step": 0.01,
                    "display": "number"
                }),
                "blocks_type": (["all", "single_blocks", "double_blocks"],),
            }
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "load_lora"
    CATEGORY = "loaders/hunyuan"
    OUTPUT_NODE = False
    DESCRIPTION = "加载并应用混元视频LoRA,支持选择性加载single blocks或double blocks"

    def convert_key_format(self, key: str) -> str:
        """转换LoRA key格式,支持多种命名方式"""
        # 移除可能的前缀
        prefixes = ["diffusion_model.", "transformer."]
        for prefix in prefixes:
            if key.startswith(prefix):
                key = key[len(prefix):]
                break
                
        return key

    def filter_lora_keys(self, lora: Dict[str, torch.Tensor], blocks_type: str) -> Dict[str, torch.Tensor]:
        """根据blocks类型过滤LoRA权重"""
        if blocks_type == "all":
            return lora
            
        filtered_lora = {}
        for key, value in lora.items():
            base_key = self.convert_key_format(key)
            
            # 检查是否包含目标block
            if blocks_type == "single_blocks" in base_key:
                filtered_lora[key] = value
            elif blocks_type == "double_blocks" in base_key:
                filtered_lora[key] = value
                
        return filtered_lora

    def check_for_musubi(self, lora: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """Checks for and converts from Musubi Tuner format which supports Network Alpha and uses different naming. Largely copied from that project"""
        prefix = "lora_unet_"
        musubi = False
        lora_alphas = {}
        for key, value in lora.items():
            if key.startswith(prefix):
                lora_name = key.split(".", 1)[0]  # before first dot
                if lora_name not in lora_alphas and "alpha" in key:
                    lora_alphas[lora_name] = value
                    musubi = True
        if musubi:
            print("Loading Musubi Tuner format LoRA...")
            converted_lora = {}
            for key, weight in lora.items():
                if key.startswith(prefix):
                    if "alpha" in key:
                        continue
                    lora_name = key.split(".", 1)[0]  # before first dot
                    # HunyuanVideo lora name to module name: ugly but works
                    module_name = lora_name[len(prefix) :]  # remove "lora_unet_"
                    module_name = module_name.replace("_", ".")  # replace "_" with "."
                    module_name = module_name.replace("double.blocks.", "double_blocks.")  # fix double blocks
                    module_name = module_name.replace("single.blocks.", "single_blocks.")  # fix single blocks
                    module_name = module_name.replace("img.", "img_")  # fix img
                    module_name = module_name.replace("txt.", "txt_")  # fix txt
                    module_name = module_name.replace("attn.", "attn_")  # fix attn
                    diffusers_prefix = "diffusion_model"
                    if "lora_down" in key:
                        new_key = f"{diffusers_prefix}.{module_name}.lora_A.weight"
                        dim = weight.shape[0]
                    elif "lora_up" in key:
                        new_key = f"{diffusers_prefix}.{module_name}.lora_B.weight"
                        dim = weight.shape[1]
                    else:
                        print(f"unexpected key: {key} in Musubi LoRA format")
                        continue
                    # scale weight by alpha
                    if lora_name in lora_alphas:
                        # we scale both down and up, so scale is sqrt
                        scale = lora_alphas[lora_name] / dim
                        scale = scale.sqrt()
                        weight = weight * scale
                    else:
                        print(f"missing alpha for {lora_name}")
                    converted_lora[new_key] = weight
            return converted_lora
        else:
            print("Loading Diffusers format LoRA...")
            return lora

    def load_lora(self, model, lora_name: str, strength: float, blocks_type: str):
        """
        加载并应用LoRA到模型
        
        Parameters
        ----------
        model : ModelPatcher
            要应用LoRA的基础模型
        lora_name : str
            LoRA文件名
        strength : float
            LoRA权重强度
        blocks_type : str
            要加载的blocks类型: "all", "single_blocks" 或 "double_blocks"
            
        Returns
        -------
        tuple
            包含应用了LoRA的模型的元组
        """
        if not lora_name:
            return (model,)
            
        from comfy.utils import load_torch_file
        from comfy.sd import load_lora_for_models
        from comfy.lora import load_lora

        # 获取LoRA文件路径
        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not os.path.exists(lora_path):
            raise Exception(f"Lora {lora_name} not found at {lora_path}")

        # 缓存LoRA加载
        if self.loaded_lora is not None:
            if self.loaded_lora[0] == lora_path:
                lora = self.loaded_lora[1]
            else:
                self.loaded_lora = None
        
        if self.loaded_lora is None:
            lora = load_torch_file(lora_path)
            self.loaded_lora = (lora_path, lora)
        
        diffusers_lora = self.check_for_musubi(lora)
        # 过滤并转换LoRA权重
        filtered_lora = self.filter_lora_keys(diffusers_lora, blocks_type)
        
        # 应用LoRA
        new_model, _ = load_lora_for_models(model, None, filtered_lora, strength, 0)
        if new_model is not None:
            return (new_model,)
            
        return (model,)

    @classmethod
    def IS_CHANGED(s, model, lora_name, strength, blocks_type):
        """当LoRA的配置发生变化时重新执行"""
        return f"{lora_name}_{strength}_{blocks_type}" 