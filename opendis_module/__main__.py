import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

# Explicit imports trigger function registration
import opendis_module.functions  # noqa: F401
from opendis_module import logging_config, module_config
from opendis_module.functions.registry import get_function
from opendis_module.module_config import ModuleConfig

logger = logging.getLogger(__name__)


@dataclass
class CommandArgs:
    function_name: str
    input_file: str
    output_file: str
    temp_dir: str
    config_path: Optional[str] = None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="opendis_module",
        description="Istari module for parsing DIS (IEEE 1278.1) binary PDU streams.",
    )

    parser.add_argument(
        "function_name",
        type=str,
        help="The name of the Istari Function to execute.",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        help="Path to the input JSON file.",
        required=True,
    )
    parser.add_argument(
        "--output-file",
        type=str,
        help="Path to the output JSON list to be written by this module.",
        required=True,
    )
    parser.add_argument(
        "--temp-dir",
        type=str,
        help="A directory for storing output and temporary files.",
        required=True,
    )
    parser.add_argument(
        "--config-path",
        "-c",
        type=str,
        help="Path to the module configuration file.",
        required=False,
        default=None,
    )
    args = CommandArgs(**vars(parser.parse_args()))
    run(
        args.function_name,
        args.input_file,
        args.output_file,
        args.temp_dir,
        args.config_path,
    )


def run(
    function_name: str,
    input_file: str,
    output_file: str,
    temp_dir: str,
    config_path_arg: Optional[str] = None,
) -> None:
    # 1. Setup configuration
    if config_path_arg:
        config_path = Path(config_path_arg)
    else:
        if getattr(sys, "frozen", False):
            base_directory = Path(sys.executable).parent
        else:
            base_directory = Path.cwd()
        config_path = base_directory / "module_config.json"

    logging_config.configure_initial_logging()
    config: ModuleConfig = module_config.load_config(str(config_path))
    logging_config.configure_logging(
        log_level=config.log_level,
        log_file_path=str(config.log_file_path),
    )

    # 2. Read Input
    try:
        logger.info(f'Reading input items from "{input_file}".')
        function_input_json = Path(input_file).read_text(encoding="utf-8")
    except OSError:
        logger.fatal(f'Could not read input file at "{input_file}".', exc_info=True)
        sys.exit(1)

    # 3. Get Function
    try:
        function = get_function(function_name)
    except ValueError as e:
        logger.fatal(str(e))
        sys.exit(1)

    # 4. Execute Function
    try:
        outputs = function(function_input_json, temp_dir)
    except ValueError as e:
        logger.fatal(f"Function execution failed: {e}")
        sys.exit(1)

    # 5. Write Output
    try:
        logger.info(f'Writing output items to "{output_file}".')
        output_dicts = [asdict(output) for output in outputs]
        Path(output_file).write_text(json.dumps(output_dicts), encoding="utf-8")
    except OSError:
        logger.exception(f'Failed to write the outputs JSON to "{output_file}".')


if __name__ == "__main__":
    main()
