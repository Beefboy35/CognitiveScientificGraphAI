from app.config.settings import Settings


def get_settings() -> Settings:
    return Settings(app_env="dev")
