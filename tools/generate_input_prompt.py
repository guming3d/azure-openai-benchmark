import argparse
import sys
import base64
import json
import os
from typing import List, Union
from PIL import Image
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from benchmark.oaitokenizer import num_tokens_from_text

IMG_BASE_TOKENS_PER_IMG = 85
IMG_HQ_TOKENS_PER_TILE = 170
IMG_TILE_SIZE = 512

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


def generate_prompt_json(image_dir: str, request_ratio: float, quality_mode: str = "high", total_messages: int = 100) -> List[List[dict]]:
    """
    Generate a JSON file containing prompts with text-only and multimodal (text + image) requests.
    Token ratios between text and image inputs respect the request ratio.
    """
    # Ensure image directory exists and has images
    if not os.path.exists(image_dir):
        print(f"Error: Image directory '{image_dir}' not found.")
        return []

    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not image_files:
        print(f"Error: No image files found in '{image_dir}'.")
        return []

    # Initialize variables
    prompts = []
    image_token_total = 0
    text_token_total = 0

    # Loop through image files and generate prompts until total_messages is reached
    while len(prompts) < total_messages:
        for image_file in image_files:
            if len(prompts) >= total_messages:
                break  # Ensure we don't exceed the total message count

            image_path = os.path.join(image_dir, image_file)
            base64_image = encode_image_to_base64(image_path)
            if not base64_image:
                continue
            
            image_tokens = get_image_token_count(image_path, quality_mode)
            image_text_prompt = {
                "type": "text",
                "text": "Please write a story about the image, no more than 200 words"
            }
            text_tokens = num_tokens_from_text(image_text_prompt["text"], "gpt-4o")

            text_prompt = {
                "type": "text",
                "text": """
Please write summary of following news no more than 100 words:
OVER A CENTURY ago, ships leaving Rotterdam's harbour were among the earliest to be equipped with wireless telegraphy and submarine signalling. Now, Europe's busiest port is pioneering the use of artificial intelligence (AI). PortXChange, developed by the port and spun out as an independent entity, uses AI to analyse several dozen factors tracking vessels, port emissions and estimated arrival times. A huge source of wasted fuel is the "hurry up and wait" common among ships rushing to arrive at congested ports. This platform helped Shell, an oil giant, reduce "idle time", affecting departures of barges and bulk shipments across all ports, by 20%. The tool is now being used by companies and ports around the globe.

The Dutch are hardly alone. Companies worldwide are applying AI tools like machine learning (ML) to cut energy use and emissions. Examples abound even in asset-heavy, fossil-intensive industries like steel, building maintenance and transport that account for a huge chunk of anthropogenic greenhouse gas (GHG) emissions.

Consider the steel industry, responsible for roughly a tenth of CO2 emissions. It is hard to decarbonise when steel is made from virgin iron ore in conventional blast furnaces, because coal is used both as fuel and a reducing agent. A more promising path involves making steel from scrap metal in electric-arc furnaces powered with clean energy. The snag is that scrap comes in batches with varying impurities, which can make these mills more complex to operate and increase their energy use.

This is where Gerdau, a big Brazilian steelmaker with global operations, is applying ML. Fero Labs, a software company, analysed years of production data from a Gerdau facility in North America to work out how different "recipes" of input materials affect the quality of outputs. Its system measures the contents of each batch of scrap and uses AI to suggest the minimum quantity of alloys that will be needed to then produce metals that meet required standards. This saves time and overuse of additives. In 2024, with no change in hardware, these efforts cut GHG emissions associated with making a commonly used grade of steel by 3.3%.

In a report released on April 10th, the International Energy Agency estimates that widespread industrial application of such AI tools could save eight exajoules (EJ) of energy demand by 2035, as much energy as Mexico uses today. Widespread adoption in non-industrial sectors could save another 5EJ or so.

Mining is another dirty business where AI is making inroads. Fortescue, an Australian giant, is applying AI in designing current systems and redesigning future mining and energy operations with an eye to eliminating fossil fuels. Its algorithms automate tasks such as calculating how energy is used and the routes that autonomous heavy vehicles take. If the weather forecast is for rain, meaning solar output will fall, the company brings forward energy-intensive tasks while it can still use clean solar power. The software enabling this sort of load flexibility, the firm reckons, has allowed it to cut the required capacity of the power system it built by 9%, saving nearly $500m.

Buildings are responsible for perhaps a fifth of all man-made GHGs, and because they last a long time their climate impact can be hard to reduce. Happily, AI can help here too. BrainBox AI, a Canadian tech firm recently acquired by Ireland's Trane Technologies, has helped Dollar Tree, an American discount retailer, deploy autonomous heating, ventilation and air-conditioning in over 600 stores. Combining internal data with weather forecasts, the new systems cut electricity use by nearly 8GWh in a year, saving the firm over $1m.

Predictive maintenance shows promise too. Using AI-powered software supplied by AVEVA, a British company, Ontario Power Generation, a utility, found some $4m in efficiency savings in two years while reducing risks. Sund & Baelt, a Danish firm, used IBM's AI (in tandem with camera-toting drones) to cut expenses by 2% year on year. The approach is so superior that the company expects to double the lifespan of its assets, in effect avoiding 750,000 tonnes of CO2 emissions.

Shipping and logistics companies have taken to applying AI with gusto. UPS, a package-delivery giant, recalculates delivery routes throughout the day as orders, pickups and traffic conditions fluctuate. It estimates that its smart software has improved on-time delivery while cutting 16-22 kilometres from drivers' daily trips, saving hundreds of millions in fuel costs. Cargill Ocean Transportation, the logistics arm of an agribusiness goliath, uses AI enabled by Amazon's AWS to reduce the time ships spend loading and unloading in port, saving up to 2,800 working hours, and their associated CO2 emissions, per year.

Denmark's Maersk, one of the world's largest container-shipping lines, uses AI to analyse variables from engine performance to ocean currents and weather to avoid rough seas and waiting time. Making even its older ships smarter has reduced fuel consumption by over 5% across its fleet, saving $250m and reducing CO2 emissions by perhaps 1.5m tonnes.

That example points back to Rotterdam. Routescanner, a route-optimisation platform developed by the port, uses terminal and company data to offer shippers real-time alternatives on routes, modalities (barge versus lorry, say) and environmental impact. The platform is now used by leading global forwarders and ports from Houston to Singapore. Slowly but surely, AI is helping turn brown to green.
                """
            }

            if (image_token_total / (image_token_total + text_token_total + image_tokens)) < request_ratio:
                # Create multimodal request if ratio is not exceeded
                multimodal_request = [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant."
                    },
                    {
                        "role": "user",
                        "content": [
                            image_text_prompt,
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": quality_mode
                                }
                            }
                        ]
                    }
                ]
                image_token_total += image_tokens
                text_tokens = num_tokens_from_text(image_text_prompt["text"], "gpt-4o")
                text_token_total += text_tokens
                prompts.append(multimodal_request)
            else:
                # Add simple text-only prompts
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
                text_token_total += num_tokens_from_text(text_prompt["text"], "gpt-4o")  # Approximate text token count (words for simplicity)
                prompts.append(text_prompt_request)

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
    parser = argparse.ArgumentParser(description="Generate prompt JSON for load testing.")
    parser.add_argument("--image-dir", type=str, required=True, help="Directory containing images.")
    parser.add_argument("--request-ratio", type=float, default=0.0, help="Ratio of multimodal requests (between 0.0 and 1.0).")
    parser.add_argument("--output-file", type=str, required=True, help="File to save the generated JSON.")
    parser.add_argument("--quality-mode", type=str, choices=["low", "high"], default="high", help="Image quality mode, 'low' or 'high'.")
    parser.add_argument("--total-messages", type=int, default=100, help="Total number of prompt messages to generate.")
    args = parser.parse_args()

    if args.request_ratio < 0.0 or args.request_ratio > 1.0:
        print("Error: --request-ratio must be between 0.0 and 1.0 (inclusive).")
        exit(1)

    if args.quality_mode not in ["low", "high"]:
        print("Error: --quality-mode must be either 'low' or 'high'.")
        exit(1)

    prompts = generate_prompt_json(args.image_dir, args.request_ratio, quality_mode=args.quality_mode, total_messages=args.total_messages)
    if prompts:
        with open(args.output_file, "w") as output_file:
            json.dump(prompts, output_file, indent=4)
        print(f"Generated prompt JSON saved to {args.output_file}.")
    else:
        print("Error generating prompts. No output.")