from .nodes import Qwen3_VQA_Customized

# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {
    "Qwen3_VQA_Customized": Qwen3_VQA_Customized,
}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "Qwen3_VQA_Customized": "Qwen3 VQA Customized",
}
