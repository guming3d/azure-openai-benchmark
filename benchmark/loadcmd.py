# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import json
import logging
import os
import sys
import time
from typing import Iterable, Iterator
from urllib.parse import urlsplit

import aiohttp
import requests
from ping3 import ping

from benchmark.messagegeneration import (
    BaseMessagesGenerator,
    RandomMessagesGenerator,
    ReplayMessagesGenerator,
)

from .asynchttpexecuter import AsyncHTTPExecuter
from .oairequester import OAIRequester
from .ratelimiting import NoRateLimiter, RateLimiter
from .statsaggregator import _StatsAggregator


class _RequestBuilder:
    """
    Wrapper iterator class to build request payloads.
    """

    def __init__(
        self,
        messages_generator: BaseMessagesGenerator,
        max_tokens: None,
        completions: None,
        frequence_penalty: None,
        presence_penalty: None,
        temperature: None,
        top_p: None,
        model: None,
    ):
        self.messages_generator = messages_generator
        self.max_tokens = max_tokens
        self.completions = completions
        self.frequency_penalty = frequence_penalty
        self.presence_penalty = presence_penalty
        self.temperature = temperature
        self.top_p = top_p
        self.model = model

    def __iter__(self) -> Iterator[dict]:
        return self

    def __next__(self) -> (dict, int):
        messages, messages_tokens = self.messages_generator.generate_messages()
        body = {"messages": messages}
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        if self.completions is not None:
            body["n"] = self.completions
        if self.frequency_penalty is not None:
            body["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            body["presenece_penalty"] = self.presence_penalty
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.top_p is not None:
            body["top_p"] = self.top_p
        # model param is only for openai.com endpoints
        if self.model is not None:
            body["model"] = self.model
        return body, messages_tokens


def load(args):
    try:
        _validate(args)
    except ValueError as e:
        print(f"invalid argument(s): {e}")
        sys.exit(1)

    run_args = {
        "api_base_endpoint": args.api_base_endpoint[0],
        "deployment": args.deployment,
        "clients": args.clients,
        "requests": args.requests,
        "duration": args.duration,
        "run_end_condition_mode": args.run_end_condition_mode,
        "rate": args.rate,
        "aggregation_window": args.aggregation_window,
        "context_generation_method": args.context_generation_method,
        "replay_path": args.replay_path,
        "shape_profile": args.shape_profile,
        "context_tokens": args.context_tokens,
        "max_tokens": args.max_tokens,
        "prevent_server_caching": args.prevent_server_caching,
        "completions": args.completions,
        "retry": args.retry,
        "api_version": args.api_version,
        "frequency_penalty": args.frequency_penalty,
        "presence_penalty": args.presence_penalty,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "adjust_for_network_latency": args.adjust_for_network_latency,
        "output_format": args.output_format,
        "log_request_content": args.log_request_content,
    }
    converted = json.dumps(run_args)
    logging.info("Load test args: " + converted)

    api_key = os.getenv(args.api_key_env)
    if not api_key:
        raise ValueError(
            f"API key is not set - make sure to set the environment variable '{args.api_key_env}'"
        )
    # Check if endpoint is OpenAI compatible based on command line arg or URL patterns
    is_openai_com_endpoint = args.openai_compatible or "openai.com" in args.api_base_endpoint[0] or "googleapis.com" in args.api_base_endpoint[0]
    # Set URL
    if is_openai_com_endpoint:
        url = args.api_base_endpoint[0]
    else:
        url = (
            args.api_base_endpoint[0]
            + "/openai/deployments/"
            + args.deployment
            + "/chat/completions"
        )
        url += "?api-version=" + args.api_version

    rate_limiter = NoRateLimiter()
    if args.rate is not None and args.rate > 0:
        rate_limiter = RateLimiter(args.rate, 60)

    # Check model name in order to correctly estimate tokens
    if is_openai_com_endpoint:
        model = args.deployment
    else:
        model_check_headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }
        model_check_body = {"messages": [{"content": "What is 1+1?", "role": "user"}]}
        response = requests.post(
            url, headers=model_check_headers, json=model_check_body
        )
        if response.status_code != 200:
            raise ValueError(
                f"Deployment check failed with status code {response.status_code}. Reason: {response.reason}. Data: {response.text}"
            )
        model = response.json()["model"]
    logging.info(f"model detected: {model}")

    if args.adjust_for_network_latency:
        logging.info("checking ping to endpoint...")
        network_latency_adjustment = measure_avg_ping(url)
        logging.info(
            f"average ping to endpoint: {int(network_latency_adjustment*1000)}ms. this will be subtracted from all aggregate latency metrics."
        )
    else:
        network_latency_adjustment = 0

    max_tokens = args.max_tokens
    if args.context_generation_method == "generate":
        context_tokens = args.context_tokens
        if args.shape_profile == "balanced":
            context_tokens = 500
            max_tokens = 500
        elif args.shape_profile == "context":
            context_tokens = 2000
            max_tokens = 200
        elif args.shape_profile == "generation":
            context_tokens = 500
            max_tokens = 1000

        logging.info(
            f"using random messages generation with shape profile {args.shape_profile}: context tokens: {context_tokens}, max tokens: {max_tokens}"
        )
        messages_generator = RandomMessagesGenerator(
            model=model,
            prevent_server_caching=args.prevent_server_caching,
            tokens=context_tokens,
            max_tokens=max_tokens,
        )
    if args.context_generation_method == "replay":
        logging.info(f"replaying messages from {args.replay_path}")
        messages_generator = ReplayMessagesGenerator(
            model=model,
            prevent_server_caching=args.prevent_server_caching,
            path=args.replay_path,
        )

    if args.run_end_condition_mode == "and":
        logging.info(
            f"run-end-condition-mode='{args.run_end_condition_mode}': run will not end until BOTH the `requests` and `duration` limits are reached"
        )
    else:
        logging.info(
            f"run-end-condition-mode='{args.run_end_condition_mode}': run will end when EITHER the `requests` or `duration` limit is reached"
        )

    request_builder = _RequestBuilder(
        messages_generator=messages_generator,
        max_tokens=max_tokens,
        completions=args.completions,
        frequence_penalty=args.frequency_penalty,
        presence_penalty=args.presence_penalty,
        temperature=args.temperature,
        top_p=args.top_p,
        model=args.deployment if is_openai_com_endpoint else None,
    )

    logging.info("starting load...")

    _run_load(
        request_builder,
        max_concurrency=args.clients,
        api_key=api_key,
        url=url,
        rate_limiter=rate_limiter,
        backoff=args.retry == "exponential",
        request_count=args.requests,
        duration=args.duration,
        aggregation_duration=args.aggregation_window,
        run_end_condition_mode=args.run_end_condition_mode,
        json_output=args.output_format == "jsonl",
        log_request_content=args.log_request_content,
        network_latency_adjustment=network_latency_adjustment,
        is_openai_com_endpoint=is_openai_com_endpoint,
    )


