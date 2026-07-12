from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentSpec:
    id: str
    label: str
    kind: str
    repository: str
    revision: str
    repository_path: str
    filename: str
    size: int
    sha256: str
    license: str
    embedded_markers: tuple[str, ...]

    @property
    def source_url(self) -> str:
        return f"https://huggingface.co/{self.repository}/resolve/{self.revision}/{self.repository_path}?download=true"


@dataclass(frozen=True)
class FamilyBundle:
    repository: str
    preset: str
    label: str
    component_ids: tuple[str, ...]


def _component(id, label, kind, repository, revision, repository_path, filename, size, sha256, license, *markers):
    return ComponentSpec(id, label, kind, repository, revision, repository_path, filename, size, sha256, license, tuple(markers))


# Sources and revisions follow Forge Neo's Download Models table (2026-06-28).
# Every file is pinned by repository commit, exact byte size and SHA-256.
COMPONENTS = {
    item.id: item
    for item in (
        _component("sd1_vae", "VAE SD 1.x", "vae", "stabilityai/sd-vae-ft-mse-original", "629b3ad3030ce36e15e70c5db7d91df0d60c627f", "vae-ft-mse-840000-ema-pruned.safetensors", "vae-ft-mse-840000-ema-pruned.safetensors", 334641190, "735e4c3a447a3255760d7f86845f09f937809baa529c17370d83e4c3758f3c75", "MIT", "first_stage_model.", "vae."),
        _component("sdxl_vae", "VAE SDXL", "vae", "madebyollin/sdxl-vae-fp16-fix", "207b116dae70ace3637169f1ddd2434b91b3a8cd", "sdxl_vae.safetensors", "sdxl_vae.safetensors", 334641162, "235745af8d86bf4a4c1b5b4f529868b37019a10f7c0b2e79ad0abca3a22bc6e1", "MIT", "first_stage_model.", "vae."),
        _component("flux_ae", "Flux AE", "vae", "Comfy-Org/Lumina_Image_2.0_Repackaged", "22e393d707f2d13e736b1a461c958644258cd9d9", "split_files/vae/ae.safetensors", "ae.safetensors", 335304388, "afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38", "см. исходную лицензию модели", "vae."),
        _component("clip_l", "CLIP-L", "text_encoder", "comfyanonymous/flux_text_encoders", "6af2a98e3f615bdfa612fbd85da93d1ed5f69ef5", "clip_l.safetensors", "clip_l.safetensors", 246144152, "660c6f5b1abae9dc498ac2d21e1347d2abdb0cf6c0c0c8576cd796491d9a6cdd", "Apache-2.0", "text_encoders.clip_l.", "clip_l."),
        _component("t5xxl", "T5-XXL FP8 scaled", "text_encoder", "comfyanonymous/flux_text_encoders", "6af2a98e3f615bdfa612fbd85da93d1ed5f69ef5", "t5xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors", 5157348688, "a498f0485dc9536735258018417c3fd7758dc3bccc0a645feaa472b34955557a", "Apache-2.0", "text_encoders.t5xxl.", "t5xxl."),
        _component("gemma2_2b", "Gemma 2 2B FP16", "text_encoder", "duongve/NetaYume-Lumina-Image-2.0", "69c29c441119d43405d8373c654b16827d3cf46e", "Text_Encoder/gemma_2_2b_fp16.safetensors", "gemma_2_2b_fp16.safetensors", 5232958283, "29761442862f8d064d3f854bb6fabf4379dcff511a7f6ba9405a00bd0f7e2dbd", "Apache-2.0", "text_encoders.gemma2_2b.", "gemma2_2b."),
        _component("qwen3_4b", "Qwen3 4B", "text_encoder", "Comfy-Org/z_image_turbo", "d24c4cf2a0cd98a42f23467e27e3d76ee9438b8e", "split_files/text_encoders/qwen_3_4b.safetensors", "qwen_3_4b.safetensors", 8044982048, "6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a", "Apache-2.0 (Qwen3)", "text_encoders.qwen3_4b.", "qwen3_4b."),
        _component("flux2_decoder", "Flux.2 VAE / small decoder", "vae", "black-forest-labs/FLUX.2-small-decoder", "a3efc24f613ef42d9428af62fdbd6f5fd8856c4a", "full_encoder_small_decoder.safetensors", "full_encoder_small_decoder.safetensors", 249519092, "ea4273f02d1fafbf8e1d1c2cf6018ed8748652eb0bf34f2dd91171f16f15ab62", "Apache-2.0", "vae."),
        _component("qwen3_8b", "Qwen3 8B", "text_encoder", "Comfy-Org/vae-text-encorder-for-flux-klein-9b", "23fbc8aa8b621f29f2249cd1bd9c47e5d0eebd83", "split_files/text_encoders/qwen_3_8b.safetensors", "qwen_3_8b.safetensors", 16381517176, "f0ff9239d56269ca1d05e5f86da6a79fac111af464955681f11c7ab0ec5ef6c1", "Apache-2.0 (Qwen3)", "text_encoders.qwen3_8b.", "qwen3_8b."),
        _component("ministral3_3b", "Ministral 3 3B", "text_encoder", "Comfy-Org/ERNIE-Image", "629188faf9dc5248753bd1ebec50ef9452f2b162", "text_encoders/ministral-3-3b.safetensors", "ministral-3-3b.safetensors", 7717637511, "49a750a128863854eac7d85e1a277a7b44bf6ec3646405b84686dfeeca3708ca", "Apache-2.0", "text_encoders.ministral3_3b.", "ministral3_3b."),
        _component("umt5_xxl", "UMT5-XXL FP8 scaled", "text_encoder", "Comfy-Org/Wan_2.1_ComfyUI_repackaged", "06e001fc51048fb03433a6fb25334de7836704a5", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "umt5_xxl_fp8_e4m3fn_scaled.safetensors", 6735906897, "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68", "Apache-2.0 (Wan)", "text_encoders.umt5xxl.", "umt5xxl."),
        _component("wan_vae", "Wan 2.1 VAE", "vae", "Comfy-Org/Wan_2.1_ComfyUI_repackaged", "06e001fc51048fb03433a6fb25334de7836704a5", "split_files/vae/wan_2.1_vae.safetensors", "wan_2.1_vae.safetensors", 253815318, "2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b", "Apache-2.0 (Wan)", "vae."),
        _component("qwen25_vl_7b", "Qwen 2.5 VL 7B FP8 scaled", "text_encoder", "Comfy-Org/Qwen-Image_ComfyUI", "46839d338df81ce625d5fae27d7e370314c0fbc9", "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", "qwen_2.5_vl_7b_fp8_scaled.safetensors", 9384670680, "cb5636d852a0ea6a9075ab1bef496c0db7aef13c02350571e388aea959c5c0b4", "Apache-2.0", "text_encoders.qwen25_7b.", "qwen25_7b."),
        _component("qwen_image_vae", "Qwen Image VAE", "vae", "Comfy-Org/Qwen-Image_ComfyUI", "46839d338df81ce625d5fae27d7e370314c0fbc9", "split_files/vae/qwen_image_vae.safetensors", "qwen_image_vae.safetensors", 253806246, "a70580f0213e67967ee9c95f05bb400e8fb08307e017a924bf3441223e023d1f", "Apache-2.0", "vae."),
        _component("qwen3_06b", "Qwen3 0.6B", "text_encoder", "circlestone-labs/Anima", "53eec3898af698b2cf2a11379021fc9c5465d228", "split_files/text_encoders/qwen_3_06b_base.safetensors", "qwen_3_06b_base.safetensors", 1192135096, "cd2a512003e2f9f3cd3c32a9c3573f820bb28c940f73c57b1ddaa983d9223eba", "Anima model license", "text_encoders.qwen3_06b.", "qwen3_06b."),
        _component("qwen3vl_4b", "Qwen3-VL 4B FP8 scaled", "text_encoder", "Comfy-Org/Krea-2", "8038ce89b91b042141541ad0fa51b985ca262c5f", "text_encoders/qwen3vl_4b_fp8_scaled.safetensors", "qwen3vl_4b_fp8_scaled.safetensors", 5242467968, "54bd5144df0bbc25dd6ccadfcb826b521445a1b06ae5a42570bdd2974ca87094", "Apache-2.0 (Qwen3-VL)", "text_encoders.qwen3vl_4b.", "qwen3vl_4b."),
        _component("gemma2_2b_it", "Gemma 2 2B IT FP8 scaled", "text_encoder", "Comfy-Org/PixelDiT", "88ececd3dd61b9768e7160a2308b5e9875209e83", "text_encoders/gemma_2_2b_it_elm_fp8_scaled.safetensors", "gemma_2_2b_it_elm_fp8_scaled.safetensors", 2618902308, "87692b2ab1714028e29910ea645d96db656505ca0805051048d2298b225c02d1", "NVIDIA Open Model License / Gemma terms", "text_encoders.gemma2_2b.", "gemma2_2b."),
    )
}


