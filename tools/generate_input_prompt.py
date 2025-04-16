import argparse
import sys
import base64
import json
import os
import random
from typing import List, Union, Optional
from PIL import Image
from io import BytesIO
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from benchmark.oaitokenizer import num_tokens_from_text

IMG_BASE_TOKENS_PER_IMG = 85
IMG_HQ_TOKENS_PER_TILE = 170
IMG_TILE_SIZE = 512
DEFAULT_MAX_WORDS = 400

def get_base64_img_dimensions(base64_image: str) -> Union[tuple[int, int], None]:
    """
    Return width and height of a base64 image.
    """
    try:
        img = Image.open(BytesIO(base64.b64decode(base64_image)))
        return img.size
    except Exception as e:
        print(f"Error decoding image or calculating dimensions: {e}")
        return None

def encode_image_to_base64(image_path: str) -> str:
    """
    Convert an image to a base64-encoded string.
    """
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")
    except Exception as e:
        print(f"Error encoding image '{image_path}' to base64: {e}")
        return None

def calc_num_img_patches(width: int, height: int) -> int:
    max_side = max(width, height)
    scaling_factor = min(1, 2048 / max_side)
    scaled_width, scaled_height = int(width * scaling_factor), int(height * scaling_factor)
    
    min_side = min(scaled_width, scaled_height)
    scaling_factor = min(1, 768 / min_side)
    scaled_width, scaled_height = int(scaled_width * scaling_factor), int(scaled_height * scaling_factor)
    
    num_width_tiles = scaled_width // IMG_TILE_SIZE + int(scaled_width % IMG_TILE_SIZE > 0)
    num_height_tiles = scaled_height // IMG_TILE_SIZE + int(scaled_height % IMG_TILE_SIZE > 0)
    return num_width_tiles * num_height_tiles

def get_image_token_count(image_path: str, quality_mode: str) -> int:
    """
    Calculate the token count for an image based on its dimensions and quality.
    """
    assert quality_mode in ["high", "low"]
    if quality_mode == "low":
        return IMG_BASE_TOKENS_PER_IMG
    else:
        img = Image.open(image_path)
        width, height = img.size
        tiles_per_img = calc_num_img_patches(width, height)
        return IMG_BASE_TOKENS_PER_IMG + tiles_per_img * IMG_HQ_TOKENS_PER_TILE


