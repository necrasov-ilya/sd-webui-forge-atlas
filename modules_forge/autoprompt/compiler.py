from __future__ import annotations

import html
import re
import unicodedata


DEFAULT_PROMPT = "balanced composition, natural light, cohesive color palette, consistent texture, refined detail"

SCENE_TERMS = {
    "portrait": ("portrait", "headshot", "close-up", "close up", "face"),
    "landscape": ("landscape", "mountain", "valley", "forest", "field", "countryside"),
    "seascape": ("seascape", "ocean", "sea", "coast", "beach"),
    "cityscape": ("cityscape", "city", "urban", "street", "skyline"),
    "architectural scene": ("architecture", "architectural", "building", "interior", "room"),
    "still life": ("still life",),
    "natural scene": ("nature", "wildlife", "animal", "plant", "garden"),
}

MEDIUM_TERMS = {
    "photograph": ("photo", "photograph", "photographic", "camera"),
    "digital illustration": ("digital art", "digital illustration", "illustration"),
    "anime artwork": ("anime", "manga"),
    "oil painting": ("oil painting", "painted in oil", "oil on canvas"),
    "watercolor painting": ("watercolor", "watercolour"),
    "traditional painting": ("painting", "painted", "canvas"),
    "3D render": ("3d", "render", "cgi"),
    "graphic design": ("graphic design", "poster", "vector"),
}

COMPOSITION_TERMS = {
    "close-up composition": ("close-up", "close up", "macro"),
    "portrait composition": ("portrait composition", "portrait orientation"),
    "wide composition": ("wide shot", "wide-angle", "wide angle", "panorama", "panoramic"),
    "full-scene composition": ("full shot", "long shot", "full scene"),
    "centered composition": ("centered", "symmetrical", "symmetry"),
    "dynamic composition": ("dynamic composition", "dramatic angle", "diagonal composition"),
}

LIGHT_TERMS = {
    "soft diffused light": ("soft light", "diffused", "overcast", "gentle light"),
    "dramatic directional light": ("dramatic light", "directional light", "chiaroscuro", "hard light"),
    "warm golden light": ("golden hour", "warm light", "sunset light"),
    "cool ambient light": ("cool light", "blue light", "moonlight"),
    "neon lighting": ("neon",),
    "natural light": ("natural light", "daylight", "sunlight"),
    "studio lighting": ("studio light", "studio lighting"),
}

PALETTE_TERMS = {
    "warm color palette": ("warm palette", "warm colors", "warm tones"),
    "cool color palette": ("cool palette", "cool colors", "cool tones"),
    "muted color palette": ("muted", "desaturated", "subdued colors"),
    "vibrant color palette": ("vibrant", "saturated", "colorful", "colourful"),
    "monochrome palette": ("monochrome", "black and white", "grayscale", "greyscale"),
    "pastel color palette": ("pastel",),
    "earthy color palette": ("earth tones", "earthy"),
}

TONE_TERMS = {
    "high contrast": ("high contrast", "strong contrast"),
    "low contrast": ("low contrast", "soft contrast"),
    "cinematic atmosphere": ("cinematic",),
    "calm atmosphere": ("calm", "serene", "peaceful", "tranquil"),
    "moody atmosphere": ("moody", "somber", "melancholic"),
    "dreamlike atmosphere": ("dreamlike", "dreamy", "ethereal", "surreal"),
    "energetic atmosphere": ("energetic", "lively", "vibrant atmosphere"),
}

TEXTURE_TERMS = {
    "fine natural texture": ("fine texture", "natural texture", "subtle texture"),
    "visible brushwork": ("brushwork", "brush strokes", "brushstrokes"),
    "smooth rendering": ("smooth rendering", "smooth gradients", "clean rendering"),
    "crisp detail": ("crisp", "sharp detail", "highly detailed", "intricate detail"),
    "soft detail": ("soft focus", "soft detail", "painterly detail"),
    "film grain": ("film grain", "grainy", "analog texture"),
}


def _normalise(raw_caption: str) -> str:
    text = html.unescape(raw_caption or "")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[\[({]\s*\d+(?:[.,]\s*\d+)+\s*[\])}]", " ", text)
    text = re.sub(r"[\"“”«»][^\"“”«»]{1,80}[\"“”«»]", " ", text)
    text = re.sub(r"\b\d+(?:[.,:/-]\d+)*\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-")
    return text


def _matches(text: str, categories: dict[str, tuple[str, ...]], maximum: int = 1) -> list[str]:
    lowered = text.casefold()
    found = []
    for output, aliases in categories.items():
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered) for alias in aliases):
            found.append(output)
            if len(found) >= maximum:
                break
    return found


def compile_tile_safe_prompt(raw_caption: str, max_length: int = 320) -> str:
    """Compile a caption into deterministic global visual properties only."""
    if max_length < 80:
        raise ValueError("Максимальная длина промпта должна быть не меньше 80 символов.")
    text = _normalise(raw_caption)
    if not text:
        return DEFAULT_PROMPT[:max_length]

    candidates: list[str] = []
    for categories, maximum in (
        (MEDIUM_TERMS, 1),
        (SCENE_TERMS, 1),
        (COMPOSITION_TERMS, 1),
        (LIGHT_TERMS, 1),
        (PALETTE_TERMS, 1),
        (TONE_TERMS, 2),
        (TEXTURE_TERMS, 2),
    ):
        candidates.extend(_matches(text, categories, maximum))

    if not any(item in candidates for item in LIGHT_TERMS):
        candidates.append("cohesive lighting")
    if not any(item in candidates for item in PALETTE_TERMS):
        candidates.append("cohesive color palette")
    if not any(item in candidates for item in TEXTURE_TERMS):
        candidates.append("consistent texture")
    candidates.append("refined global detail")

    unique: list[str] = []
    for candidate in candidates:
        if candidate.casefold() not in {item.casefold() for item in unique}:
            unique.append(candidate)
    while unique and len(", ".join(unique)) > max_length:
        unique.pop()
    return ", ".join(unique) or DEFAULT_PROMPT[:max_length]
