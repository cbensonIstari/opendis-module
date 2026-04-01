#!/usr/bin/env python3
"""Run opendis-module functions in a live Istari system with full digital thread.

Platform E2E test for @istari:opendis-module v1.0.0.
Tests all 5 functions: ParseDISStream, ExtractEntityStates, AnalyzeScenario,
ConvertDISToJSON, ValidateDISStream.
"""
import json
import os
import sys
import tempfile
import time
import yaml
from datetime import datetime
from pathlib import Path

# ── Credentials from config (NEVER hardcode) ──
config_path = os.path.expanduser(
    "~/Library/Application Support/istari_digital/istari_digital_config.yaml"
)
with open(config_path) as f:
    cfg = yaml.safe_load(f)
os.environ["ISTARI_REGISTRY_URL"] = cfg["cli"]["istari_digital_registry_url"]
os.environ["ISTARI_REGISTRY_AUTH_TOKEN"] = cfg["cli"]["istari_digital_registry_auth_token"]

from istari_digital_client import Client, NewSource
from istari_digital_client.v2.models import (
    NewSystem, NewSystemConfiguration, NewSnapshot,
    NewSnapshotTag, NewTrackedFile, TrackedFileSpecifierType,
)

FIXTURES = Path(__file__).parent / "test_inputs"
SCENARIO_BASIC = FIXTURES / "scenario_basic.dis"
SCENARIO_COMBAT = FIXTURES / "scenario_combat.dis"
SINGLE_ENTITY = FIXTURES / "single_entity.dis"
PLATFORM = "https://demo.istari.app"
NOW = datetime.now().strftime("%Y-%m-%d")
AGENT_ID = "e0fddacb-5ff2-4e47-b5df-9b64228e7f55"


def upload_with_retry(client, path, display_name, description, version_name, retries=3, delay=3):
    """Upload a model with retry logic for transient 500s."""
    for attempt in range(retries):
        try:
            if attempt > 0:
                time.sleep(delay * attempt)
            return client.add_model(
                path=str(path), display_name=display_name,
                description=description, version_name=version_name,
            )
        except Exception as e:
            print(f"    Upload attempt {attempt+1}/{retries} failed: {type(e).__name__}: {e}")
            if attempt == retries - 1:
                raise
    return None


def make_snapshot(client, config_id, name, tag_name=None, tag_desc=None):
    """Create snapshot + optional tag."""
    try:
        snap = client.create_snapshot(
            configuration_id=config_id,
            new_snapshot=NewSnapshot(name=name),
        )
        if hasattr(snap, 'id') and snap.id and tag_name:
            client.create_tag(
                snapshot_id=str(snap.id),
                new_snapshot_tag=NewSnapshotTag(name=tag_name, description=tag_desc or tag_name),
            )
            return str(snap.id)
    except Exception as e:
        print(f"    Snapshot skipped: {type(e).__name__}")
    return None


