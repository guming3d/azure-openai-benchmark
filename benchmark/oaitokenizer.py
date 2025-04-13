# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import base64
import logging
from io import BytesIO
from importlib.metadata import version

import tiktoken
from PIL import Image
import google.generativeai as genai

IMG_BASE_TOKENS_PER_IMG = 85
IMG_HQ_TOKENS_PER_TILE = 170
IMG_TILE_SIZE = 512


def num_tokens_from_text(text, model):
    """Return the number of tokens used by text."""

    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def calc_num_img_patches(width: int, height: int) -> int:
    # Instructions copied from https://platform.openai.com/docs/guides/vision/calculating-costs
    # 1. images are first scaled to fit within a 2048 x 2048 square, maintaining their aspect ratio
    max_side = max(width, height)
    scaling_factor = min(1, 2048 / max_side)
    scaled_width, scaled_height = int(width * scaling_factor), int(height * scaling_factor)
    # 2. Then, they are scaled such that the shortest side of the image is 768px long
    min_side = min(scaled_width, scaled_height)
    scaling_factor = min(1, 768/min_side)
    scaled_width, scaled_height = int(scaled_width * scaling_factor), int(scaled_height * scaling_factor)
    # 3. Finally, we count how many 512px squares the image consists of
    num_width_tiles = scaled_width // IMG_TILE_SIZE + int(
        scaled_width % IMG_TILE_SIZE > 0
    )
    num_height_tiles = scaled_height // IMG_TILE_SIZE + int(
        scaled_height % IMG_TILE_SIZE > 0
    )
    return num_height_tiles * num_width_tiles


def num_tokens_from_image(
    avg_height: int,
    avg_width: int,
    quality_mode: str,
) -> int:
    assert quality_mode in ["high", "low"]
    if quality_mode == "low":
        return IMG_BASE_TOKENS_PER_IMG
    else:
        tiles_per_img = calc_num_img_patches(avg_height, avg_width)
        return IMG_BASE_TOKENS_PER_IMG + tiles_per_img * IMG_HQ_TOKENS_PER_TILE


def get_base64_img_dimensions(base64_image: str) -> tuple[int, int]:
    img = Image.open(BytesIO(base64.b64decode(base64_image)))
    return img.size


def num_tokens_from_messages(messages, model):
    """Return the number of text tokens and image tokens used by a list of messages."""
    num_text_tokens = 0
    num_image_tokens = 0
    
    # Handle Gemini models
    if model.startswith("gemini-"):
        try:
            logging.debug(f"Processing messages for Gemini model: {model}")
            
            genai_model = genai.GenerativeModel(f"models/{model}")
            for i, message in enumerate(messages):
                logging.debug(f"Processing message {i}: {message}")
                if "content" in message:
                    content = message["content"]
                    
                    if isinstance(content, str):
                        if not content.strip():
                            logging.warning(f"Empty string content in message {i}")
                            continue
                        token_response = genai_model.count_tokens(content)
                        num_text_tokens += token_response.total_tokens
                    
                    elif isinstance(content, list):
                        for j, submessage in enumerate(content):
                            if submessage.get("type") == "text":
                                text_content = submessage["text"]
                                if not text_content.strip():
                                    logging.warning(f"Empty text content in submessage {j}")
                                    continue
                                token_response = genai_model.count_tokens(text_content)
                                num_text_tokens += token_response.total_tokens
                            
                            elif submessage.get("type") == "image_url":
                                try:
                                    quality_mode = submessage["image_url"].get("detail", "low")
                                    if quality_mode not in ["high", "low"]:
                                        logging.warning(f"Invalid quality mode '{quality_mode}' in submessage {j}, defaulting to 'low'")
                                        quality_mode = "low"
                                    
                                    base64_img = submessage["image_url"]["url"].split(",")[-1]
                                    width, height = get_base64_img_dimensions(base64_img)
                                    img_tokens = num_tokens_from_image(
                                        height,
                                        width,
                                        quality_mode,
                                    )
                                    num_image_tokens += img_tokens
                                except Exception as e:
                                    logging.error(f"Error processing image in submessage {j}: {str(e)}")
                                    continue
                else:
                    logging.warning(f"Message {i} has no 'content' field: {message}")
            
            return num_text_tokens, num_image_tokens
            
        except Exception as e:
            logging.error(f"Error in Gemini token calculation: {str(e)}")
            logging.error(f"Full message structure: {messages}")
            raise RuntimeError(f"Error calculating tokens for Gemini model: {str(e)}")

    # Original OpenAI token calculation logic
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError as e:
        if "Could not automatically map" in str(e):
            raise RuntimeError(
                (
                    f"Unsupported tiktoken model: '{model}'. This is usually caused by an out-of-date version of tiktoken (your version: {version('tiktoken')})."
                    "Please run `pip install --upgrade -r requirements.txt` to upgrade all dependencies to their latest versions, then try again."
                )
            ) from e
        raise

    if model in {
        "gpt-35-turbo",
        "gpt-3.5-turbo",
        "gpt-35-turbo-0613",
        "gpt-3.5-turbo-0613",
        "gpt-35-turbo-16k-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-35-turbo-16k",
        "gpt-3.5-turbo-16k",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        "gpt-4o",
    } or model.startswith("gpt-4o-"):
        tokens_per_message = 3
        tokens_per_name = 1
    elif model == "gpt-35-turbo-0301" or model == "gpt-3.5-turbo-0301":
        tokens_per_message = (
            4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        )
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif "gpt-35-turbo" in model or "gpt-3.5-turbo" in model:
        logging.warn(
            "Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-35-turbo-0613."
        )
        return num_tokens_from_messages(messages, model="gpt-35-turbo-0613")
    # elif "gpt-4o" in model:
    #     return num_tokens_from_messages(messages, model="gpt-4o")
    else:
        raise NotImplementedError(
            f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."""
        )
    
    for message in messages:
        num_text_tokens += tokens_per_message
        for key, value in message.items():
            if key == "name":
                num_text_tokens += tokens_per_name
            if key == "content":
                if isinstance(value, str):
                    if not value.strip():
                        logging.warning("Empty string content in message")
                        continue
                    num_text_tokens += len(encoding.encode(value, disallowed_special=()))
                elif isinstance(value, list):
                    for submessage in value:
                        msg_type = submessage.get("type")
                        if msg_type == "image_url":
                            try:
                                quality_mode = submessage["image_url"].get("detail", "low")
                                if quality_mode not in ["high", "low"]:
                                    logging.warning(f"Invalid quality mode '{quality_mode}', defaulting to 'low'")
                                    quality_mode = "low"
                                
                                base64_img = submessage["image_url"]["url"].split(",")[-1]
                                width, height = get_base64_img_dimensions(base64_img)
                                img_tokens = num_tokens_from_image(
                                    height,
                                    width,
                                    quality_mode,
                                )
                                num_image_tokens += img_tokens
                            except Exception as e:
                                logging.error(f"Error processing image: {str(e)}")
                                continue
                        elif msg_type == "text":
                            text_content = submessage.get("text", "")
                            if not text_content.strip():
                                logging.warning("Empty text content in submessage")
                                continue
                            num_text_tokens += len(
                                encoding.encode(
                                    text_content, disallowed_special=()
                                )
                            )
    num_text_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_text_tokens, num_image_tokens
