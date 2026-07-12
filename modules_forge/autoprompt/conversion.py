# Adapted from Hugging Face Transformers' official Florence-2 converter:
# https://github.com/huggingface/transformers/blob/63f32a8782cb70da3365acab16f2b67947737985/src/transformers/models/florence2/convert_florence2_original_pytorch_to_hf.py
# Copyright 2025 Microsoft and the HuggingFace Team, Apache-2.0.
from __future__ import annotations

import json
from pathlib import Path

import torch
from accelerate import init_empty_weights
from safetensors.torch import load_file
from transformers import (
    AddedToken,
    BartConfig,
    BartTokenizerFast,
    CLIPImageProcessor,
    Florence2Config,
    Florence2ForConditionalGeneration,
    Florence2Processor,
    Florence2VisionConfig,
)


LEGACY_SPECIAL_TOKENS = (
    ["<od>", "</od>", "<ocr>", "</ocr>"]
    + [f"<loc_{index}>" for index in range(1000)]
    + [
        "<cap>",
        "</cap>",
        "<ncap>",
        "</ncap>",
        "<dcap>",
        "</dcap>",
        "<grounding>",
        "</grounding>",
        "<seg>",
        "</seg>",
        "<sep>",
        "<region_cap>",
        "</region_cap>",
        "<region_to_desciption>",
        "</region_to_desciption>",
        "<proposal>",
        "</proposal>",
        "<poly>",
        "</poly>",
        "<and>",
    ]
)

BLOCK_SUFFIXES = {
    "spatial_block": (
        ("conv1.fn.dw.weight", "conv1.weight"),
        ("conv1.fn.dw.bias", "conv1.bias"),
        ("window_attn.norm.weight", "norm1.weight"),
        ("window_attn.norm.bias", "norm1.bias"),
        ("window_attn.fn.qkv.weight", "window_attn.qkv.weight"),
        ("window_attn.fn.qkv.bias", "window_attn.qkv.bias"),
        ("window_attn.fn.proj.weight", "window_attn.proj.weight"),
        ("window_attn.fn.proj.bias", "window_attn.proj.bias"),
        ("conv2.fn.dw.weight", "conv2.weight"),
        ("conv2.fn.dw.bias", "conv2.bias"),
        ("ffn.norm.weight", "norm2.weight"),
        ("ffn.norm.bias", "norm2.bias"),
        ("ffn.fn.net.fc1.weight", "ffn.fc1.weight"),
        ("ffn.fn.net.fc1.bias", "ffn.fc1.bias"),
        ("ffn.fn.net.fc2.weight", "ffn.fc2.weight"),
        ("ffn.fn.net.fc2.bias", "ffn.fc2.bias"),
    ),
    "channel_block": (
        ("conv1.fn.dw.weight", "conv1.weight"),
        ("conv1.fn.dw.bias", "conv1.bias"),
        ("channel_attn.norm.weight", "norm1.weight"),
        ("channel_attn.norm.bias", "norm1.bias"),
        ("channel_attn.fn.qkv.weight", "channel_attn.qkv.weight"),
        ("channel_attn.fn.qkv.bias", "channel_attn.qkv.bias"),
        ("channel_attn.fn.proj.weight", "channel_attn.proj.weight"),
        ("channel_attn.fn.proj.bias", "channel_attn.proj.bias"),
        ("conv2.fn.dw.weight", "conv2.weight"),
        ("conv2.fn.dw.bias", "conv2.bias"),
        ("ffn.norm.weight", "norm2.weight"),
        ("ffn.norm.bias", "norm2.bias"),
        ("ffn.fn.net.fc1.weight", "ffn.fc1.weight"),
        ("ffn.fn.net.fc1.bias", "ffn.fc1.bias"),
        ("ffn.fn.net.fc2.weight", "ffn.fc2.weight"),
        ("ffn.fn.net.fc2.bias", "ffn.fc2.bias"),
    ),
}