def main():
    client = Client()
    version_log = []
    job_results = []

    # ══════════════════════════════════════════════════════════
    # PHASE 1: Create System + Upload ALL Files
    # ══════════════════════════════════════════════════════════
    print("=" * 60)
    print("PHASE 1: Create System + Upload All Files")
    print("=" * 60)

    system = client.create_system(NewSystem(
        name=f"opendis-module — DIS Protocol Validation ({NOW})",
        description=(
            "Validation of @istari:opendis-module (v1.0.0) for Transfer Matrix "
            "domain (Simulation). Tests ParseDISStream, ExtractEntityStates, "
            "AnalyzeScenario, ConvertDISToJSON, ValidateDISStream against "
            "programmatically generated DIS binary fixtures."
        ),
    ))
    system_id = str(system.id)
    system_url = f"{PLATFORM}/systems/{system_id}"
    print(f"  System: {system_url}")

    # Upload README
    readme_dir = Path(tempfile.mkdtemp())
    readme_path = readme_dir / "SYSTEM_README.md"
    readme_path.write_text(
        f"# opendis-module — DIS Protocol Validation\n\n"
        f"**System:** [{system_url}]({system_url})\n\n"
        f"## Status\n\n| Step | Status |\n|------|--------|\n"
        f"| System created | DONE |\n| Files uploading | IN PROGRESS |\n\n"
        f"## Version History\n\n| Ver | Change |\n|-----|--------|\n"
        f"| v1 | Initial system setup |\n"
    )
    version_log.append("Initial system setup")

    time.sleep(1)
    readme_model = upload_with_retry(client, readme_path,
        "System README", "Living documentation for opendis-module validation", "v1 — Initial setup")
    readme_id = str(readme_model.id)
    readme_file_id = str(readme_model.revision.file_id)
    print(f"  README: {PLATFORM}/models/{readme_id}")

    # Upload input DIS fixtures
    time.sleep(2)
    basic_model = upload_with_retry(client, SCENARIO_BASIC,
        "DIS Scenario Basic (scenario_basic.dis)",
        "3 entities x 10 timesteps + 3 fire events + 2 detonations (DIS7 binary)",
        "v1 — Basic multi-entity scenario")
    basic_model_id = str(basic_model.id)
    basic_file_id = str(basic_model.revision.file_id)
    print(f"  scenario_basic.dis: {PLATFORM}/models/{basic_model_id}")

    time.sleep(2)
    combat_model = upload_with_retry(client, SCENARIO_COMBAT,
        "DIS Scenario Combat (scenario_combat.dis)",
        "2 entities x 20 timesteps + 5 fire + 5 detonation events (DIS7 binary)",
        "v1 — Combat scenario with heavy fire/detonation")
    combat_model_id = str(combat_model.id)
    combat_file_id = str(combat_model.revision.file_id)
    print(f"  scenario_combat.dis: {PLATFORM}/models/{combat_model_id}")

    # ══════════════════════════════════════════════════════════
    # PHASE 2: Create Configuration Tracking ALL Files
    # ══════════════════════════════════════════════════════════
    print(f"\n{'=' * 60}")
    print("PHASE 2: Create Configuration with All Tracked Files")
    print("=" * 60)

    tracked_files = [
        NewTrackedFile(file_id=readme_file_id, specifier_type=TrackedFileSpecifierType.LATEST),
        NewTrackedFile(file_id=basic_file_id, specifier_type=TrackedFileSpecifierType.LATEST),
        NewTrackedFile(file_id=combat_file_id, specifier_type=TrackedFileSpecifierType.LATEST),
    ]

    config = client.create_configuration(
        system_id=system_id,
        new_system_configuration=NewSystemConfiguration(
            name="Baseline — All inputs uploaded",
            tracked_files=tracked_files,
        ),
    )
    current_config_id = str(config.id)
    current_tracked = list(tracked_files)
    print(f"  Config: {current_config_id} ({len(tracked_files)} tracked files)")

    # Baseline snapshot
    make_snapshot(client, current_config_id,
                  "Baseline — README + all input models uploaded",
                  "baseline", "System initialized with all inputs before any jobs")

    # Update README
    version_num = 2
    version_log.append("All input models uploaded")
    readme_path.write_text(
        f"# opendis-module — DIS Protocol Validation\n\n"
        f"**System:** [{system_url}]({system_url})\n"
        f"**Module:** @istari:opendis-module v1.0.0 (Pattern A, opendis 1.0)\n"
        f"**Domain:** Simulation — IEEE 1278.1 DIS Protocol\n\n"
        f"## Inputs\n\n"
        f"| Model | Description | Link |\n|-------|-------------|------|\n"
        f"| scenario_basic.dis | 3 entities, 10 timesteps, fire+detonation | [{basic_model_id[:8]}]({PLATFORM}/models/{basic_model_id}) |\n"
        f"| scenario_combat.dis | 2 entities, 20 timesteps, heavy combat | [{combat_model_id[:8]}]({PLATFORM}/models/{combat_model_id}) |\n\n"
        f"## Status\n\n| Step | Status |\n|------|--------|\n"
        f"| System created | DONE |\n| All files uploaded | DONE |\n"
        f"| ParseDISStream | PENDING |\n| ExtractEntityStates | PENDING |\n"
        f"| AnalyzeScenario | PENDING |\n| ConvertDISToJSON | PENDING |\n"
        f"| ValidateDISStream | PENDING |\n\n"
        f"## Version History\n\n| Ver | Change |\n|-----|--------|\n"
        f"| v1 | Initial setup |\n| v2 | All inputs uploaded |\n"
    )
    client.update_model(model_id=readme_id, path=str(readme_path),
                        version_name="v2 — All input models uploaded")

    # ══════════════════════════════════════════════════════════
    # PHASE 3: Run Each Function
    # ══════════════════════════════════════════════════════════
    functions = [
        {
            "name": "ParseDISStream", "key": "@istari:ParseDISStream",
            "model_id": basic_model_id, "sources": None,
            "expect": "JSON with parsed PDU array including EntityState, Fire, Detonation PDUs",
        },
        {
            "name": "ExtractEntityStates", "key": "@istari:ExtractEntityStates",
            "model_id": basic_model_id, "sources": None,
            "expect": "JSON with entity state trajectories grouped by entity ID",
        },
        {
            "name": "AnalyzeScenario", "key": "@istari:AnalyzeScenario",
            "model_id": combat_model_id, "sources": None,
            "expect": "JSON scenario analysis with entity count, engagement events, timeline",
        },
        {
            "name": "ConvertDISToJSON", "key": "@istari:ConvertDISToJSON",
            "model_id": basic_model_id, "sources": None,
            "expect": "Full JSON conversion of all DIS PDU fields",
        },
        {
            "name": "ValidateDISStream", "key": "@istari:ValidateDISStream",
            "model_id": basic_model_id, "sources": None,
            "expect": "JSON validation report with valid/invalid PDU counts, issues",
        },
    ]

    for func in functions:
        fname = func["name"]
        fkey = func["key"]
        print(f"\n{'=' * 60}")
        print(f"FUNCTION: {fname}")
        print("=" * 60)

        # Pre-job snapshot
        make_snapshot(client, current_config_id,
                      f"Pre-job — about to run {fname}",
                      f"pre-{fname.lower()}", f"About to run {fname}")

        # Submit job with assigned agent
        print(f"  Submitting {fkey} (agent: {AGENT_ID[:12]}...)...")
        try:
            job = client.add_job(
                model_id=func["model_id"], function=fkey,
                assigned_agent_id=AGENT_ID,
                description=f"Platform E2E validation: {fname}",
                sources=func["sources"],
            )
            job_id = str(job.id)
            print(f"  Job: {PLATFORM}/jobs/{job_id}")
        except Exception as e:
            print(f"  SUBMIT ERROR: {e}")
            job_results.append({
                "function": fkey, "name": fname, "status": "SUBMIT_ERROR",
                "job_id": None, "artifacts": [],
            })
            continue

        # Poll for completion (15s intervals, 300s timeout)
        print(f"  Waiting...", end="", flush=True)
        start = time.time()
        final_status = "TIMEOUT"
        timeline_str = ""

        while time.time() - start < 300:
            j = client.get_job(job_id)
            d = j.to_dict()
            hist = d.get("status_history", [])
            if hist:
                latest = str(hist[-1].get("name", "")).upper()
                if "COMPLETED" in latest or "SUCCESS" in latest:
                    final_status = "COMPLETED"
                    timeline_str = " -> ".join(str(h.get("name", "")) for h in hist)
                    break
                elif "FAILED" in latest:
                    final_status = "FAILED"
                    timeline_str = " -> ".join(str(h.get("name", "")) for h in hist)
                    break
            print(".", end="", flush=True)
            time.sleep(15)

        elapsed = int(time.time() - start)
        print(f" {final_status} ({elapsed}s)")

        # Review artifacts
        artifact_details = []
        eng_summary = ""
        new_artifact_file_ids = []

        if final_status == "COMPLETED":
            try:
                arts = client.list_model_artifacts(model_id=func["model_id"])
                for art in arts.items:
                    afid = str(art.revision.file_id) if hasattr(art, 'revision') and art.revision else None
                    detail = {
                        "id": str(art.id), "name": str(art.name or ""),
                        "size": art.size if hasattr(art, 'size') else 0,
                        "link": f"{PLATFORM}/artifacts/{art.id}",
                        "file_id": afid,
                    }
                    artifact_details.append(detail)
                    if afid:
                        new_artifact_file_ids.append(afid)
                    print(f"  Artifact: {detail['name']} ({detail['size']} bytes) — {detail['link']}")

                    # Read JSON content for engineering summary
                    if str(art.name).endswith('.json'):
                        try:
                            data = json.loads(art.read_text())
                            if "pdu_count" in data:
                                eng_summary += f"{data['pdu_count']} PDUs parsed. "
                            if "entity_count" in data:
                                eng_summary += f"{data['entity_count']} entities. "
                            if "total_pdus" in data:
                                eng_summary += f"{data['total_pdus']} total PDUs. "
                            if "valid_count" in data:
                                eng_summary += f"{data['valid_count']} valid, {data.get('invalid_count',0)} invalid. "
                            if "engagement_count" in data or "fire_events" in data:
                                fires = data.get("fire_events", data.get("fire_count", "?"))
                                dets = data.get("detonation_events", data.get("detonation_count", "?"))
                                eng_summary += f"{fires} fire, {dets} detonation events. "
                        except Exception:
                            pass
            except Exception as e:
                print(f"  Artifact listing error: {e}")

        if not eng_summary:
            eng_summary = f"{final_status}. {len(artifact_details)} artifact(s)."

        job_results.append({
            "function": fkey, "name": fname, "status": final_status,
            "job_id": job_id, "artifacts": artifact_details,
            "duration": elapsed, "timeline": timeline_str, "summary": eng_summary,
        })

        # Create NEW configuration with artifacts tracked
        existing_file_ids = {tf.file_id for tf in current_tracked}
        if new_artifact_file_ids:
            for afid in new_artifact_file_ids:
                if afid not in existing_file_ids:
                    current_tracked.append(
                        NewTrackedFile(file_id=afid, specifier_type=TrackedFileSpecifierType.LATEST)
                    )
                    existing_file_ids.add(afid)
            try:
                new_config = client.create_configuration(
                    system_id=system_id,
                    new_system_configuration=NewSystemConfiguration(
                        name=f"After {fname} — {len(current_tracked)} files",
                        tracked_files=current_tracked,
                    ),
                )
                current_config_id = str(new_config.id)
                print(f"  New config: {current_config_id} ({len(current_tracked)} tracked files)")
            except Exception as e:
                print(f"  Config creation failed: {e}")

        # Post-job snapshot
        make_snapshot(client, current_config_id,
                      f"Post-{fname} — {final_status}, {len(artifact_details)} artifacts",
                      f"post-{fname.lower()}", f"{fname} {final_status}")

        # Update README with results
        version_num += 1
        version_log.append(f"Results from {fname} ({final_status})")

        # Rebuild full README
        status_rows = "| System created | DONE |\n| All files uploaded | DONE |\n"
        for jr in job_results:
            status_rows += f"| {jr['name']} | {jr['status']} ({jr.get('duration',0)}s) |\n"
        for f2 in functions:
            if not any(jr['name'] == f2['name'] for jr in job_results):
                status_rows += f"| {f2['name']} | PENDING |\n"

        results_sections = ""
        for jr in job_results:
            results_sections += (
                f"\n## Results: {jr['name']}\n\n"
                f"**Job:** [{jr['job_id'][:8] if jr['job_id'] else 'N/A'}...]({PLATFORM}/jobs/{jr['job_id']})\n"
                f"**Status:** {jr['status']} | **Duration:** {jr.get('duration',0)}s\n"
                f"**Timeline:** {jr.get('timeline','N/A')}\n\n"
            )
            if jr['artifacts']:
                results_sections += "### Artifacts\n\n| Artifact | Size | Link |\n|----------|------|------|\n"
                for a in jr['artifacts']:
                    results_sections += f"| {a['name']} | {a['size']}B | [{a['id'][:8]}...]({a['link']}) |\n"
            results_sections += f"\n### Engineering Summary\n\n{jr.get('summary','')}\n"

        ver_table = ""
        for i, v in enumerate(version_log):
            ver_table += f"| v{i+1} | {v} |\n"

        readme_path.write_text(
            f"# opendis-module — DIS Protocol Validation\n\n"
            f"**System:** [{system_url}]({system_url})\n"
            f"**Module:** @istari:opendis-module v1.0.0 (Pattern A, opendis 1.0)\n"
            f"**Domain:** Simulation — IEEE 1278.1 DIS Protocol\n\n"
            f"## Inputs\n\n"
            f"| Model | Description | Link |\n|-------|-------------|------|\n"
            f"| scenario_basic.dis | 3 entities, 10 timesteps, fire+detonation | [{basic_model_id[:8]}]({PLATFORM}/models/{basic_model_id}) |\n"
            f"| scenario_combat.dis | 2 entities, 20 timesteps, heavy combat | [{combat_model_id[:8]}]({PLATFORM}/models/{combat_model_id}) |\n\n"
            f"## Status\n\n| Step | Status |\n|------|--------|\n{status_rows}\n"
            f"{results_sections}\n"
            f"## Version History\n\n| Ver | Change |\n|-----|--------|\n{ver_table}\n"
        )
        client.update_model(model_id=readme_id, path=str(readme_path),
                            version_name=f"v{version_num} — Results from {fname}")

        # Documented snapshot
        make_snapshot(client, current_config_id,
                      f"Documented — {fname} results in README",
                      f"documented-{fname.lower()}", f"README updated with {fname} results")

    # ══════════════════════════════════════════════════════════
    # PHASE 4: Final Summary + Report
    # ══════════════════════════════════════════════════════════
    print(f"\n{'=' * 60}")
    print("PHASE 4: Final Summary")
    print("=" * 60)

    completed = sum(1 for r in job_results if r["status"] == "COMPLETED")
    failed = sum(1 for r in job_results if r["status"] != "COMPLETED")

    # Final README
    version_num += 1
    version_log.append("Final summary — all functions tested")

    status_rows = "| System created | DONE |\n| All files uploaded | DONE |\n"
    for jr in job_results:
        status_rows += f"| {jr['name']} | {jr['status']} ({jr.get('duration',0)}s) |\n"
    status_rows += "| **All functions tested** | **DONE** |\n"

    ver_table = ""
    for i, v in enumerate(version_log):
        ver_table += f"| v{i+1} | {v} |\n"

    results_sections = ""
    for jr in job_results:
        results_sections += (
            f"\n## Results: {jr['name']}\n\n"
            f"**Job:** [{jr['job_id'][:8] if jr['job_id'] else 'N/A'}...]({PLATFORM}/jobs/{jr['job_id']})\n"
            f"**Status:** {jr['status']} | **Duration:** {jr.get('duration',0)}s\n"
            f"**Timeline:** {jr.get('timeline','N/A')}\n\n"
        )
        if jr['artifacts']:
            results_sections += "### Artifacts\n\n| Artifact | Size | Link |\n|----------|------|------|\n"
            for a in jr['artifacts']:
                results_sections += f"| {a['name']} | {a['size']}B | [{a['id'][:8]}...]({a['link']}) |\n"
        results_sections += f"\n### Engineering Summary\n\n{jr.get('summary','')}\n"

    readme_path.write_text(
        f"# opendis-module — DIS Protocol Validation\n\n"
        f"**System:** [{system_url}]({system_url})\n"
        f"**Module:** @istari:opendis-module v1.0.0 (Pattern A, opendis 1.0)\n"
        f"**Domain:** Simulation — IEEE 1278.1 DIS Protocol\n\n"
        f"## Inputs\n\n"
        f"| Model | Description | Link |\n|-------|-------------|------|\n"
        f"| scenario_basic.dis | 3 entities, 10 timesteps, fire+detonation | [{basic_model_id[:8]}]({PLATFORM}/models/{basic_model_id}) |\n"
        f"| scenario_combat.dis | 2 entities, 20 timesteps, heavy combat | [{combat_model_id[:8]}]({PLATFORM}/models/{combat_model_id}) |\n\n"
        f"## Status\n\n| Step | Status |\n|------|--------|\n{status_rows}\n"
        f"{results_sections}\n"
        f"## Final Summary\n\n"
        f"- **Functions tested:** {len(functions)}\n"
        f"- **COMPLETED:** {completed}\n"
        f"- **FAILED/OTHER:** {failed}\n"
        f"- **Tracked files:** {len(current_tracked)}\n\n"
        f"## Version History\n\n| Ver | Change |\n|-----|--------|\n{ver_table}\n"
    )
    client.update_model(model_id=readme_id, path=str(readme_path),
                        version_name=f"v{version_num} — Final summary")

    # Final snapshot
    make_snapshot(client, current_config_id,
                  "Complete — All functions tested and documented",
                  "validation-complete", f"All {len(functions)} functions tested")

    # ── Save platform_test_report.json ──
    run_report = {
        "module": "@istari:opendis-module",
        "module_version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "system_id": system_id,
        "system_url": system_url,
        "readme_model_id": readme_id,
        "final_config_id": current_config_id,
        "agent_id": AGENT_ID,
        "functions_tested": [],
        "input_models": [
            {"name": "scenario_basic.dis", "model_id": basic_model_id,
             "description": "3 entities x 10 timesteps + 3 fire + 2 detonation (DIS7)"},
            {"name": "scenario_combat.dis", "model_id": combat_model_id,
             "description": "2 entities x 20 timesteps + 5 fire + 5 detonation (DIS7)"},
        ],
        "summary": {
            "total": len(functions),
            "completed": completed,
            "failed": failed,
            "tracked_files": len(current_tracked),
        },
    }

    for jr in job_results:
        func_entry = {
            "name": jr["name"],
            "function_key": jr["function"],
            "status": jr["status"],
            "job_id": jr.get("job_id"),
            "job_url": f"{PLATFORM}/jobs/{jr.get('job_id')}" if jr.get("job_id") else None,
            "duration_seconds": jr.get("duration", 0),
            "timeline": jr.get("timeline", ""),
            "engineering_summary": jr.get("summary", ""),
            "artifacts": [],
        }
        for a in jr.get("artifacts", []):
            art_entry = {
                "id": a["id"], "name": a["name"], "size": a["size"], "link": a["link"],
                "content": None,
            }
            try:
                art_obj = client.get_artifact(a["id"])
                if a["name"].endswith(".json"):
                    art_entry["content"] = json.loads(art_obj.read_text())
            except Exception:
                pass
            func_entry["artifacts"].append(art_entry)
        run_report["functions_tested"].append(func_entry)

    report_path = Path(__file__).parent / "results" / "platform_test_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(run_report, indent=2))
    print(f"\n  Platform test report saved: {report_path}")

    # ── FINAL REPORT ──
    print(f"\n{'=' * 60}")
    print(f"SYSTEM URL: {system_url}")
    print(f"{'=' * 60}")
    print(f"Functions: {len(functions)} | COMPLETED: {completed} | FAILED: {failed}")
    print(f"Tracked files: {len(current_tracked)} | README versions: {version_num}")

    return system_url, run_report


if __name__ == "__main__":
    url, report = main()
    print(f"\n\nFINAL SYSTEM LINK: {url}")