FAMILY_BUNDLES = {
    item.repository: item
    for item in (
        FamilyBundle("runwayml/stable-diffusion-v1-5", "sd", "SD 1.x", ("sd1_vae",)),
        FamilyBundle("stabilityai/stable-diffusion-xl-base-1.0", "xl", "SDXL", ("sdxl_vae",)),
        FamilyBundle("stabilityai/stable-diffusion-xl-refiner-1.0", "xl", "SDXL Refiner", ("sdxl_vae",)),
        FamilyBundle("black-forest-labs/FLUX.1-dev", "flux", "Flux.1", ("clip_l", "t5xxl", "flux_ae")),
        FamilyBundle("black-forest-labs/FLUX.1-schnell", "flux", "Flux.1 Schnell", ("clip_l", "t5xxl", "flux_ae")),
        FamilyBundle("black-forest-labs/FLUX.2-klein-4B", "klein", "Flux.2 Klein 4B", ("qwen3_4b", "flux2_decoder")),
        FamilyBundle("black-forest-labs/FLUX.2-klein-9B", "klein", "Flux.2 Klein 9B", ("qwen3_8b", "flux2_decoder")),
        FamilyBundle("neta-art/Neta-Lumina", "lumina", "Lumina Image 2", ("gemma2_2b", "flux_ae")),
        FamilyBundle("Tongyi-MAI/Z-Image-Turbo", "zit", "Z-Image", ("qwen3_4b", "flux_ae")),
        FamilyBundle("circlestone-labs/Anima", "anima", "Anima", ("qwen3_06b", "qwen_image_vae")),
        FamilyBundle("Wan-AI/Wan2.1-T2V-14B", "wan", "Wan T2V", ("umt5_xxl", "wan_vae")),
        FamilyBundle("Wan-AI/Wan2.1-I2V-14B", "wan", "Wan I2V", ("umt5_xxl", "wan_vae")),
        FamilyBundle("Qwen/Qwen-Image", "qwen", "Qwen Image", ("qwen25_vl_7b", "qwen_image_vae")),
        FamilyBundle("krea/Krea-2-Raw", "krea", "Krea 2", ("qwen3vl_4b", "qwen_image_vae")),
        FamilyBundle("baidu/ERNIE-Image", "ernie", "Ernie Image", ("ministral3_3b", "flux2_decoder")),
        FamilyBundle("nvidia/PiD", "pid", "PiD", ("gemma2_2b_it",)),
    )
}


# Alternative files explicitly listed by the same Forge Neo compatibility table.
# They count as installed, but Atlas downloads only the pinned default above.
COMPONENT_ALIASES = {
    "t5xxl": ("t5xxl_fp16.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors"),
    "qwen3_4b": ("qwen_3_4b.safetensors", "qwen3_4b_fp8_scaled.safetensors"),
    "flux2_decoder": ("flux2-vae.safetensors", "full_encoder_small_decoder.safetensors"),
    "qwen3_8b": ("qwen_3_8b.safetensors", "qwen_3_8b_fp8mixed.safetensors"),
    "umt5_xxl": ("umt5_xxl_fp16.safetensors", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    "qwen_image_vae": ("qwen_image_vae.safetensors", "qwen2d_vae.safetensors"),
    "qwen3vl_4b": ("qwen3vl_4b_bf16.safetensors", "qwen3vl_4b_fp8_scaled.safetensors"),
    "gemma2_2b_it": ("gemma_2_2b_it_elm_bf16.safetensors", "gemma_2_2b_it_elm_fp8_scaled.safetensors"),
}
