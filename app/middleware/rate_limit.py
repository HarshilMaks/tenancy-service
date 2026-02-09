"""Rate limiting middleware for DoS protection."""

import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware to prevent DoS attacks.
    
    Tracks requests per IP address and enforces limits.
    """
    
    def __init__(self, app, requests_per_window: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        # Store: {ip: [(timestamp, count), ...]}
        self.request_history: Dict[str, list] = defaultdict(list)
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Check rate limit before processing request."""
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/health/live", "/health/ready"]:
            return await call_next(request)
        
        # Check rate limit
        current_time = time.time()
        window_start = current_time - self.window_seconds
        
        # Clean old requests outside window
        if client_ip in self.request_history:
            self.request_history[client_ip] = [
                ts for ts in self.request_history[client_ip]
                if ts > window_start
            ]
        
        # Count requests in current window
        request_count = len(self.request_history[client_ip])
        
        # Check if limit exceeded
        if request_count >= self.requests_per_window:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "requests": request_count,
                    "limit": self.requests_per_window,
                    "path": request.url.path,
                }
            )
            
            return Response(
                content='{"error": "Rate limit exceeded"}',
                status_code=429,
                headers={
                    "Retry-After": str(self.window_seconds),
                    "X-RateLimit-Limit": str(self.requests_per_window),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(current_time + self.window_seconds)),
                }
            )
        
        # Record this request
        self.request_history[client_ip].append(current_time)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = self.requests_per_window - request_count - 1
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(current_time + self.window_seconds))
        
        return response
