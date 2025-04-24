# get pand ids from 3dbag api and save each to an individual json file (LoD 1.2 only)
# extract b3_h_maaiveld to find correct building heights
# run requests concurrently

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import pathlib
from typing import Iterable, List, Tuple, Dict, Any

import aiohttp
import boto3
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from tqdm.asyncio import tqdm



# batch files 
# "0B_pand_arch_map_6.json"
# "0B_pand_arch_map_7.json"
# "0B_pand_arch_map_8.json"
# "0B_pand_arch_map_21.json"

# ADJUST ARCH_MAP_FILE, OUTPUT_DIR, lOG_DIR

# ───────────────────────── inputs ──────────────────────────
ARCH_MAP_FILE = "0B_pand_arch_map_8.json"    # archetype
OUTPUT_DIR = pathlib.Path("1B_pand_jsons_8")
LOG_DIR = pathlib.Path("logs_8"); LOG_DIR.mkdir(exist_ok=True)                         

S3_BUCKET: str = ""         # leave empty, local files

CONCURRENT  = 10     # simultaneous TCP connections to api.3dbag.nl
BATCH_SIZE  = 500    # Pand IDs handled per batch
TIMEOUT_S   = 60     # per‑request timeout
MAX_RETRIES = 4      # Tenacity retries on 5xx / time‑out


TIMEOUT_LOG = LOG_DIR / f"timed_out_{datetime.date.today()}.txt"

#

s3       = boto3.client("s3")
_timeout = aiohttp.ClientTimeout(total=TIMEOUT_S)


# ─────────────────────── helpers ──────────────────────────────
def chunked(it: Iterable[Tuple[str, str]], n: int) -> Iterable[List[Tuple[str, str]]]:
    """Yield successive *n*-element lists from *it*."""
    buf: List[Tuple[str, str]] = []
    for item in it:
        buf.append(item)
        if len(buf) == n:
            yield buf
            buf = []
    if buf:
        yield buf


# ─────────────────── network / IO layer ─────────────────────────
@retry(
    stop  = stop_after_attempt(MAX_RETRIES),
    wait  = wait_exponential(min=5, max=120),
    retry = retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
)
async def fetch_one(pid: str, arche: str, session: aiohttp.ClientSession) -> None:
    """Download one Pand JSON, write it to disk or S3."""
    key = f"{pid}.json"

    if not S3_BUCKET:
        OUTPUT_DIR.mkdir(exist_ok=True)
        if (OUTPUT_DIR / key).exists():
            return                                 # already cached

    url = f"https://api.3dbag.nl/collections/pand/items/NL.IMBAG.Pand.{pid}"
    async with session.get(url, timeout=_timeout) as resp:
        resp.raise_for_status()
        data: Dict[str, Any] = await resp.json()

    # root feature
    features = data.get("features") or [data.get("feature")]
    if not features:
        return
    root = features[0]

    out: Dict[str, Any] = {
        "metadata": {**data.get("metadata", {}), "vertices": root.get("vertices", [])},
        "buildings": [],
    }

        # extract buildings
    for obj_id, obj in root.get("CityObjects", {}).items():
        if obj.get("type") != "Building":
            continue

        attr = obj["attributes"]
        building: Dict[str, Any] = {
            "Pand ID": pid,
            "Archetype ID": arche,
            "Status": attr.get("status"),
            "Construction Year": attr.get("oorspronkelijkbouwjaar"),
            "Number of Floors": attr.get("b3_bouwlagen"),
            "Roof Type": attr.get("b3_dak_type"),
            "Wall Area": attr.get("b3_opp_buitenmuur"),
            "Roof Area (Flat)": attr.get("b3_opp_dak_plat"),
            "Roof Area (Sloped)": attr.get("b3_opp_dak_schuin"),
            "Floor Area": attr.get("b3_opp_grond"),
            "Shared Wall Area": attr.get("b3_opp_scheidingsmuur"),
            "Ground Elevation (NAP)": attr.get("b3_h_maaiveld"),
            "LoD 1.2 Data": {},
            "Boundaries (LoD 1.2)": []
        }

        # LoD 1.2: extract roof height + boundaries from children
        for child_id in obj.get("children", []):
            child = root["CityObjects"].get(child_id, {})
            for geom in child.get("geometry", []):
                if geom.get("lod") != "1.2":
                    continue

                # Height data from RoofSurface
                for surf in geom.get("semantics", {}).get("surfaces", []):
                    if surf.get("type") == "RoofSurface":
                        building["LoD 1.2 Data"] = {
                            "Building Height (Mean)": surf.get("b3_h_dak_50p"),
                            "Building Height (70%)":   surf.get("b3_h_dak_70p"),
                            "Building Height (Max)":   surf.get("b3_h_dak_max"),
                            "Building Height (Min)":   surf.get("b3_h_dak_min"),
                        }
                        break  # first RoofSurface is enough

                # Save boundaries
                boundaries = geom.get("boundaries")
                if boundaries:
                    building["Boundaries (LoD 1.2)"].append(boundaries)

        out["buildings"].append(building)


    data_bytes = json.dumps(out, indent=2).encode()

    if S3_BUCKET:
        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data_bytes)
    else:
        (OUTPUT_DIR / key).write_bytes(data_bytes)


# ----- simple wrapper that always gives (pid, exc) back ------------
async def fetch_safe(
    pid: str,
    arche: str,
    session: aiohttp.ClientSession,
) -> Tuple[str, Exception | None]:
    """Run *fetch_one* with retries; never raise, always return (pid, exc?)."""
    try:
        await fetch_one(pid, arche, session)
        return pid, None
    except Exception as exc:
        return pid, exc


async def fetch_batch(
    batch: List[Tuple[str, str]],
    session: aiohttp.ClientSession,
) -> List[str]:
    """Download one batch concurrently, return the IDs that still failed."""

    tasks = [
        asyncio.create_task(fetch_safe(pid, arche, session))
        for pid, arche in batch
    ]

    failed: List[str] = []

    for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
        pid, exc = await fut
        if exc is None:
            continue                       # success
        failed.append(pid)
        logging.error("Unhandled error for %s – %s", pid, exc)

    return failed


# ──────────────────────────── main ─────────────────────────────
async def main() -> None:
    pand_to_arch: Dict[str, str] = json.load(open(ARCH_MAP_FILE))

    connector = aiohttp.TCPConnector(limit_per_host=CONCURRENT)
    all_failed: List[str] = []

    async with aiohttp.ClientSession(connector=connector) as session:
        for batch in chunked(pand_to_arch.items(), BATCH_SIZE):
            all_failed.extend(await fetch_batch(batch, session))

    if all_failed:
        with TIMEOUT_LOG.open("a") as fp:
            fp.writelines(f"{pid}\n" for pid in all_failed)
        print(f"{len(all_failed)} IDs failed – appended to {TIMEOUT_LOG}")

    print("done")


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s:%(message)s")
    asyncio.run(main())
