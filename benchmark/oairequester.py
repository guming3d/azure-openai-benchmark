# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import asyncio
import logging
import time
from typing import Optional
import json
import traceback
import random

import aiohttp
import backoff

# TODO: switch to using OpenAI client library once new headers are exposed.

REQUEST_ID_HEADER = "apim-request-id"
UTILIZATION_HEADER = "azure-openai-deployment-utilization"
RETRY_AFTER_MS_HEADER = "retry-after-ms"
MAX_RETRY_SECONDS = 60.0

TELEMETRY_USER_AGENT_HEADER = "x-ms-useragent"
USER_AGENT = "aoai-benchmark"

class RequestStats:
    """
    Statistics collected for a particular AOAI request.
    """
    def __init__(self):
        self.request_start_time: Optional[float] = None
        self.response_status_code: int = 0
        self.response_time: Optional[float] = None
        self.first_token_time: Optional[float] = None
        self.response_end_time: Optional[float] = None
        self.context_text_tokens: int = 0
        self.context_image_tokens: int = 0
        self.generated_tokens: Optional[int] = None
        self.deployment_utilization: Optional[float] = None
        self.calls: int = 0
        self.last_exception: Optional[Exception] = None
        self.input_messages: Optional[dict[str, str]] = None
        self.output_content: list[dict] = list()

    def as_dict(self, include_request_content: bool = False) -> dict:
        output = {
            "request_start_time": self.request_start_time,
            "response_status_code": self.response_status_code,
            "response_time": self.response_time,
            "first_token_time": self.first_token_time,
            "response_end_time": self.response_end_time,
            "context_text_tokens": self.context_text_tokens,
            "context_image_tokens": self.context_image_tokens,
            "generated_tokens": self.generated_tokens,
            "deployment_utilization": self.deployment_utilization,
            "calls": self.calls,
        }
        if include_request_content:
            output["input_messages"] = self.input_messages
            output["output_content"] = self.output_content if self.output_content else None
        # Add last_exception last, to keep it pretty
        output["last_exception"] = self.last_exception
        return output

def _terminal_http_code(e):
    # Check if the exception has a "response" attribute to avoid AttributeError
    if hasattr(e, 'response') and e.response.status != 429:
        return True
    
    # Explicitly handle ClientConnectorDNSError or other connection-related issues
    if isinstance(e, aiohttp.client_exceptions.ClientConnectorError) or \
       isinstance(e, aiohttp.client_exceptions.ClientConnectorDNSError):
        logging.warning(f"Exception while connecting: {e}")
        return True  # Give up retrying for connection errors

    return False

