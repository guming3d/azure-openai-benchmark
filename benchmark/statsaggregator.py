# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import datetime
import json
import logging
import threading
import time
from typing import Optional
import traceback

import numpy as np

from .oairequester import RequestStats
from .oaitokenizer import get_base64_img_dimensions, num_tokens_from_image, num_tokens_from_messages

logger = logging.getLogger()

class _Samples:
   def __init__(self):
      # [0] timestamp, [1] value
      self.samples:[(float, float)] = []

   def _trim_oldest(self, duration:float):
      while len(self.samples) > 0 and (time.time() - self.samples[0][0]) > duration:
         self.samples.pop(0)

   def _append(self, timestamp:float, value:float):
      self.samples.append((timestamp, value))

   def _values(self) -> [float]:
      values = []
      for entry in self.samples:
         values.append(entry[1])
      return values
   
   def _len(self) -> int:
      return len(self.samples)

class _StatsAggregator(threading.Thread):
   """
   A thread-safe request stats aggregator that can periodically emit statistics.
   """
   lock = threading.Lock()
   terminate: threading.Event

   start_time: float = 0
   processing_requests_count: int = 0
   total_requests_count: int = 0
   total_failed_count: int = 0
   throttled_count: int = 0

   request_timestamps = _Samples()
   request_latency = _Samples()
   call_tries = _Samples()
   response_latencies = _Samples()
   first_token_latencies = _Samples()
   token_latencies = _Samples()
   context_text_tokens = _Samples()
   context_image_tokens = _Samples()
   generated_tokens = _Samples()
   utilizations = _Samples()

   raw_stat_dicts = list()

   def __init__(
         self, 
         clients:int, 
         dump_duration:float=5, 
         window_duration:float=60, 
         expected_gen_tokens: Optional[int] = None, 
         json_output:bool=False, 
         log_request_content:bool=False, 
         network_latency_adjustment:float=0, 
         *args,
         **kwargs
      ):
      """
      :param clients: number of clients being used in testing.
      :param dump_duration: duration in seconds to dump current aggregates.
      :param window_duration: duration of sliding window in second to consider for aggregation.
      :param expected_gen_tokens: number of tokens expected in each response.
      :param json_output: whether to dump periodic stats as json or human readable.
      :param log_request_content: whether to log request content in the raw call stat output.
      :param network_latency_adjustment: amount of time (in ms) to subtract from the latency metrics of each request.
      """
      self.clients = clients
      self.dump_duration = dump_duration
      self.window_duration = window_duration
      self.expected_gen_tokens = expected_gen_tokens
      self.json_output = json_output
      self.log_request_content = log_request_content
      self.network_latency_adjustment = network_latency_adjustment

      super(_StatsAggregator, self).__init__(*args, **kwargs)


   def dump_raw_call_stats(self):
      """Dumps raw stats for each individual call within the aggregation window"""
      logger.info(f"Raw call stats: {json.dumps(self.raw_stat_dicts)}")

   def run(self):
      """
      Start the periodic aggregator. Use stop() to stop.
      """
      self.start_time = time.time()
      self.terminate = threading.Event()
      while not self.terminate.wait(self.dump_duration):
         self._dump()
         self._slide_window()

   def stop(self):
      self.terminate.set()
      # Dump one more time to ensure we include the final request
      self._dump()

   def record_new_request(self):
      """
      Records a new request, so that the number of processing requests is known.
      """
      with self.lock:
         self.processing_requests_count += 1

   def aggregate_request(self, stats: RequestStats):
      """
      Aggregates request stat within the sliding window.
      :param stats: request stats object.
      """
      with self.lock:
         try:
            self.processing_requests_count -= 1
            self.total_requests_count += 1
            if stats.request_start_time is not None:
                self.call_tries._append(stats.request_start_time, stats.calls)
            if stats.response_status_code != 200:
               self.total_failed_count += 1
               if stats.response_status_code == 429:
                  self.throttled_count += 1
            else:
               # Check that both response_end_time and request_start_time are not None before calculation
               if stats.response_end_time is not None and stats.request_start_time is not None:
                  request_latency = stats.response_end_time - stats.request_start_time - self.network_latency_adjustment
                  self.request_latency._append(stats.request_start_time, request_latency)
                  if request_latency > self.window_duration:
                     logging.warning((
                           f"request completed in {round(request_latency, 2)} seconds, while aggregation-window is {round(self.window_duration, 2)} "
                           "seconds, consider increasing aggregation-window to at least 2x your typical request latency."
                        )
                     )
               else:
                  logging.warning(f"Skipping request latency calculation as response_end_time or request_start_time is None: ")
               
               self.request_timestamps._append(stats.request_start_time, stats.request_start_time)
               
               # Check for None values before calculations
               if stats.response_time is not None and stats.request_start_time is not None:
                  self.response_latencies._append(stats.request_start_time, stats.response_time - stats.request_start_time - self.network_latency_adjustment)
               
               if stats.first_token_time is not None and stats.request_start_time is not None:
                  self.first_token_latencies._append(stats.request_start_time, stats.first_token_time - stats.request_start_time - self.network_latency_adjustment)
               
               if stats.generated_tokens == 0:
                  logging.error(
                     f"generated_tokens is zero"
                  )
               elif stats.generated_tokens is not None and stats.response_end_time is not None and stats.first_token_time is not None:
                  self.token_latencies._append(
                     stats.request_start_time,
                     (stats.response_end_time - stats.first_token_time - self.network_latency_adjustment) / stats.generated_tokens
                  )
               
               if stats.request_start_time is not None:
                  self.context_text_tokens._append(stats.request_start_time, stats.context_text_tokens)
                  self.context_image_tokens._append(stats.request_start_time, stats.context_image_tokens)
                  if stats.generated_tokens is not None:
                     self.generated_tokens._append(stats.request_start_time, stats.generated_tokens)
            if stats.deployment_utilization is not None and stats.request_start_time is not None:
               self.utilizations._append(stats.request_start_time, stats.deployment_utilization)
         except Exception as e:
            exc_str = '\n'.join(traceback.format_exc().splitlines()[-3:])
            logging.error(f"error while aggregating request stats: {exc_str}")
         # Save raw stat for the call
         self.raw_stat_dicts.append(stats.as_dict(include_request_content=self.log_request_content))

   def _dump(self):
      with self.lock:
         run_seconds = round(time.time() - self.start_time)
         dynamic_window = min(run_seconds, self.window_duration)
         timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
         
         # Existing calculations
         e2e_latency_avg = round(np.average(self.request_latency._values()), 3) if self.request_latency._len() > 0 else "n/a"
         e2e_latency_95th = round(np.percentile(self.request_latency._values(), 95), 3) if self.request_latency._len() > 1 else "n/a"
         context_text_per_minute = round(60.0 * np.sum(self.context_text_tokens._values()) / dynamic_window, 0) if self.context_text_tokens._len() > 0 else "n/a"
         context_image_per_minute = round(60.0 * np.sum(self.context_image_tokens._values()) / dynamic_window, 0) if self.context_image_tokens._len() > 0 else "n/a"
         gen_per_minute = round(60.0 * np.sum(self.generated_tokens._values()) / dynamic_window, 0) if self.generated_tokens._len() > 0 else "n/a"
        
         # New calculation for image tokens
         image_tokens = 0
         for raw_stat in self.raw_stat_dicts:
            logger.debug(f"Processing raw_stat: {json.dumps(raw_stat)}")  # Debug log
            if "input_messages" in raw_stat:
                messages = raw_stat["input_messages"]
                
                # Define the model, assuming it's part of the raw_stat or derived from earlier logic
                model = raw_stat.get("model", "gpt-4o")  

                tokens_from_messages = num_tokens_from_messages(messages, model)
                num_text_tokens, num_image_tokens = tokens_from_messages  # Unpack updated return values

                if num_text_tokens > 0 or num_image_tokens > 0:
                    logging.debug(f"Text Tokens: {num_text_tokens}, Image Tokens: {num_image_tokens}")
                    image_tokens += num_image_tokens
         tokens_per_minute = 0
         if context_text_per_minute != "n/a":
            tokens_per_minute += context_text_per_minute 
         if context_image_per_minute != "n/a":
            tokens_per_minute += context_image_per_minute
         if gen_per_minute != "n/a":
            tokens_per_minute += gen_per_minute
         
         # Add image tokens to the output
         if self.json_output:
            j = {
                "run_seconds": run_seconds,
                "timestamp": timestamp,
                "rpm": round(60.0 * self.request_timestamps._len() / dynamic_window, 1) if self.request_timestamps._len() > 0 else "n/a",
                "processing": min(self.clients, self.processing_requests_count),
                "completed": self.total_requests_count,
                "failures": self.total_failed_count,
                "throttled": self.throttled_count,
                "requests": self.total_requests_count,
                "tpm": {
                    "context_text": context_text_per_minute,
                    "context_image": context_image_per_minute,
                    "gen": gen_per_minute,
                    "total": tokens_per_minute,
                },
                "e2e": {
                    "avg": e2e_latency_avg,
                    "95th": e2e_latency_95th,
                },
                "ttft": {
                    "avg": round(np.average(self.first_token_latencies._values()), 3) if self.first_token_latencies._len() > 0 else "n/a",
                    "95th": round(np.percentile(self.first_token_latencies._values(), 95), 3) if self.first_token_latencies._len() > 1 else "n/a",
                },
                "tbt": {
                    "avg": round(np.average(self.token_latencies._values()), 3) if self.token_latencies._len() > 0 else "n/a",
                    "95th": round(np.percentile(self.token_latencies._values(), 95), 3) if self.token_latencies._len() > 1 else "n/a",
                },
                "context_tpr_avg": int(np.sum(self.context_text_tokens._values()) / self.context_text_tokens._len()) if self.context_text_tokens._len() > 0 else "n/a",
                "gen_tpr": {
                    "10th": int(np.percentile(self.generated_tokens._values(), 10)) if self.generated_tokens._len() > 1 else "n/a",
                    "avg": int(np.sum(self.generated_tokens._values()) / self.generated_tokens._len()) if self.generated_tokens._len() > 0 else "n/a",
                    "90th": int(np.percentile(self.generated_tokens._values(), 90)) if self.generated_tokens._len() > 1 else "n/a",
                },
                "util": {
                    "avg": f"{round(np.average(self.utilizations._values()), 1)}%" if self.utilizations._len() > 0 else "n/a",
                    "95th": f"{round(np.percentile(self.utilizations._values(), 95), 1)}%" if self.utilizations._len() > 1 else "n/a",
                },
            }
            logger.info(json.dumps(j))
         else:
            logger.info(f"rpm: {round(60.0 * self.request_timestamps._len() / dynamic_window, 1) if self.request_timestamps._len() > 0 else 'n/a'} image_tokens: {image_tokens:<6} processing: {min(self.clients, self.processing_requests_count):<4} completed: {self.total_requests_count:<5} failures: {self.total_failed_count:<4} throttled: {self.throttled_count:<4} requests: {self.total_requests_count:<5} tpm: context_text: {context_text_per_minute:<6} gen: {gen_per_minute:<6} image: {image_tokens:<6} total: {tokens_per_minute:<6} ttft_avg: {round(np.average(self.first_token_latencies._values()), 3) if self.first_token_latencies._len() > 0 else 'n/a':<6} ttft_95th: {round(np.percentile(self.first_token_latencies._values(), 95), 3) if self.first_token_latencies._len() > 1 else 'n/a':<6} tbt_avg: {round(np.average(self.token_latencies._values()), 3) if self.token_latencies._len() > 0 else 'n/a':<6} tbt_95th: {round(np.percentile(self.token_latencies._values(), 95), 3) if self.token_latencies._len() > 1 else 'n/a':<6} e2e_avg: {e2e_latency_avg:<6} e2e_95th: {e2e_latency_95th:<6} context_tpr_avg {int(np.sum(self.context_text_tokens._values()) / self.context_text_tokens._len()) if self.context_text_tokens._len() > 0 else 'n/a':<4} gen_tpr_10th {int(np.percentile(self.generated_tokens._values(), 10)) if self.generated_tokens._len() > 1 else 'n/a':<4} gen_tpr_avg {int(np.sum(self.generated_tokens._values()) / self.generated_tokens._len()) if self.generated_tokens._len() > 0 else 'n/a':<4} gen_tpr_90th {int(np.percentile(self.generated_tokens._values(), 90)) if self.generated_tokens._len() > 1 else 'n/a':<4} util_avg: {f'{round(np.average(self.utilizations._values()), 1)}%' if self.utilizations._len() > 0 else 'n/a':<6} util_95th: {f'{round(np.percentile(self.utilizations._values(), 95), 1)}%' if self.utilizations._len() > 1 else 'n/a':<6}")

   def _slide_window(self):
      with self.lock:
         self.call_tries._trim_oldest(self.window_duration)
         self.request_timestamps._trim_oldest(self.window_duration)
         self.response_latencies._trim_oldest(self.window_duration)
         self.first_token_latencies._trim_oldest(self.window_duration)
         self.token_latencies._trim_oldest(self.window_duration)
         self.context_text_tokens._trim_oldest(self.window_duration)
         self.context_image_tokens._trim_oldest(self.window_duration)
         self.generated_tokens._trim_oldest(self.window_duration)
         self.utilizations._trim_oldest(self.window_duration)