def generate_prompt_json(image_dir: str, request_ratio: float, texts_dir: Optional[str], quality_mode: str = "high", total_messages: int = 100, images_per_request: int = 1, max_words: int = DEFAULT_MAX_WORDS) -> List[List[dict]]:
    """
    Generate a JSON file containing prompts with text-only and multimodal (text + image) requests.
    Token ratios between text and image inputs respect the request ratio.
    
    Args:
        image_dir: Directory containing images.
        request_ratio: Ratio of multimodal requests (0.0 to 1.0).
        texts_dir: Directory containing text files for text-only requests. Required if request_ratio < 1.0.
        quality_mode: Image quality mode ('low' or 'high').
        total_messages: Total number of prompt messages to generate.
        images_per_request: Number of images to include in each multimodal request (1-120).
        max_words: Maximum number of words to request in the generated prompt.
    """
    # Ensure image directory exists and has images
    if request_ratio > 0.0:
        if not os.path.exists(image_dir):
            print(f"Error: Image directory '{image_dir}' not found.")
            return []

        image_files = [f for f in os.listdir(image_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if not image_files:
            print(f"Error: No image files found in '{image_dir}'.")
            return []
        # Limit images_per_request to available images or maximum
        images_per_request = min(images_per_request, len(image_files), 120)
    else:
        image_files = [] # No images needed if ratio is 0.0


    # Load text files if needed
    text_files = []
    if request_ratio < 1.0:
        if not texts_dir or not os.path.isdir(texts_dir):
            print(f"Error: Texts directory '{texts_dir}' not found or invalid.")
            return []
        try:
            text_files = [os.path.join(texts_dir, f) for f in os.listdir(texts_dir) if os.path.isfile(os.path.join(texts_dir, f))]
            if not text_files:
                print(f"Error: No files found in texts directory '{texts_dir}'.")
                return []
        except Exception as e:
            print(f"Error: Error reading texts directory '{texts_dir}': {e}.")
            return []

    # Initialize variables
    prompts = []
    image_token_total = 0
    text_token_total = 0

    # Loop through image files and generate prompts until total_messages is reached
    while len(prompts) < total_messages:
        # Decide whether to generate a multimodal or text-only prompt
        generate_multimodal = False
        if request_ratio == 1.0:
            generate_multimodal = True
        elif request_ratio > 0.0:
            # Check token ratio, avoiding division by zero
            current_total_tokens = image_token_total + text_token_total
            if current_total_tokens == 0 or (image_token_total / current_total_tokens) < request_ratio:
                 generate_multimodal = True

        if generate_multimodal:
            # Create multimodal request with multiple images
            image_batch = []
            total_batch_tokens = 0
            
            # Randomly select images for this batch
            batch_image_files = random.sample(
                image_files, 
                min(images_per_request, len(image_files))
            ) if len(image_files) >= images_per_request else random.choices(image_files, k=images_per_request)
            
            # Process each selected image
            for image_file in batch_image_files:
                image_path = os.path.join(image_dir, image_file)
                base64_image = encode_image_to_base64(image_path)
                if not base64_image:
                    continue
                    
                # Calculate token count for this image
                image_tokens = get_image_token_count(image_path, quality_mode)
                total_batch_tokens += image_tokens
                
                image_batch.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": quality_mode
                    }
                })
            
            # Skip if no images could be processed
            if not image_batch:
                continue
                
            # Create prompt text based on number of images
            prompt_text = f"Please write a story about {'this image' if len(image_batch) == 1 else 'these images'}, no more than {max_words} words"
            image_text_prompt = {
                "type": "text",
                "text": prompt_text
            }
            
            content = [image_text_prompt] + image_batch
            
            multimodal_request = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
            
            text_tokens = num_tokens_from_text(prompt_text, "gpt-4o")
            image_token_total += total_batch_tokens
            text_token_total += text_tokens
            prompts.append(multimodal_request)
        else:
            # Add text-only prompts from files
            if not text_files:
                 # This should not happen due to checks above, but as a safeguard:
                 print("Error: No text files available for text-only request generation.")
                 # Use a simple fallback prompt
                 text_content = f"Please provide a summary of a recent news article, no more than {max_words} words."
            else:
                 selected_text_file = random.choice(text_files)
                 try:
                     with open(selected_text_file, 'r', encoding='utf-8') as f:
                         # Prepend the instruction to the existing text content
                         file_content = f.read()
                         text_content = f"Please summarize the following text in no more than {max_words} words:\n\n{file_content}"
                 except Exception as e:
                     print(f"Warning: Error reading text file '{selected_text_file}': {e}. Using fallback prompt.")
                     text_content = f"Please provide a summary of a recent news article, no more than {max_words} words."

            text_prompt = {
                "type": "text",
                "text": text_content
            }
            
            text_prompt_request = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": [text_prompt]
                }
            ]
            text_token_total += num_tokens_from_text(text_prompt["text"], "gpt-4o")
            prompts.append(text_prompt_request)
            
        # Break if we've reached the desired number of messages
        if len(prompts) >= total_messages:
            break

    # Add fallback example if no prompts generated
    if request_ratio == 0.0 or len(prompts) == 0:
        prompts.append([
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please help summarize the text provided in the input."
                    }
                ]
            }
        ])
    
    print(f"Total Text Tokens: {text_token_total}")
    print(f"Total Image Tokens: {image_token_total}")
    print(f"Percentage of text tokens: {text_token_total / (text_token_total + image_token_total)}")

    return prompts

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate JSON prompts for benchmarking OpenAI models with text and image inputs.",
        epilog="""
Examples:
  # Generate 100 text-only prompts from the 'texts' directory
  python tools/generate_input_prompt.py --image-dir ./images --request-ratio 0.0 --texts-dir ./texts --output-file prompts.json
  
  # Generate 200 prompts with 30% image requests (1 image per request), text prompts from 'my_texts'
  python tools/generate_input_prompt.py --image-dir ./images --request-ratio 0.3 --texts-dir ./my_texts --total-messages 200 --output-file prompts.json
  
  # Generate 50 prompts with 50% image requests (3 images per request) in high quality
  python tools/generate_input_prompt.py --image-dir ./images --request-ratio 0.5 --texts-dir ./prompts_text --total-messages 50 --images-per-request 3 --quality-mode high --max-words 500 --output-file prompts.json
        """
    )
    parser.add_argument("--image-dir", type=str, required=True, help="Directory containing images for multimodal requests.")
    parser.add_argument("--request-ratio", type=float, default=0.0, help="Ratio of multimodal requests to total requests (between 0.0 and 1.0).")
    parser.add_argument("--texts-dir", type=str, default=None, help="Directory containing text files for text-only requests. Required if --request-ratio < 1.0.")
    parser.add_argument("--output-file", type=str, required=True, help="JSON file path to save the generated prompts.")
    parser.add_argument("--quality-mode", type=str, choices=["low", "high"], default="high", help="Image quality mode: 'low' (faster) or 'high' (better quality).")
    parser.add_argument("--total-messages", type=int, default=100, help="Total number of prompt messages to generate.")
    parser.add_argument("--images-per-request", type=int, default=1, help="Number of images to include in each multimodal request (1-120).")
    parser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS, help="Maximum number of words to request in the generated prompt.")
    args = parser.parse_args()

    # Validate arguments
    if args.request_ratio < 0.0 or args.request_ratio > 1.0:
        print("Error: --request-ratio must be between 0.0 and 1.0 (inclusive).")
        exit(1)

    if args.request_ratio < 1.0 and not args.texts_dir:
        print("Error: --texts-dir is required when --request-ratio is less than 1.0.")
        exit(1)

    if args.quality_mode not in ["low", "high"]:
        print("Error: --quality-mode must be either 'low' or 'high'.")
        exit(1)
        
    if args.images_per_request < 1 or args.images_per_request > 120:
        print("Error: --images-per-request must be between 1 and 120 (inclusive).")
        exit(1)

    prompts = generate_prompt_json(
        args.image_dir, 
        args.request_ratio, 
        args.texts_dir,
        quality_mode=args.quality_mode, 
        total_messages=args.total_messages, 
        images_per_request=args.images_per_request,
        max_words=args.max_words
    )
    if prompts:
        with open(args.output_file, "w") as output_file:
            json.dump(prompts, output_file, indent=4)
        print(f"Generated prompt JSON saved to {args.output_file}.")
    else:
        print("Error generating prompts. No output.")