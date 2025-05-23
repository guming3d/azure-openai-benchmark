# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import argparse
import logging
import os
from datetime import datetime

from .loadcmd import load
from .tokenizecmd import tokenize


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')
    
def main():
    parser = argparse.ArgumentParser(description="Benchmarking tool for Azure OpenAI Provisioned Throughput Units (PTUs).")
    parser.add_argument("--log-save-dir", type=str, default="logs", help="Directory to save log files. Defaults to 'logs'.")
    parser.add_argument("--testcase-name", type=str, default="", help="Name of the testcase to be included in log filenames.")
    sub_parsers = parser.add_subparsers()

    load_parser = sub_parsers.add_parser("load", help="Run load generation tool.")
    load_parser.add_argument("-a", "--api-version", type=str, default="2024-12-01-preview", help="Set OpenAI API version.")
    load_parser.add_argument("-k", "--api-key-env", type=str, default="OPENAI_API_KEY", help="Environment variable that contains the API KEY.")
    load_parser.add_argument("-c", "--clients", type=int, default=20, help="Set number of parallel clients to use for load generation.")
    load_parser.add_argument("-n", "--requests", type=int, help="Number of requests for the load run (whether successful or not). Default to 'until killed'.")
    load_parser.add_argument("-d", "--duration", type=int, help="Duration of load in seconds. Defaults to 'until killed'.")
    load_parser.add_argument("--run-end-condition-mode", type=str, help="Determines whether both the `requests` and `duration` args must be reached before ending the run ('and'), or whether to end the run when either arg is reached ('or'). If only one arg is set, the run will end when it is reached. Defaults to 'or'.", choices=["and", "or"], default="or")
    load_parser.add_argument("-r", "--rate", type=float, help="Rate of request generation in Requests Per Minute (RPM). Default to as fast as possible.")
    load_parser.add_argument("-w", "--aggregation-window", type=float, default=60, help="Statistics aggregation sliding window duration in seconds. See README.md for more details.")
    load_parser.add_argument("--context-generation-method", type=str, default="generate", help="Source of context messages to be used during testing.", choices=["generate", "replay"])
    load_parser.add_argument("--replay-path", type=str, help="Path to JSON file containing messages for replay when using --context-message-source=replay.")
    load_parser.add_argument("-s", "--shape-profile", type=str, default="balanced", help="Shape profile of requests.", choices=["balanced", "context", "generation", "custom"])
    load_parser.add_argument("-p", "--context-tokens", type=int, help="Number of context tokens to use when --shape-profile=custom.")
    load_parser.add_argument("-m", "--max-tokens", type=int, help="Number of requested max_tokens when --shape-profile=custom. Defaults to unset.")
    load_parser.add_argument("--prevent-server-caching", type=str2bool, nargs='?', help="Adds a random prefixes to all requests in order to prevent server-side caching. Defaults to True.", const=True, default=True)
    load_parser.add_argument("-i", "--completions", type=int, default=1, help="Number of completion for each request.")
    load_parser.add_argument("--frequency-penalty", type=float, help="Request frequency_penalty.")
    load_parser.add_argument("--presence-penalty", type=float, help="Request frequency_penalty.")
    load_parser.add_argument("--temperature", type=float, help="Request temperature.")
    load_parser.add_argument("--top-p", type=float, help="Request top_p.")
    load_parser.add_argument("--openai-compatible", type=str2bool, nargs='?', help="Indicate if the endpoint is OpenAI API compatible (like openai.com or googleapis.com). Defaults to False.", const=True, default=False)
    load_parser.add_argument("--adjust-for-network-latency", type=str2bool, nargs='?', help="If True, will subtract base network delay from all latency measurements (based on ping). Only use this when trying to simulate the results as if the test machine was in the same data centre as the endpoint. Defaults to False.", const=True, default=False)
    load_parser.add_argument("-f", "--output-format", type=str, default="jsonl", help="Output format.", choices=["jsonl", "human"])
    load_parser.add_argument("--log-save-dir", type=str, help="If provided, will save detailed stdout logs to this directory (in addition to the main benchmark log). Filename will include important run parameters.")
    load_parser.add_argument("--log-request-content", type=str2bool, nargs='?', help="If True, will log the raw input and output tokens of every request. Defaults to False.", const=True, default=False)
    load_parser.add_argument("-t", "--retry", type=str, default="none", help="Request retry strategy. See README for details", choices=["none", "exponential"])
    load_parser.add_argument("-e", "--deployment", type=str, help="Azure OpenAI deployment name, or OpenAI.com model name.", required=True)
    load_parser.add_argument("api_base_endpoint", help="Azure OpenAI deployment base endpoint (or OpenAI.com chat completions endpoint).", nargs=1)
    load_parser.set_defaults(func=load)

    tokenizer_parser = sub_parsers.add_parser("tokenize", help="Text tokenization tool.")
    tokenizer_parser.add_argument(
        "-m", "--model", type=str, help="Model to assume for tokenization.", 
        choices=[
            "gpt-4", "gpt-4o", "gpt-4-0314", "gpt-4-32k-0314", "gpt-4-0613", "gpt-4-32k-0613", 
            "gpt-35-turbo", "gpt-35-turbo-0613", "gpt-35-turbo-16k-0613"], 
        required=True)
    tokenizer_parser.add_argument("text", help="Input text or chat messages json to tokenize. Default to stdin.", nargs="?")
    tokenizer_parser.set_defaults(func=tokenize)

    args = parser.parse_args()

    # Create a formatter that includes timestamp
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Use the parsed argument for the log directory
    log_dir = args.log_save_dir
    os.makedirs(log_dir, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    # Use the potentially configured log_dir here
    testcase_suffix = f"_{args.testcase_name}" if args.testcase_name else ""
    file_handler = logging.FileHandler(os.path.join(log_dir, f"benchmark_{now}{testcase_suffix}.log"))
    file_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Set to DEBUG to capture all levels
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    if args.func is load and args.log_save_dir is not None:
        now = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        # Create log file output
        if args.context_generation_method == "generate":
            token_config_str = f"shape={args.shape_profile}_context-tokens={args.context_tokens}_max-tokens={args.max_tokens}" if args.shape_profile == "custom" else f"shape={args.shape_profile}"
        else:
            token_config_str = f"replay-basename={os.path.basename(args.replay_path).split('.')[0]}_max-tokens={args.max_tokens}"
        rate_str = str(int(args.rate)) if (args.rate is not None) else 'none'
        # This uses the --log-save-dir specific to the load command
        output_path = os.path.join(args.log_save_dir, f"{now}_{args.deployment}_{token_config_str}_clients={int(args.clients)}_rate={rate_str}.log")
        os.makedirs(args.log_save_dir, exist_ok=True)
        try:
            os.remove(output_path)
        except FileNotFoundError:
            pass
        fh = logging.FileHandler(output_path)
        fh.setFormatter(formatter) # Also apply the formatter here
        logger = logging.getLogger()
        logger.addHandler(fh)

    if "func" in args:
        args.func(args)
    else:
        # Use the main parser's help if no subcommand is given
        parser.print_help()

main()