def _run_load(
    request_builder: Iterable[dict],
    max_concurrency: int,
    api_key: str,
    url: str,
    rate_limiter=None,
    backoff=False,
    duration=None,
    aggregation_duration=60,
    request_count=None,
    run_end_condition_mode="or",
    json_output=False,
    log_request_content=False,
    network_latency_adjustment=0,
    is_openai_com_endpoint=False
):
    aggregator = _StatsAggregator(
        window_duration=aggregation_duration,
        dump_duration=1,
        expected_gen_tokens=request_builder.max_tokens,
        clients=max_concurrency,
        json_output=json_output,
        log_request_content=log_request_content,
        network_latency_adjustment=network_latency_adjustment,
    )
    requester = OAIRequester(api_key, url, backoff=backoff, debug=True, is_openai_compatible=is_openai_com_endpoint)

    async def request_func(session: aiohttp.ClientSession):
        nonlocal aggregator
        nonlocal requester
        request_body, messages_tokens = request_builder.__next__()
        aggregator.record_new_request()
        stats = await requester.call(session, request_body)
        stats.context_text_tokens = messages_tokens[0]
        stats.context_image_tokens = messages_tokens[1]
        try:
            aggregator.aggregate_request(stats)
        except Exception as e:
            print(e)

    def finish_run_func():
        """Function to run when run is finished."""
        nonlocal aggregator
        aggregator.dump_raw_call_stats()

    executer = AsyncHTTPExecuter(
        request_func,
        rate_limiter=rate_limiter,
        max_concurrency=max_concurrency,
        finish_run_func=finish_run_func,
    )

    aggregator.start()
    executer.run(
        call_count=request_count,
        duration=duration,
        run_end_condition_mode=run_end_condition_mode,
    )
    aggregator.stop()

    logging.info("finished load test")


def _validate(args):
    if len(args.api_version) == 0:
        raise ValueError("api-version is required")
    if len(args.api_key_env) == 0:
        raise ValueError("api-key-env is required")
    if os.getenv(args.api_key_env) is None:
        raise ValueError(f"api-key-env {args.api_key_env} not set")
    if args.clients < 1:
        raise ValueError("clients must be > 0")
    if args.requests is not None and args.requests < 0:
        raise ValueError("requests must be > 0")
    if args.duration is not None and args.duration != 0 and args.duration < 30:
        raise ValueError("duration must be > 30")
    if args.run_end_condition_mode not in ("and", "or"):
        raise ValueError("run-end-condition-mode must be one of: ['and', 'or']")
    if args.rate is not None and args.rate < 0:
        raise ValueError("rate must be > 0")
    if args.context_generation_method == "replay":
        if not args.replay_path:
            raise ValueError(
                "replay-path is required when context-generation-method=replay"
            )
    if args.context_generation_method == "generate":
        if args.shape_profile == "custom" and args.context_tokens < 1:
            raise ValueError("context-tokens must be specified with shape=custom")
        if args.shape_profile == "custom":
            if args.context_tokens < 1:
                raise ValueError("context-tokens must be specified with shape=custom")
    if args.max_tokens is not None and args.max_tokens < 0:
        raise ValueError("max-tokens must be > 0")
    if args.completions < 1:
        raise ValueError("completions must be > 0")
    if args.frequency_penalty is not None and (
        args.frequency_penalty < -2 or args.frequency_penalty > 2
    ):
        raise ValueError("frequency-penalty must be between -2.0 and 2.0")
    if args.presence_penalty is not None and (
        args.presence_penalty < -2 or args.presence_penalty > 2
    ):
        raise ValueError("presence-penalty must be between -2.0 and 2.0")
    if args.temperature is not None and (args.temperature < 0 or args.temperature > 2):
        raise ValueError("temperature must be between 0 and 2.0")


def measure_avg_ping(url: str, num_requests: int = 5, max_time: int = 5):
    """Measures average network latency for a given URL by sending multiple ping requests."""
    ping_url = urlsplit(url).netloc
    latencies = []
    latency_test_start_time = time.time()
    while (
        len(latencies) < num_requests
        and time.time() < latency_test_start_time + max_time
    ):
        delay = ping(ping_url, timeout=5)
        latencies.append(delay)
        if delay < 0.5:  # Ensure at least 0.5 seconds between requests
            time.sleep(0.5 - delay)
    avg_latency = round(
        sum(latencies) / len(latencies), 2
    )  # exclude first request, this is usually 3-5x slower
    return avg_latency
