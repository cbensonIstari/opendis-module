import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opendis_module.logging_config import LogLevel

logger = logging.getLogger(__name__)

DEFAULT_LOG_FILE = Path("opendis_module.log")


class ModuleConfig(BaseModel):
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="The log level for the module",
    )
    log_file_path: Path = Field(
        default=DEFAULT_LOG_FILE,
        description="Path to the log file to write logs to.",
    )

    model_config = ConfigDict(extra="allow")


def load_config(config_file_path: str) -> ModuleConfig:
    try:
        with open(config_file_path, "r") as config_file:
            config_data: str = config_file.read()
        config = ModuleConfig.model_validate_json(config_data)
        return config
    except FileNotFoundError:
        logger.warning(
            f'Did not find a configuration file at "{config_file_path}". Loading default configuration.',
        )
    except OSError:
        logger.warning(
            "Could not read configuration file. Loading default configuration.",
        )
    except ValidationError:
        logger.warning(
            "Configuration file is not valid. Loading default configuration.",
        )

    config = ModuleConfig()
    return config