def build_processor_and_config(model_path: str | Path, dtype: torch.dtype):
    model_path = Path(model_path)
    raw_config = json.loads((model_path / "config.json").read_text(encoding="utf-8"))
    tokenizer = BartTokenizerFast.from_pretrained(model_path, local_files_only=True)
    tokenizer.add_special_tokens({"additional_special_tokens": list(LEGACY_SPECIAL_TOKENS)})
    image_token = AddedToken("<image>", special=True, normalized=False)
    tokenizer.add_tokens(image_token, special_tokens=True)
    tokenizer.image_token = "<image>"
    tokenizer.image_token_id = tokenizer.encode("<image>", add_special_tokens=False)[0]

    image_processor = CLIPImageProcessor.from_pretrained(model_path, local_files_only=True)
    processor = Florence2Processor(image_processor=image_processor, tokenizer=tokenizer)

    original_vision = raw_config["vision_config"]
    vision_config = Florence2VisionConfig(
        embed_dim=original_vision["dim_embed"],
        max_temporal_embeddings=original_vision["visual_temporal_embedding"]["max_temporal_embeddings"],
        max_position_embeddings=original_vision["image_pos_embed"]["max_pos_embeddings"],
        **{key: value for key, value in original_vision.items() if key not in {"dim_embed", "visual_temporal_embedding", "image_pos_embed", "model_type"}},
    )
    text_config = BartConfig(**raw_config["text_config"])
    config = Florence2Config(text_config=text_config, vision_config=vision_config, image_token_id=tokenizer.image_token_id, dtype=dtype)
    return processor, config


def _key_pairs(config: Florence2Config, original_keys: set[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for stage_index in range(len(config.vision_config.embed_dim)):
        for suffix in ("weight", "bias"):
            pairs.append((f"vision_tower.convs.{stage_index}.proj.{suffix}", f"model.vision_tower.convs.{stage_index}.conv.{suffix}"))
            pairs.append((f"vision_tower.convs.{stage_index}.norm.{suffix}", f"model.vision_tower.convs.{stage_index}.norm.{suffix}"))
        for block_index in range(config.vision_config.depths[stage_index]):
            for block_name, suffixes in BLOCK_SUFFIXES.items():
                for old_suffix, new_suffix in suffixes:
                    pairs.append(
                        (
                            f"vision_tower.blocks.{stage_index}.{block_index}.{block_name}.{old_suffix}",
                            f"model.vision_tower.blocks.{stage_index}.{block_index}.{block_name}.{new_suffix}",
                        )
                    )

    pairs.extend(
        (
            ("image_projection", "model.multi_modal_projector.image_projection.weight"),
            ("image_proj_norm.weight", "model.multi_modal_projector.image_proj_norm.weight"),
            ("image_proj_norm.bias", "model.multi_modal_projector.image_proj_norm.bias"),
            ("image_pos_embed.row_embeddings.weight", "model.multi_modal_projector.image_position_embed.row_embeddings.weight"),
            ("image_pos_embed.column_embeddings.weight", "model.multi_modal_projector.image_position_embed.column_embeddings.weight"),
            ("visual_temporal_embed.pos_idx_to_embed", "model.multi_modal_projector.visual_temporal_embed.pos_idx_to_embed"),
        )
    )
    pairs.extend((key, key.replace("language_model.model.", "model.language_model.")) for key in original_keys if key.startswith("language_model.model."))
    pairs.append(("language_model.model.shared.weight", "lm_head.weight"))
    pairs.append(("language_model.model.shared.weight", "model.language_model.encoder.embed_tokens.weight"))
    pairs.append(("language_model.model.shared.weight", "model.language_model.decoder.embed_tokens.weight"))
    return pairs


def load_converted_model(model_path: str | Path, config: Florence2Config, tokenizer_length: int, dtype: torch.dtype):
    original = load_file(Path(model_path) / "model.safetensors", device="cpu")
    pairs = _key_pairs(config, set(original))
    converted: dict[str, torch.Tensor] = {}
    for old_key, new_key in pairs:
        if old_key not in original:
            raise RuntimeError(f"В Florence snapshot отсутствует ожидаемый tensor: {old_key}")
        tensor = original[old_key]
        if old_key == "image_projection":
            tensor = tensor.transpose(1, 0)
        if tensor.is_floating_point() and tensor.dtype != dtype:
            tensor = tensor.to(dtype=dtype)
        converted[new_key] = tensor

    with init_empty_weights():
        model = Florence2ForConditionalGeneration(config)
    model.load_state_dict(converted, strict=True, assign=True)
    model.tie_weights()
    model.resize_token_embeddings(tokenizer_length, pad_to_multiple_of=64)
    return model
