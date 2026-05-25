"""
Django settings for the Fair Work Award RAG chatbot.

Reads configuration from a .env file in the project root (see .env.example).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root if present.
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------
# Core Django
# --------------------------------------------------------------------------
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure--g_*l=96z^nopj%iqqjsbng^=%#ly3sanpmcv!a0u_7dctt1!u",
)

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "awards",
    "chatbot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = True

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite stores both the scraped award clauses and every chat request/response.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # Public API: no auth/CSRF friction for the chat endpoints.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}

# --------------------------------------------------------------------------
# Fair Work Award chatbot configuration
# --------------------------------------------------------------------------
AWARD = {
    # The award document to scrape.
    "CODE": os.getenv("AWARD_CODE", "MA000100"),
    "URL": os.getenv("AWARD_URL", "https://awards.fairwork.gov.au/MA000100.html"),
    # Approx. characters per chunk (~4 chars per token => ~900 tokens).
    "CHUNK_CHARS": int(os.getenv("AWARD_CHUNK_CHARS", "3600")),
}

OLLAMA = {
    "BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
    "CHAT_MODEL": os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b-instruct-q4_K_M"),
    "EMBED_MODEL": os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
    "TIMEOUT": int(os.getenv("OLLAMA_TIMEOUT", "120")),
}

PINECONE = {
    "API_KEY": os.getenv("PINECONE_API_KEY", ""),
    "INDEX_NAME": os.getenv("PINECONE_INDEX_NAME", "fairwork-ma000100"),
    "CLOUD": os.getenv("PINECONE_CLOUD", "aws"),
    "REGION": os.getenv("PINECONE_REGION", "us-east-1"),
    "NAMESPACE": os.getenv("PINECONE_NAMESPACE", "ma000100"),
    "METRIC": os.getenv("PINECONE_METRIC", "cosine"),
    "DIMENSION": int(os.getenv("PINECONE_DIMENSION", "768")),
}

RAG = {
    # How many clause chunks to retrieve per question.
    "TOP_K": int(os.getenv("RAG_TOP_K", "5")),
}

LLM = {
    "PROVIDER": os.getenv("LLM_PROVIDER", "ollama").lower(),
    "TIMEOUT": int(os.getenv("LLM_TIMEOUT", "60")),
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
    "OPENAI_CHAT_MODEL": os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    "GROQ_API_KEY": os.getenv("GROQ_API_KEY", ""),
    "GROQ_CHAT_MODEL": os.getenv("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    "GEMINI_CHAT_MODEL": os.getenv("GEMINI_CHAT_MODEL", "gemini-2.0-flash"),
}

LANGSMITH = {
    "TRACING": env_bool("LANGSMITH_TRACING", False),
    "API_KEY": os.getenv("LANGSMITH_API_KEY", ""),
    "PROJECT": os.getenv("LANGSMITH_PROJECT", "fairwork-chatbot"),
    "ENDPOINT": os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
}

# Sync LangSmith env vars so @traceable picks them up before services are imported.
if LANGSMITH["TRACING"]:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    if LANGSMITH["API_KEY"]:
        os.environ.setdefault("LANGSMITH_API_KEY", LANGSMITH["API_KEY"])
    if LANGSMITH["PROJECT"]:
        os.environ.setdefault("LANGSMITH_PROJECT", LANGSMITH["PROJECT"])
    if LANGSMITH["ENDPOINT"]:
        os.environ.setdefault("LANGSMITH_ENDPOINT", LANGSMITH["ENDPOINT"])

# --------------------------------------------------------------------------
# Logging — traces every chat query through the RAG / calculation pipeline.
#
# The `services` logger records, per request: the user query, its embedding
# vector summary, the similar vectors retrieved (id + similarity score), which
# path was chosen (calculation vs RAG) and the engine result. Read the trace
# in the console or in logs/chatbot.log to see exactly where an answer is
# formed — and where a rule is or is not applied.
# --------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "pipeline": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "pipeline",
        },
        "pipeline_file": {
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "chatbot.log"),
            "encoding": "utf-8",
            "formatter": "pipeline",
        },
    },
    "loggers": {
        # All RAG / calculation tracing flows through the `services` parent
        # logger (services.rag, services.llm, services.embeddings, ...).
        "services": {
            "handlers": ["console", "pipeline_file"],
            "level": os.getenv("CHATBOT_LOG_LEVEL", "INFO").upper(),
            "propagate": False,
        },
    },
}
