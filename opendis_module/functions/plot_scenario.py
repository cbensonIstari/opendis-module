"""PlotScenario function — visualize DIS entity trajectories as a PNG plot."""

import json
import logging
from pathlib import Path
from typing import List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opendis_module.functions.base.function_io import Input, Output, OutputType
from opendis_module.functions.registry import register
from opendis_module.services.dis_parser import parse_dis_file

logger = logging.getLogger(__name__)

# Distinct colors for entity trajectories
ENTITY_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


class PlotScenarioInput(BaseModel):
    """Input schema for PlotScenario."""

    input_model: Input[str] = Field(
        ..., description="Path to DIS binary file (.dis or .bin)"
    )

    model_config = ConfigDict(extra="allow")


def plot_scenario(input_json: str, temp_dir: str) -> List[Output]:
    """Parse a DIS binary file and produce a PNG trajectory plot.

    Args:
        input_json: JSON string with input_model pointing to .dis/.bin file.
        temp_dir: Directory for output files.

    Returns:
        List of Output items (scenario_plot_png, metadata).
    """
    logger.info("Starting PlotScenario execution.")

    # 1. Parse input
    try:
        function_input = PlotScenarioInput.model_validate_json(input_json)
    except ValidationError as e:
        raise ValueError(f"Invalid input for PlotScenario: {e}") from e

    outputs: List[Output] = []
    dis_file_path = function_input.input_model.value

    # 2. Parse DIS file
    try:
        result = parse_dis_file(dis_file_path)
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(f"PlotScenario failed: {e}") from e

    # 3. Extract entity trajectories from EntityStatePdu (type 1)
    entity_tracks: dict[str, list[tuple[float, float]]] = {}
    for pdu in result["pdus"]:
        if pdu["pdu_type"] == 1:
            eid = f"{pdu['entity_id']['site']}.{pdu['entity_id']['application']}.{pdu['entity_id']['entity']}"
            loc = pdu["entity_location"]
            if eid not in entity_tracks:
                entity_tracks[eid] = []
            entity_tracks[eid].append((loc["x"], loc["y"]))

    # 4. Create plot
    fig, ax = plt.subplots(1, 1, figsize=(10, 8))

    if entity_tracks:
        for idx, (eid, positions) in enumerate(entity_tracks.items()):
            color = ENTITY_COLORS[idx % len(ENTITY_COLORS)]
            xs = [p[0] for p in positions]
            ys = [p[1] for p in positions]
            ax.plot(xs, ys, color=color, linewidth=1.5, label=f"Entity {eid}")
            # Start marker
            ax.plot(xs[0], ys[0], marker="o", color=color, markersize=8)
            # End marker
            ax.plot(xs[-1], ys[-1], marker="s", color=color, markersize=8)
    else:
        ax.text(
            0.5, 0.5, "No entity state PDUs found",
            transform=ax.transAxes, ha="center", va="center", fontsize=14,
        )

    entity_count = len(entity_tracks)
    pdu_count = result["pdu_count"]
    ax.set_title(f"DIS Scenario: {entity_count} entities, {pdu_count} PDUs", fontsize=14)
    ax.set_xlabel("X Position (ECEF)", fontsize=11)
    ax.set_ylabel("Y Position (ECEF)", fontsize=11)
    if entity_tracks:
        ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    # 5. Save plot
    plot_path = Path(temp_dir) / "scenario_plot.png"
    fig.savefig(str(plot_path), dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved scenario plot to {plot_path}")

    # 6. Write metadata
    metadata_path = Path(temp_dir) / "metadata.json"
    metadata = {
        "function": "PlotScenario",
        "source_file": result["source_file"],
        "entity_count": entity_count,
        "pdu_count": pdu_count,
        "output_format": "PNG",
        "output_dpi": 200,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    outputs.append(Output(name="scenario_plot_png", type=OutputType.FILE, path=str(plot_path)))
    outputs.append(Output(name="metadata", type=OutputType.FILE, path=str(metadata_path)))

    return outputs


register("PlotScenario", plot_scenario)
