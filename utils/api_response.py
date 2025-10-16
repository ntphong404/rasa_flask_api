"""
API Response utility module for standardized Flask API responses
"""
from flask import jsonify

class ApiResponse:
    """Utility class for standardized API responses"""
    
    @staticmethod
    def success(message, result=None, code=200):
        """
        Create a success response
        
        Args:
            message (str): Success message
            result (any): Response data
            code (int): HTTP status code (default: 200)
            
        Returns:
            tuple: (flask.Response, int)
        """
        return jsonify({
            "code": code,
            "message": message,
            "result": result
        }), code
    
    @staticmethod
    def error(message, result=None, code=400):
        """
        Create an error response
        
        Args:
            message (str): Error message
            result (any): Error details
            code (int): HTTP status code (default: 400)
            
        Returns:
            tuple: (flask.Response, int)
        """
        return jsonify({
            "code": code,
            "message": message,
            "result": result
        }), code
    
    @staticmethod
    def not_found(message, result=None):
        """
        Create a 404 not found response
        
        Args:
            message (str): Error message
            result (any): Error details
            
        Returns:
            tuple: (flask.Response, int)
        """
        return ApiResponse.error(message, result, 404)
    
    @staticmethod
    def internal_error(message, result=None):
        """
        Create a 500 internal server error response
        
        Args:
            message (str): Error message
            result (any): Error details
            
        Returns:
            tuple: (flask.Response, int)
        """
        return ApiResponse.error(message, result, 500)
    
    @staticmethod
    def bad_request(message, result=None):
        """
        Create a 400 bad request response
        
        Args:
            message (str): Error message
            result (any): Error details
            
        Returns:
            tuple: (flask.Response, int)
        """
        return ApiResponse.error(message, result, 400)
    
    @staticmethod
    def unauthorized(message="Unauthorized", result=None):
        """
        Create a 401 unauthorized response
        
        Args:
            message (str): Error message
            result (any): Error details
            
        Returns:
            tuple: (flask.Response, int)
        """
        return ApiResponse.error(message, result, 401)
    
    @staticmethod
    def forbidden(message="Forbidden", result=None):
        """
        Create a 403 forbidden response
        
        Args:
            message (str): Error message
            result (any): Error details
            
        Returns:
            tuple: (flask.Response, int)
        """
        return ApiResponse.error(message, result, 403)
    
    @staticmethod
    def created(message, result=None):
        """
        Create a 201 created response
        
        Args:
            message (str): Success message
            result (any): Response data
            
        Returns:
            tuple: (flask.Response, int)
        """
        return ApiResponse.success(message, result, 201)
    
    @staticmethod
    def accepted(message, result=None):
        """
        Create a 202 accepted response
        
        Args:
            message (str): Success message
            result (any): Response data
            
        Returns:
            tuple: (flask.Response, int)
        """
        return ApiResponse.success(message, result, 202)
    
    @staticmethod
    def no_content(message="No content"):
        """
        Create a 204 no content response
        
        Args:
            message (str): Success message
            
        Returns:
            tuple: (flask.Response, int)
        """
        return ApiResponse.success(message, None, 204)