class OAIRequester:
    """
    A simple AOAI requester that makes a streaming call and collect corresponding
    statistics.
    :param api_key: Azure OpenAI resource endpoint key.
    :param url: Full deployment URL in the form of https://<resource>.openai.azure.com/openai/deployments/<deployment>/chat/completins?api-version=<api_version>
    :param backoff: Whether to retry throttled or unsuccessful requests.
    :param debug: Whether to print raw request and response content for debugging.
    :param is_openai_compatible: Whether the endpoint is OpenAI compatible (e.g., openai.com or Google's API).
    """
    def __init__(self, api_key: str, url: str, backoff=False, debug=True, is_openai_compatible=False):
        self.api_key = api_key
        self.url = url
        self.backoff = backoff
        self.debug = debug
        self.is_openai_compatible = is_openai_compatible

    async def call(self, session:aiohttp.ClientSession, body: dict) -> RequestStats:
        """
        Makes a single call with body and returns statistics. The function
        forces the request in streaming mode to be able to collect token
        generation latency.
        In case of failure, if the status code is 429 due to throttling, value
        of header retry-after-ms will be honored. Otherwise, request
        will be retried with an exponential backoff.
        Any other non-200 status code will fail immediately.

        :param body: json request body.
        :return RequestStats.
        """
        stats = RequestStats()
        stats.input_messages = body["messages"]
        # operate only in streaming mode so we can collect token stats.
        body["stream"] = True
        try:
            await self._call(session, body, stats)
        except Exception as e:
            stats.last_exception = traceback.format_exc()
            # Make sure response_end_time is set even in case of exceptions
            if stats.response_end_time is None:
                stats.response_end_time = time.time()

        return stats

    @backoff.on_exception(backoff.expo,
                      aiohttp.ClientError,
                      jitter=backoff.full_jitter,
                      max_time=MAX_RETRY_SECONDS,
                      giveup=_terminal_http_code)
    async def _call(self, session:aiohttp.ClientSession, body: dict, stats: RequestStats):
        """
        Makes a single call with body and returns statistics. The function
        forces the request in streaming mode to be able to collect token
        generation latency.
        """
        stats.calls += 1
        stats.request_start_time = time.time()
        stats.input_messages = body.get("messages", [])

        # Add timestamp and random number to message content to avoid caching
        current_timestamp = time.time()
        random_number = random.random()
        prefix = f"ts={current_timestamp} rand={random_number}\n"
        if stats.input_messages:
            for message in stats.input_messages:
                if 'content' in message and isinstance(message['content'], str):
                     message['content'] = prefix + message['content']
                elif 'content' in message and isinstance(message['content'], list): # Handle list content (e.g., multimodal)
                    # Prepend to the first text part if available
                    prepended = False
                    for item in message['content']:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            item['text'] = prefix + item.get('text', '')
                            prepended = True
                            break
                    # If no text part, add a new text part at the beginning
                    if not prepended:
                         message['content'].insert(0, {'type': 'text', 'text': prefix.strip()})

        # Calculate context tokens before making the request
        if stats.input_messages:
            from .oaitokenizer import num_tokens_from_messages
            model = body.get("model", "gpt-4o")
            text_tokens, image_tokens = num_tokens_from_messages(stats.input_messages, model)
            stats.context_text_tokens = text_tokens
            stats.context_image_tokens = image_tokens

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
            TELEMETRY_USER_AGENT_HEADER: USER_AGENT,
        }
        # Add api-key depending on whether it is an OpenAI.com or Azure OpenAI deployment
        if self.is_openai_compatible:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers["api-key"] = self.api_key

        if self.debug:
            logging.debug(f"Raw request to {self.url}:")
            logging.debug(f"Headers: {json.dumps(headers, indent=2)}")
            logging.debug(f"Body: {json.dumps(body, indent=2)}")

        stats.request_start_time = time.time()
        while stats.calls == 0 or time.time() - stats.request_start_time < MAX_RETRY_SECONDS:
            stats.calls += 1
            response = await session.post(self.url, headers=headers, json=body)
            stats.response_status_code = response.status
            
            if self.debug:
                logging.debug(f"Raw response status: {response.status}")
                logging.debug(f"Raw response headers: {dict(response.headers)}")
                
            # capture utilization in all cases, if found
            self._read_utilization(response, stats)
            if response.status != 429:
                break
            if self.backoff and RETRY_AFTER_MS_HEADER in response.headers:
                try:
                    retry_after_str = response.headers[RETRY_AFTER_MS_HEADER]
                    retry_after_ms = float(retry_after_str)
                    logging.debug(f"retry-after sleeping for {retry_after_ms}ms")
                    await asyncio.sleep(retry_after_ms/1000.0)
                except ValueError as e:
                    logging.warning(f"unable to parse retry-after header value: {UTILIZATION_HEADER}={retry_after_str}: {e}")   
                    # fallback to backoff
                    break
            else:
                # fallback to backoff
                break

        if response.status != 200:
            stats.response_end_time = time.time()
        if response.status != 200 and response.status != 429:
            # logging.warning(f"call failed: {REQUEST_ID_HEADER}={response.headers[REQUEST_ID_HEADER]} {response.status}: {response.reason}")
            logging.warning(f"call failed: {response.status}: {response.reason}: {self.url}: {self.api_key}")
        if self.backoff:
            response.raise_for_status()
        if response.status == 200:
            await self._handle_response(response, stats)
        
    async def _handle_response(self, response: aiohttp.ClientResponse, stats: RequestStats):
        async with response:
            stats.response_time = time.time()
            raw_response_content = []
            
            async for line in response.content:
                if self.debug:
                    raw_response_content.append(line.decode('utf-8'))
                
                if not line.startswith(b'data:'):
                    continue
                if stats.first_token_time is None:
                    stats.first_token_time = time.time()
                if stats.generated_tokens is None:
                    stats.generated_tokens = 0
                # Save content from generated tokens
                content = line.decode('utf-8')
                if content == "data: [DONE]\n":
                    # Request is finished - no more tokens to process
                    break
                
                try:
                    # Parse the JSON response
                    parsed_content = json.loads(content.replace("data: ", ""))
                    
                    # Check if the response has the expected structure
                    if "choices" in parsed_content and len(parsed_content["choices"]) > 0 and "delta" in parsed_content["choices"][0]:
                        delta = parsed_content["choices"][0]["delta"]
                        
                        # Handle both role and content independently
                        if "role" in delta:
                            stats.output_content.append({"role": delta["role"], "content": ""})
                        
                        if "content" in delta and delta["content"]:
                            # If there's no existing output content yet, create one with default role
                            if not stats.output_content:
                                stats.output_content.append({"role": "assistant", "content": ""})
                            
                            # Append the content
                            stats.output_content[-1]["content"] += delta["content"]
                            stats.generated_tokens += 1
                    else:
                        if self.debug:
                            logging.debug(f"Unexpected response structure: {parsed_content}")
                except json.JSONDecodeError:
                    if self.debug:
                        logging.debug(f"Failed to parse response line: {content}")
                except Exception as e:
                    if self.debug:
                        logging.debug(f"Error processing response: {str(e)}")
            
            if self.debug:
                logging.debug("Raw response content:")
                logging.debug("".join(raw_response_content))
                
            stats.response_end_time = time.time()

    def _read_utilization(self, response: aiohttp.ClientResponse, stats: RequestStats):
        if UTILIZATION_HEADER in response.headers:
            util_str = response.headers[UTILIZATION_HEADER]
            if len(util_str) == 0:
                logging.warning(f"got empty utilization header {UTILIZATION_HEADER}")
            elif util_str[-1] != '%':
                logging.warning(f"invalid utilization header value: {UTILIZATION_HEADER}={util_str}")
            else:
                try:
                    stats.deployment_utilization = float(util_str[:-1])
                except ValueError as e:
                    logging.warning(f"unable to parse utilization header value: {UTILIZATION_HEADER}={util_str}: {e}")

