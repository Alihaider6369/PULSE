import os

# Set a harmless test-only value for SECRET_KEY before any test imports the app/settings
os.environ.setdefault("SECRET_KEY", "test-only-secret-not-for-production")
