import os
import torch
import folder_paths
from torchvision.transforms import ToPILImage
from transformers import (
    Qwen3VLForConditionalGeneration,
    AutoProcessor,
    BitsAndBytesConfig,
)
import comfy.model_management
from qwen_vl_utils import process_vision_info
from pathlib import Path


class Qwen3_VQA_Customized:
    def __init__(self):
        self.model_checkpoint = None
        self.processor = None
        self.model = None
        self.device = comfy.model_management.get_torch_device()
        self.bf16_support = (
            torch.cuda.is_available()
            and torch.cuda.get_device_capability(self.device)[0] >= 8
        )

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "system": (
                    "STRING",
                    {
                        "default": "You are QwenVL, you are a helpful assistant expert in turning images into words.",
                        "multiline": True,
                    },
                ),
                "user": ("STRING", {"default": "", "multiline": True}),
                "assistant": ("STRING", {"default": "", "multiline": True}),
                "model": (
                    [
                        "Qwen3-VL-4B-Instruct-FP8",
                        "Qwen3-VL-4B-Thinking-FP8",
                        "Qwen3-VL-8B-Instruct-FP8",
                        "Qwen3-VL-8B-Thinking-FP8",
                        "Qwen3-VL-4B-Instruct",
                        "Qwen3-VL-4B-Thinking",
                        "Qwen3-VL-8B-Instruct",
                        "Qwen3-VL-8B-Thinking",
                    ],
                    {"default": "Qwen3-VL-4B-Instruct-FP8"},
                ),
                "quantization": (
                    ["none", "4bit", "8bit"],
                    {"default": "none"},
                ),  # add quantization type selection
                "keep_model_loaded": ("BOOLEAN", {"default": False}),
                "temperature": (
                    "FLOAT",
                    {"default": 0.7, "min": 0, "max": 1, "step": 0.1},
                ),
                "repetition_penalty": (
                    "FLOAT",
                    {"default": 1.15, "min": 1, "max": 2, "step": 0.01},
                ),
                "max_new_tokens": (
                    "INT",
                    {"default": 2048, "min": 128, "max": 256000, "step": 1},
                ),
                "min_pixels": (
                    "INT",
                    {
                        "default": 256 * 28 * 28,
                        "min": 4 * 28 * 28,
                        "max": 16384 * 28 * 28,
                        "step": 28 * 28,
                    },
                ),
                "max_pixels": (
                    "INT",
                    {
                        "default": 1280 * 28 * 28,
                        "min": 4 * 28 * 28,
                        "max": 16384 * 28 * 28,
                        "step": 28 * 28,
                    },
                ),
                "seed": ("INT", {"default": -1}),  # add seed parameter, default is -1
                "attention": (
                    [
                        "eager",
                        "sdpa",
                        "flash_attention_2",
                    ],
                )
            },
            "optional": {"source_path": ("PATH",), "image": ("IMAGE",)},
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "inference"
    CATEGORY = "Comfyui_Qwen3-VL-Instruct"

    def inference(
        self,
        system,
        user,
        assistant,
        model,
        keep_model_loaded,
        temperature,
        repetition_penalty,
        max_new_tokens,
        min_pixels,
        max_pixels,
        seed,
        quantization,
        source_path=None,
        image=None,  # add image parameter
        attention="eager",
    ):
        if seed != -1:
            torch.manual_seed(seed)
        model_id = f"qwen/{model}"
        self.model_checkpoint = os.path.join(
            folder_paths.models_dir, "prompt_generator", os.path.basename(model_id)
        )

        if not os.path.exists(self.model_checkpoint):
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=model_id,
                local_dir=self.model_checkpoint,
                local_dir_use_symlinks=False,
            )

        if self.processor is None:
            # The default range for the number of visual tokens per image in the model is 4-16384. You can set min_pixels and max_pixels according to your needs, such as a token count range of 256-1280, to balance speed and memory usage.
            self.processor = AutoProcessor.from_pretrained(
                self.model_checkpoint, min_pixels=min_pixels, max_pixels=max_pixels
            )

        if self.model is None:
            # Load the model on the available device(s)
            if quantization == "4bit":
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                )
            elif quantization == "8bit":
                quantization_config = BitsAndBytesConfig(
                    load_in_8bit=True,
                )
            else:
                quantization_config = None

            self.model = Qwen3VLForConditionalGeneration.from_pretrained(
                self.model_checkpoint,
                dtype=torch.bfloat16 if self.bf16_support else torch.float16,
                device_map="auto",
                attn_implementation=attention,
                quantization_config=quantization_config,
            )

        temp_path = None
        if image is not None:
            pil_image = ToPILImage()(image[0].permute(2, 0, 1))
            temp_path = Path(folder_paths.temp_directory) / f"temp_image_{seed}.png"
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            pil_image.save(temp_path)

        with torch.no_grad():
            messages = [
                {
                    "role": "system",
                    "content": system,
                },
            ]
            if source_path:
                messages += [
                    {
                        "role": "user",
                        "content": source_path
                        + [
                            {"type": "text", "text": user},
                        ],
                    },
                ]
            elif temp_path:
                messages += [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": f"file://{temp_path}"},
                            {"type": "text", "text": user},
                        ],
                    },
                ]
                # raise ValueError("Either image or video must be provided")
            else:
                messages += [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user},
                        ],
                    }
                ]
            if assistant.strip() != "":
                messages += [
                    {
                        "role": "assistant",
                        "content": assistant,
                    }
                ]
                # Preparation for inference
                text = self.processor.apply_chat_template(
                    messages, tokenize=False, continue_final_message=True
                )
            else:
                # Preparation for inference
                text = self.processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True,
                )

            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )
            inputs = inputs.to(self.device)
            # Inference: Generation of the output
            generated_ids = self.model.generate(
                **inputs, max_new_tokens=max_new_tokens, temperature=temperature, repetition_penalty=repetition_penalty
            )
            generated_ids_trimmed = [
                out_ids[len(in_ids) :]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            result = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
                temperature=temperature,
            )

            if not keep_model_loaded:
                del self.processor  # release processor memory
                del self.model  # release model memory
                self.processor = None  # set processor to None
                self.model = None  # set model to None
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()  # release GPU memory
                    torch.cuda.ipc_collect()

            return (result,)
