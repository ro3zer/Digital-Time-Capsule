from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
from flask import request, jsonify
from typing import Dict, List, Tuple
import time

class RateLimiter:
    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.requests: Dict[str, List[float]] = defaultdict(list)
        
    def _clean_old_requests(self, user_id: str):
        """Remove requests older than 1 hour"""
        current_time = time.time()
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if current_time - req_time < 3600  # 1 hour in seconds
        ]
        
    def check_rate_limit(self, user_id: str) -> Tuple[bool, str]:
        """
        Check if the request should be rate limited
        Returns: (is_allowed, error_message)
        """
        if not user_id:
            return False, "User ID is required"
            
        current_time = time.time()
        self._clean_old_requests(user_id)
        
        # Add current request
        self.requests[user_id].append(current_time)
        
        # Check minute limit
        minute_ago = current_time - 60
        requests_last_minute = sum(
            1 for req_time in self.requests[user_id]
            if req_time > minute_ago
        )
        
        if requests_last_minute > self.requests_per_minute:
            return False, f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute allowed."
            
        # Check hour limit
        requests_last_hour = len(self.requests[user_id])
        if requests_last_hour > self.requests_per_hour:
            return False, f"Rate limit exceeded. Maximum {self.requests_per_hour} requests per hour allowed."
            
        return True, ""

def rate_limit(limiter: RateLimiter):
    """
    Decorator for rate limiting routes
    """
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            user_id = request.args.get('user_id') or request.form.get('user_id')
            
            if not user_id:
                return jsonify({'error': 'User ID is required'}), 401
                
            is_allowed, error_message = limiter.check_rate_limit(user_id)
            
            if not is_allowed:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': error_message
                }), 429
                
            return await f(*args, **kwargs)
        return decorated_function
    return decorator