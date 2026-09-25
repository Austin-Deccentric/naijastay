One of the most significant issues I encountered was an application startup failure caused by missing environment variables. 
Pydantic Settings was reporting that database_url, jwt_secret_key, and rate_limit_global were required but couldn't be found.
I traced the error from the stack trace to the Settings configuration, checked how environment variables were being loaded, and configured the application to load them from .env. 
After adding the required variables and verifying that the settings loaded correctly, the application was able to start normally. 
It taught me to distinguish between application-code errors and configuration or environment errors.
