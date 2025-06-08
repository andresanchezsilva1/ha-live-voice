"""
Retry Logic Module for Home Assistant Client

Implements exponential backoff, circuit breaker pattern, and comprehensive retry logic.
"""

import asyncio
import logging
import random
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type, Union
from dataclasses import dataclass

import httpx

from .exceptions import (
    HAClientError, 
    HAConnectionError, 
    HATimeoutError, 
    HARateLimitError,
    HAAuthenticationError,
    create_ha_error_from_response
)


logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Failing, requests rejected
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retriable_exceptions: tuple = (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.NetworkError,
        HAConnectionError,
        HATimeoutError
    )
    non_retriable_exceptions: tuple = (
        HAAuthenticationError,
    )


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3


class CircuitBreaker:
    """
    Circuit breaker implementation for Home Assistant client
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
    
    def can_execute(self) -> bool:
        """Check if request can be executed"""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                return True
            return False
        elif self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.config.half_open_max_calls
        
        return False
    
    def record_success(self):
        """Record successful operation"""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            logger.info("Circuit breaker transitioning to CLOSED (recovered)")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker transitioning to OPEN (still failing)")
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error(f"Circuit breaker OPEN after {self.failure_count} failures")
        
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1


class RetryManager:
    """
    Manages retry logic with exponential backoff and circuit breaker
    """
    
    def __init__(self, retry_config: RetryConfig, circuit_config: CircuitBreakerConfig):
        self.retry_config = retry_config
        self.circuit_breaker = CircuitBreaker(circuit_config)
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff and jitter"""
        delay = min(
            self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt),
            self.retry_config.max_delay
        )
        
        if self.retry_config.jitter:
            delay *= (0.5 + random.random() * 0.5)  # Add 0-50% jitter
        
        return delay
    
    def is_retriable_exception(self, exception: Exception) -> bool:
        """Check if exception is retriable"""
        if isinstance(exception, self.retry_config.non_retriable_exceptions):
            return False
        
        if isinstance(exception, self.retry_config.retriable_exceptions):
            return True
        
        # Special handling for rate limit errors
        if isinstance(exception, HARateLimitError):
            return True
        
        # Check if it's an httpx.HTTPStatusError
        if isinstance(exception, httpx.HTTPStatusError):
            # Retry on 5xx errors and some 4xx errors
            status_code = exception.response.status_code
            if 500 <= status_code < 600:  # Server errors
                return True
            if status_code == 429:  # Too Many Requests
                return True
            if status_code == 408:  # Request Timeout
                return True
        
        return False
    
    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with retry logic and circuit breaker
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            HAClientError: If all retries are exhausted or circuit is open
        """
        if not self.circuit_breaker.can_execute():
            raise HAConnectionError("Circuit breaker is OPEN - service unavailable")
        
        last_exception = None
        
        for attempt in range(self.retry_config.max_attempts):
            try:
                logger.debug(f"Attempt {attempt + 1}/{self.retry_config.max_attempts}")
                result = await func(*args, **kwargs)
                self.circuit_breaker.record_success()
                return result
                
            except Exception as e:
                last_exception = e
                
                # Convert to HAClientError if needed
                if isinstance(e, httpx.HTTPStatusError):
                    ha_error = create_ha_error_from_response(e.response, e)
                elif isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
                    ha_error = HAConnectionError(f"Network error: {str(e)}", original_exception=e)
                elif isinstance(e, httpx.TimeoutException):
                    ha_error = HATimeoutError(f"Request timed out: {str(e)}", original_exception=e)
                elif isinstance(e, HAClientError):
                    ha_error = e
                else:
                    ha_error = HAClientError(f"Unexpected error: {str(e)}", original_exception=e)
                
                # Record failure in circuit breaker
                self.circuit_breaker.record_failure()
                
                # Check if we should retry
                if not self.is_retriable_exception(ha_error):
                    logger.warning(f"Non-retriable error: {ha_error}")
                    raise ha_error
                
                # Don't retry on last attempt
                if attempt == self.retry_config.max_attempts - 1:
                    logger.error(f"All retry attempts exhausted. Last error: {ha_error}")
                    raise ha_error
                
                # Calculate delay and wait
                delay = self.calculate_delay(attempt)
                
                # Special handling for rate limit
                if isinstance(ha_error, HARateLimitError) and ha_error.details.get('retry_after'):
                    delay = max(delay, ha_error.details['retry_after'])
                
                logger.warning(f"Attempt {attempt + 1} failed: {ha_error}. Retrying in {delay:.2f}s")
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        if last_exception:
            raise last_exception


def with_retry(
    retry_config: Optional[RetryConfig] = None,
    circuit_config: Optional[CircuitBreakerConfig] = None
):
    """
    Decorator to add retry logic to async functions
    
    Args:
        retry_config: Retry configuration
        circuit_config: Circuit breaker configuration
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            config = retry_config or RetryConfig()
            circuit_cfg = circuit_config or CircuitBreakerConfig()
            retry_manager = RetryManager(config, circuit_cfg)
            return await retry_manager.execute_with_retry(func, *args, **kwargs)
        return wrapper
    return decorator


# Default configurations
DEFAULT_RETRY_CONFIG = RetryConfig()
DEFAULT_CIRCUIT_CONFIG = CircuitBreakerConfig()

# Global retry manager instance
DEFAULT_RETRY_MANAGER = RetryManager(DEFAULT_RETRY_CONFIG, DEFAULT_CIRCUIT_CONFIG) 